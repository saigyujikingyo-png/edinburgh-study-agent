"""Learn document attachments from visible DOM metadata, never application stores."""
import json
import time
from urllib.parse import urljoin, urlsplit

from .downloads import safe_filename, validate_download_url
from .file_errors import FileDownloadError
from .models import Item, LearnAttachment
from .school_dom import CONTENT_PATH, LEARN_HOSTS, learn_url

MAX_ATTACHMENTS = 100
# Keep hidden copies from the outline/editor out of the current document's scope.
# No preview rendering, images, alternative formats or GUI download controls.
ATTACHMENTS = """() => {
  const nodes = [...document.querySelectorAll('[data-bbtype="attachment"]')]
    .filter(e => e.checkVisibility({opacityProperty:true,visibilityProperty:true}));
  return {total:nodes.length, rows:nodes.slice(0,100).map(e => ({
    data:(e.getAttribute('data-bbfile') || '').slice(0,8192),
    text:e.innerText.slice(0,1000),
    asset:e.querySelector('[data-ally-file-eid]')?.getAttribute('data-ally-file-eid') || ''
  }))};
}"""


def document(item):
    match = CONTENT_PATH.fullmatch(urlsplit(item.get("url") or "").path.rstrip("/"))
    return bool(match and match[2] == "document" and not item.get("attachment"))


def current_document(page, parent):
    target = learn_url(parent["url"], parent["course_id"])
    path = urlsplit(target).path.rstrip("/")
    match = CONTENT_PATH.fullmatch(path)
    if (not match or match[2] != "document" or match[3] != parent["native_id"]
            or urlsplit(learn_url(page.url, parent["course_id"])).path.rstrip("/") != path):
        raise FileDownloadError("ATTACHMENT_MISMATCH")
    return urlsplit(target)._replace(path=path, query="", fragment="").geturl()


def parse_rows(snapshot, parent, url):
    items, conflicts = {}, set()
    skipped = max(0, snapshot["total"] - len(snapshot["rows"]))
    for row in snapshot["rows"]:
        try:
            data = json.loads(row["data"])
            resource = urlsplit(data["resourceUrl"])
            # Only stable, credential-free addresses can identify an attachment.
            validate_download_url(data["resourceUrl"])
            if resource.hostname not in LEARN_HOSTS or resource.query or resource.fragment:
                raise ValueError("Not a stable Learn attachment address.")
            label = data.get("displayName") or data.get("linkName") or data["fileName"]
            if not isinstance(label, str) or not label.strip() or label.strip() not in row["text"]:
                raise ValueError("Attachment label was not visible.")
            name = safe_filename(data["fileName"])
            meta = LearnAttachment(parent_native_id=parent["native_id"], asset_id=row["asset"],
                resource_path=resource.path, filename=name, size_bytes=data["fileSize"],
                media_type=data["mimeType"])
            item = Item(native_id=parent["native_id"] + ":attachment:" + meta.asset_id,
                kind="resource", title=label.strip()[:500], url=url,
                course_id=parent["course_id"], course_title=parent.get("course_title"),
                excerpt=(label.strip() + "\n" + data["fileName"])[:3000],
                status="available", attachment=meta)
            previous = items.get(meta.asset_id)
            if previous and previous.attachment != meta:
                conflicts.add(meta.asset_id)
            else:
                items[meta.asset_id] = item
        except (ValueError, TypeError, KeyError, AttributeError):
            skipped += 1
    for key in conflicts:
        items.pop(key, None)
    return list(items.values()), {"visible_nodes":snapshot["total"],
        "indexed":len(items), "skipped":skipped + len(conflicts),
        "coverage":"visible_document_attachments"}


def discover(page, parent):
    url = current_document(page, parent)
    # A document may mount attachment cards just after its text. Bounded settling
    # avoids interpreting the first empty render as an exhaustive inventory.
    previous, snapshot = None, None
    for _ in range(5):
        snapshot = page.evaluate(ATTACHMENTS)
        if snapshot == previous and snapshot["rows"]:
            break
        previous = snapshot
        time.sleep(0.15)
    current_document(page, parent)
    return parse_rows(snapshot, parent, url)


def resolve(page, item, navigate):
    expected = LearnAttachment.model_validate(item["attachment"])
    parent = {**item, "native_id":expected.parent_native_id, "attachment":None}
    target = learn_url(item["url"], item["course_id"])
    if urlsplit(page.url)._replace(query="",fragment="") != urlsplit(target)._replace(query="",fragment=""):
        navigate(page, target)
    url = current_document(page, parent)
    observed, _ = discover(page, parent)
    selected = [i for i in observed if i.native_id == item["native_id"]]
    if len(selected) != 1 or selected[0].attachment != expected:
        raise FileDownloadError("ATTACHMENT_MISMATCH")
    # One authenticated, body-free request to an observed same-origin URL. The
    # campus session remains inside the browser; only a short-lived download
    # redirect is handed to the existing streaming downloader.
    response = None
    try:
        source = urljoin(url, expected.resource_path)
        response = page.context.request.head(source, max_redirects=0, timeout=15000)
        if response.status not in {301,302,303,307,308}:
            raise FileDownloadError("DOWNLOAD_HTTP_ERROR", http_status=response.status)
        target = validate_download_url(urljoin(source, response.headers.get("location", "")))
        if urlsplit(target).path != expected.resource_path or target == source:
            raise FileDownloadError("ATTACHMENT_MISMATCH")
    except FileDownloadError:
        raise
    except ValueError:
        raise FileDownloadError("ATTACHMENT_MISMATCH") from None
    except Exception:
        raise FileDownloadError("DOWNLOAD_NETWORK_ERROR") from None
    finally:
        if response is not None:
            response.dispose()
    binding = {"method":"observed_inline_attachment", "content_id":expected.parent_native_id,
        "content_path":urlsplit(url).path, "asset_id":expected.asset_id,
        "resource_path":expected.resource_path, "preview_filename":expected.filename,
        "expected_size_bytes":expected.size_bytes}
    return target, expected.filename, binding
