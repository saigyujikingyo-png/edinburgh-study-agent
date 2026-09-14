"""Export only verified cached course bytes over the existing private MCP channel.

A resource is transport data, not a ChatGPT file ID or a Drive upload receipt.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import os
import zipfile
from pathlib import Path
from urllib.parse import quote, urlsplit

from mcp.types import BlobResourceContents, CallToolResult, EmbeddedResource, TextContent
from .downloads import list_downloads, safe_filename
from .models import now_utc, safe_url

MAX_FILES = 30


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _read_cached(store, item_id, remaining):
    item = store.item(item_id)
    if item['kind'] != 'resource' or item['source'] != 'learn':
        raise ValueError('Export an observed Learn resource item_id.')
    root = store.root.resolve()
    cache = root / 'downloads'
    if cache.resolve() != cache:
        raise ValueError('The download cache is redirected; export was stopped.')
    for record in list_downloads(store, item_id)['files']:
        path = Path(record['path'])
        resolved = path.resolve()
        if not resolved.is_relative_to(cache) or resolved != path.absolute() or not resolved.is_file():
            continue
        if resolved.stat().st_size > remaining:
            raise ValueError('Export exceeds the byte limit; select fewer files or raise max_megabytes up to 32.')
        with resolved.open('rb') as stream:
            if os.fstat(stream.fileno()).st_size > remaining:
                raise ValueError('Export exceeds the byte limit; select fewer files.')
            body = stream.read(remaining + 1)
        digest = hashlib.sha256(body).hexdigest()
        if not body or len(body) > remaining or len(body) != record['size_bytes'] or digest != record['sha256']:
            continue
        filename = safe_filename(record['filename'])
        if filename != record['filename']:
            continue
        source = safe_url(record['source_page_url'])
        if urlsplit(source).hostname not in ('learn.ed.ac.uk', 'www.learn.ed.ac.uk'):
            raise ValueError('Export provenance must be an observed Learn page.')
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        uri = f'uoe://files/{digest}/{quote(filename, safe="")}'
        return {'item_id': item_id, 'filename': filename, 'mime_type': mime,
                'size_bytes': len(body), 'sha256': digest, 'resource_uri': uri,
                'source_page_url': source, 'downloaded_at': record['downloaded_at']}, body
    raise ValueError('No intact cached original for this item_id. Use study_download_files for the selected item, then export again.')


def export_files(store, item_ids, mode='files', max_megabytes=16):
    if mode not in ('manifest', 'files', 'bundle'):
        raise ValueError('mode must be manifest, files or bundle.')
    if not isinstance(item_ids, list) or not 1 <= len(item_ids) <= MAX_FILES:
        raise ValueError('Select 1..30 observed resource item_ids.')
    if any(not isinstance(x, str) or not x or len(x) > 512 for x in item_ids):
        raise ValueError('Select valid resource item_ids.')
    if len(set(item_ids)) != len(item_ids):
        raise ValueError('Duplicate item_ids are not exported twice.')
    if isinstance(max_megabytes, bool) or not isinstance(max_megabytes, int) or not 1 <= max_megabytes <= 32:
        raise ValueError('max_megabytes must be an integer from 1 to 32.')
    limit = max_megabytes * 1024 * 1024
    records, bodies, total = [], [], 0
    # All-or-nothing preflight: never send a partial selection labelled complete.
    for item_id in item_ids:
        record, body = _read_cached(store, item_id, limit - total)
        records.append(record)
        bodies.append(body)
        total += len(body)
    export_id = hashlib.sha256(_json({'mode': mode, 'files': records}).encode()).hexdigest()
    payloads = []
    if mode == 'files':
        payloads = [(r, b) for r, b in zip(records, bodies)]
    elif mode == 'bundle':
        buffer = io.BytesIO()
        manifest = {'format_version': '1', 'export_id': export_id, 'files': []}
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for index, (record, body) in enumerate(zip(records, bodies), 1):
                entry = f'{index:02d}/{record["filename"]}'
                info = zipfile.ZipInfo(entry, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, body, compresslevel=1)
                manifest['files'].append({**record, 'bundle_path': entry})
            info = zipfile.ZipInfo('manifest.json', (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, _json(manifest).encode('utf-8'), compresslevel=1)
        body = buffer.getvalue()
        if len(body) > limit:
            raise ValueError('The ZIP plus manifest exceeds the byte limit; select fewer files or increase max_megabytes.')
        digest = hashlib.sha256(body).hexdigest()
        filename = f'UoE-resources-{export_id[:12]}.zip'
        payloads = [({'filename': filename, 'mime_type': 'application/zip', 'size_bytes': len(body),
                     'sha256': digest, 'resource_uri': f'uoe://exports/{digest}/{filename}'}, body)]
    value = {'format_version': '1', 'export_id': export_id, 'mode': mode,
             'state': 'verified_local' if mode == 'manifest' else 'awaiting_host_receipt',
             'created_at': now_utc().isoformat(), 'files': records, 'total_bytes': total,
             'payloads': [{k: r[k] for k in ('filename', 'mime_type', 'size_bytes', 'sha256', 'resource_uri')} for r, _ in payloads],
             'host_registration': 'not_requested' if mode == 'manifest' else 'required',
             'next_step': ('Metadata only; call mode=files or bundle to deliver originals. No host registration occurred.' if mode == 'manifest' else 'Use the attachments/file references actually returned by the host after it materializes these MCP resources. Preserve filenames from this manifest when uploading. Other hosts must save resource blobs and verify size/SHA256 through their file API. Only pass a real host file reference to cloud connectors; never a uoe:// URI or campus computer path. Do not repeat downloads or paste binary into chat. Drive completion requires destination readback.')}
    content = [TextContent(type='text', text=_json(value))]
    content.extend(EmbeddedResource(type='resource', resource=BlobResourceContents(
        uri=record['resource_uri'], mimeType=record['mime_type'], blob=base64.b64encode(body).decode('ascii')))
        for record, body in payloads)
    return CallToolResult(content=content, structuredContent=value)
