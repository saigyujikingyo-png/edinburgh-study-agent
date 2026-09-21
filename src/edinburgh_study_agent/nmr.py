"""Resumable, source-scoped NMR acquisition with compact agent-facing results."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import time
import uuid

from .models import now_utc
from .nmr_client import NOMAD_ORIGIN, LEGACY_ORIGIN, LEGACY_PATH, NomadClient, NmrError, date_range, literal, check_cancel
from .nmr_legacy import LegacyClient, GROUPS
from .nmr_archive import inspect_archive
from .downloads import safe_filename


def _tables(store):
    with store.connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS nmr_requests (id TEXT PRIMARY KEY, updated_at REAL NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nmr_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)


def _save_request(store, request):
    with store.connection() as db:
        db.execute("INSERT OR REPLACE INTO nmr_requests VALUES(?,?,?)",
                   (request["id"], time.time(), json.dumps(request, ensure_ascii=False)))
        # Pending requests are private, bounded recovery context, not a full activity history.
        db.execute("DELETE FROM nmr_requests WHERE id NOT IN (SELECT id FROM nmr_requests ORDER BY updated_at DESC LIMIT 100)")


def _request(store, request_id):
    if request_id:
        with store.connection() as db:
            row = db.execute("SELECT payload FROM nmr_requests WHERE id=?", (request_id,)).fetchone()
        if not row: raise ValueError("Unknown or expired NMR request_id. Start a new sample query.")
        return json.loads(row[0])
    return {"id": uuid.uuid4().hex, "provider": "auto", "sample": None, "group": None,
            "start_date": None, "end_date": None, "archive": "archive", "allow_insecure_http": False,
            "candidates": [], "intent": "find"}


def record(store, item_id):
    """Private selection provenance. No generic capture can manufacture this record."""
    with store.connection() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nmr_records'").fetchone(): return None
        row = db.execute("SELECT payload FROM nmr_records WHERE id=?", (item_id,)).fetchone()
    return json.loads(row[0]) if row else None


def _record(store, request, data, subject):
    identity = data.get("experiment_id") or data.get("download_url")
    key = hashlib.sha256((request["provider"] + "\0" + subject + "\0" + identity).encode()).hexdigest()[:24]
    value = {**data, "id": key, "provider": request["provider"], "subject": subject,
             "observed_at": now_utc().isoformat(), "source_page_url":
                 NOMAD_ORIGIN + "/" if request["provider"] == "nomad" else LEGACY_ORIGIN + LEGACY_PATH}
    with store.connection() as db:
        db.execute("INSERT OR REPLACE INTO nmr_records VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))
    return value


def _public(value):
    return {k: value[k] for k in ("id", "dataset_name", "experiment_number", "sample", "title", "acquired_on",
                                  "parameter_set", "solvent", "instrument", "group", "observed_at") if value.get(k) is not None}


def _reply(request, state, message, **fields):
    return {"state": state, "request_id": request["id"], "provider": request["provider"],
            "sample": request.get("sample"), "message": message, **fields}


def _cached(store, item_id):
    from .delivery import _read_cached
    try:
        metadata, _ = _read_cached(store, item_id, 128*1024*1024)
        return {k: metadata[k] for k in ("item_id", "filename", "size_bytes", "sha256", "downloaded_at")}
    except (ValueError, OSError): return None


def _download(store, request, selected, max_megabytes, cancel_event=None):
    check_cancel(cancel_event)
    cached = _cached(store, selected["id"])
    if cached:
        return _reply(request, "downloaded", "Verified original already cached. Use study_export_files to deliver its bytes to the receiving host.",
                      files=[cached], cache_hit=True, source_transport="https" if selected["provider"] == "nomad" else "plaintext_http")
    from .nmr_auth import get_session
    session = get_session(store.root, request["provider"], request.get("group"))
    if not session:
        return _connect(store, request)
    subject = session["user_id"] if request["provider"] == "nomad" else session["group"]
    if selected["subject"] != subject:
        raise NmrError("SCOPE_MISMATCH", "The NMR account changed. Search this sample again before downloading.")
    root = store.root.resolve() / "downloads" / "nmr" / selected["id"]
    if root.resolve() != root: raise ValueError("NMR cache must not be redirected.")
    root.mkdir(parents=True, exist_ok=True)
    pending = root / (".partial-" + uuid.uuid4().hex)
    try:
        if selected["provider"] == "nomad":
            with NomadClient(session) as client:
                size = client.download(selected["experiment_id"], pending, max_megabytes*1024*1024, cancel_event=cancel_event)
        else:
            with LegacyClient(session, allow_insecure_http=request["allow_insecure_http"]) as client:
                size = client.download(selected["download_url"], pending, max_megabytes*1024*1024, cancel_event=cancel_event)
        check_cancel(cancel_event)
        manifest = inspect_archive(pending, selected["dataset_name"], selected["experiment_number"],
                                   parent_components=tuple(selected.get("parent_components", ())))
        with pending.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        filename = safe_filename(selected["dataset_name"] + "-" + selected["experiment_number"] + ".zip")
        folder = root / digest
        if folder.resolve() != folder: raise ValueError("NMR cache must not be redirected.")
        folder.mkdir(exist_ok=True)
        destination = folder / filename
        if destination.resolve() != destination: raise ValueError("NMR cache must not be redirected.")
        check_cancel(cancel_event)
        pending.replace(destination)
        receipt = {"item_id": selected["id"], "title": filename, "title_source": "filename",
                   "path": str(destination), "filename": filename, "size_bytes": size,
                   "sha256": digest, "source_page_url": selected["source_page_url"], "downloaded_at": now_utc().isoformat()}
        from .hosts import atomic_json
        atomic_json(folder / "manifest.json", {"format_version": "1", "archive": receipt, "validation": manifest,
                    "source_transport": "https" if selected["provider"] == "nomad" else "plaintext_http",
                    "scientific_interpretation": "not_performed"})
        check_cancel(cancel_event)
        with store.connection() as db:
            db.execute("INSERT OR REPLACE INTO downloads VALUES(?,?,?,?)",
                       (selected["id"], digest, receipt["downloaded_at"], json.dumps(receipt)))
            store.audit(db, "nmr_download_verified", selected["id"])
        return _reply(request, "downloaded", "Raw ZIP verified without extraction or spectral processing. Use study_export_files with the item_id to deliver original bytes; destination receipt remains separate.",
                      files=[{k: receipt[k] for k in ("item_id", "filename", "size_bytes", "sha256", "downloaded_at")}],
                      cache_hit=False, source_transport="https" if selected["provider"] == "nomad" else "plaintext_http",
                      integrity={"member_count": manifest["member_count"], "file_count": manifest["file_count"],
                                 "raw_files": manifest["raw_files"], "acquisition_files": manifest["acquisition_files"],
                                 "total_uncompressed_bytes": manifest["total_uncompressed_bytes"]})
    finally:
        pending.unlink(missing_ok=True)


def _connections(store):
    from .nmr_auth import get_session
    found = []
    for provider, group in (("nomad", None), *(("legacy", g) for g in GROUPS)):
        session = get_session(store.root, provider, group)
        if session and (session.get("provider") != provider or (group and session.get("group") != group)):
            session = None
        found.append({"provider": provider, **({"group": group} if group else {}),
                      "credentials_available": bool(session),
                      "authentication": session.get("authentication", "authenticated" if provider == "nomad" else "credentials_supplied") if session else "missing",
                      "remembered": bool(session and session.get("remembered")),
                      "persistence": session.get("persistence", "process_memory_only") if session else "none"})
    return found


def _connect(store, request, *, renew=False):
    from .nmr_auth import open_panel
    panel = open_panel(store.root, request["provider"], request.get("group"), request["id"],
                       request["allow_insecure_http"], renew=renew)
    return _reply(request, "authentication_pending",
        "Offer this small plugin-owned form directly, using URL elicitation or a clickable link. "
        "Do not operate school/browser GUI, use screenshots or request passwords in chat. "
        "Opening this local form sends no school request. It can save the group connection and its HTTP permission; "
        "after submission resume this request_id. Never request permission again merely to reopen a rejected form.",
        connection=panel)


def _failure(store, request, exc):
    if exc.code == "AUTH_REQUIRED":
        from .nmr_auth import forget_session
        forget_session(store.root, request["provider"], request.get("group"))
        return _reply(request, "needs_auth", "The school rejected this connection; it has been cleared. "
                      "Use connect with this request_id for protected replacement, then resume. Do not retry the rejected credential.",
                      code=exc.code, needed=["connection"])
    return _reply(request, "unavailable", str(exc), code=exc.code)


def run(store, action="status", *, provider="auto", sample=None, request_id=None, selection_id=None,
        group=None, start_date=None, end_date=None, archive=None, page=1, limit=10,
        allow_insecure_http=False, max_megabytes=32, cancel_event=None):
    from .nmr_auth import get_session, forget_session, open_panel
    if action not in ("status", "find", "resume", "connect", "reconnect", "download", "forget"):
        raise ValueError("Unknown NMR action.")
    if provider not in ("auto", "nomad", "legacy") or group not in (None, *GROUPS):
        raise ValueError("Choose NOMAD or the supported legacy teaching group.")
    if type(allow_insecure_http) is not bool: raise ValueError("HTTP consent must be an explicit boolean.")
    if type(max_megabytes) is not int or not 1 <= max_megabytes <= 128: raise ValueError("max_megabytes must be 1..128.")
    if type(page) is not int or not 1 <= page <= 100 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("page must be 1..100 and limit 1..20.")
    date_range(start_date, end_date)
    _tables(store)
    if action == "status":
        return {"state": "status", "provider": "auto", "connections": _connections(store),
                "message": "Reuse a saved NMR connection directly. Sample numbers can be supplied in chat or a supported host form. "
                "connect is idempotent; reconnect replaces a failed panel; forget removes the saved connection. "
                "Legacy remembered credentials include group-scoped HTTP consent. NOMAD uses its own expiring session."}
    request = _request(store, request_id)
    changes = {k: v for k, v in {"provider": provider if provider != "auto" else None,
        "sample": literal(sample) if sample is not None else None, "group": group,
        "start_date": start_date, "end_date": end_date, "archive": archive}.items() if v is not None}
    if any(request.get(k) != v for k, v in changes.items()):
        request["candidates"] = []
        request.pop("datasets", None)
        request["allow_insecure_http"] = False
    request.update(changes)
    if request["provider"] == "auto" or (request["provider"] == "legacy" and not request["group"]):
        available = [c for c in _connections(store) if c["credentials_available"]
                     and (request["provider"] == "auto" or c["provider"] == request["provider"])]
        if request["provider"] == "auto" and request["group"]:
            request["provider"] = "legacy"
        elif len(available) == 1:
            request.update(provider=available[0]["provider"], group=available[0].get("group"))
    if request["provider"] == "nomad": request["group"] = None
    if action in ("find", "download"):
        request["intent"] = action
    effective = request.get("intent", "find") if action == "resume" else action
    if request["archive"] not in ("archive", "backup"): raise ValueError("archive must be archive or backup.")
    date_range(request["start_date"], request["end_date"])
    if allow_insecure_http: request["allow_insecure_http"] = True
    _save_request(store, request)
    needed = []
    if request["provider"] == "auto": needed.append("provider")
    if action in ("find", "resume", "download") and not request["sample"]: needed.append("sample")
    if request["provider"] == "legacy" and not request["group"]: needed.append("group")
    if needed:
        return _reply(request, "needs_input", "Ask only for the listed non-secret fields, then call resume with this request_id. Keep sample numbers as text including leading zeros; old data is not assumed migrated to NOMAD.", needed=needed)
    if action == "forget":
        forget_session(store.root, request["provider"], request["group"])
        return _reply(request, "disconnected", "NMR credentials removed; downloaded originals are retained.")
    session = get_session(store.root, request["provider"], request.get("group"))
    if (request["provider"] == "legacy" and session and session.get("remembered")
            and session.get("insecure_http_approved")):
        request["allow_insecure_http"] = True
        _save_request(store, request)
    if action in ("connect", "reconnect"):
        if session and action == "connect":
            return _reply(request, "connected", "Saved connection is available; continue the sample request directly. "
                          "No new password form or school request was made. Use reconnect only to replace it.",
                          connections=[c for c in _connections(store) if c["provider"] == request["provider"]
                                       and c.get("group") == request.get("group")])
        return _connect(store, request, renew=action == "reconnect")
    if effective == "download" and not selection_id and len(request["candidates"]) == 1:
        selection_id = request["candidates"][0]
    if effective == "download" and selection_id and selection_id not in request.get("datasets", []):
        if selection_id not in request["candidates"]: raise ValueError("Select an item returned for this NMR request.")
        selected = record(store, selection_id)
        if not selected: raise ValueError("NMR selection no longer exists. Search again.")
        try: return _download(store, request, selected, max_megabytes, cancel_event)
        except NmrError as exc:
            return _failure(store, request, exc)
        except ValueError as exc:
            if not str(exc).startswith("NMR_ARCHIVE_"): raise
            return _reply(request, "unavailable", "The archive failed raw-data validation. No verified download was recorded.", code=str(exc))
    session = get_session(store.root, request["provider"], request["group"])
    if not session:
        return _connect(store, request)
    if request["provider"] == "legacy" and not request["allow_insecure_http"]:
        return _reply(request, "needs_input", "This temporary connection has no saved HTTP permission. "
                      "Ask for permission for this query, or connect once and remember the group for future queries.",
                      needed=["insecure_http_consent"])
    try:
        check_cancel(cancel_event)
        if request["provider"] == "legacy":
            with LegacyClient(session, allow_insecure_http=request["allow_insecure_http"]) as client:
                rows = client.search(request["sample"], start_date=request["start_date"], end_date=request["end_date"], source=request["archive"])
            subject, has_more = session["group"], False
        else:
            with NomadClient(session) as client:
                if selection_id:
                    if selection_id not in request.get("datasets", []): raise ValueError("Choose an observed dataset_name for this request.")
                    found = {"datasets": [], "has_more": False}
                else:
                    found = client.search(request["sample"], page=page, limit=limit, start_date=request["start_date"], end_date=request["end_date"])
                datasets = found["datasets"]
                if len(datasets) > 1 or (len(datasets) == 1 and found["has_more"]):
                    # A dataset name is only accepted if it was observed in this exact query.
                    request["datasets"] = [r["dataset_name"] for r in datasets]
                    _save_request(store, request)
                    return _reply(request, "needs_selection", "Several datasets match. Ask for the intended dataset/date; repeat find with selection_id equal to an observed dataset_name.",
                                  datasets=datasets, has_more=found["has_more"], page=page)
                if selection_id:
                    dataset = selection_id
                else: dataset = datasets[0]["dataset_name"] if datasets else None
                rows = client.experiments(dataset) if dataset else []
                if len(rows) > 20:
                    raise NmrError("SELECTION_TOO_LARGE", "This dataset contains more than 20 experiments; this preview needs a narrower dataset selection.")
            subject, has_more = session["user_id"], found["has_more"]
        check_cancel(cancel_event)
        saved = [_record(store, request, row, subject) for row in rows]
        request["candidates"] = [row["id"] for row in saved]
        _save_request(store, request)
        if not saved:
            return _reply(request, "no_matches", "No matching record was observed in this selected archive/scope. This does not prove the sample is absent elsewhere. Ask for its date/group or whether to search backup; never infer migration to NOMAD.",
                          has_more=has_more, source_transport="https" if request["provider"] == "nomad" else "plaintext_http")
        if effective == "download" and len(saved) == 1:
            return _download(store, request, saved[0], max_megabytes, cancel_event)
        return _reply(request, "ready" if len(saved) == 1 else "needs_selection",
                      "Use download with this request_id and a returned id. If several records match, ask which sample/date before downloading.",
                      results=[_public(r) for r in saved], has_more=has_more,
                      source_transport="https" if request["provider"] == "nomad" else "plaintext_http")
    except NmrError as exc:
        return _failure(store, request, exc)
    except ValueError as exc:
        if not str(exc).startswith("NMR_ARCHIVE_"): raise
        return _reply(request, "unavailable", "The archive failed raw-data validation. No verified download was recorded.", code=str(exc))
