"""Resolve only the current file page's unique visible attachment preview."""
import time
from urllib.parse import parse_qs, urlsplit
from .downloads import safe_filename, validate_download_url
from .file_errors import FileDownloadError
from .school_dom import CONTENT_PATH, learn_url

PREVIEW_TIMEOUT = 12


def filename(value):
    try:
        return safe_filename(value)
    except ValueError:
        return None


def visible_frame(frame, main):
    """Check every iframe ancestor; a visible child can have a hidden parent."""
    current = frame
    for _ in range(8):
        if current == main:
            return True
        if current.is_detached() or not current.frame_element().is_visible():
            return False
        current = current.parent_frame
        if current is None:
            return False
    return False


def resolve_original(page, item, navigate):
    target = learn_url(item.get("url") or "", item["course_id"])
    path = urlsplit(target).path.rstrip("/")
    match = CONTENT_PATH.fullmatch(path)
    if not match:
        raise FileDownloadError("ATTACHMENT_MISMATCH")
    if match[2] != "file":
        raise FileDownloadError("UNSUPPORTED_CONTAINER")
    navigate(page, target)
    expected_name = filename(item["title"])
    previous = None
    deadline = time.monotonic() + PREVIEW_TIMEOUT
    while time.monotonic() < deadline:
        # A successful SSO shell alone does not establish the requested resource.
        current = learn_url(page.url, item["course_id"])
        if urlsplit(current).path.rstrip("/") != path:
            raise FileDownloadError("ATTACHMENT_MISMATCH")
        frames = page.frames
        if len(frames) > 30:
            raise FileDownloadError("ATTACHMENT_AMBIGUOUS")
        candidates = []
        for frame in frames:
            if frame == page.main_frame:
                continue
            try:
                if not visible_frame(frame, page.main_frame):
                    continue
                originals = parse_qs(urlsplit(frame.url).query).get("originalUrl", [])
                if not originals:
                    continue
                button = frame.get_by_role("button", name="Download", exact=True)
                if not button.count() or not button.first.is_visible():
                    continue
                if len(originals) != 1 or button.count() != 1:
                    raise FileDownloadError("ATTACHMENT_AMBIGUOUS")
                try:
                    original = validate_download_url(originals[0])
                except ValueError:
                    raise FileDownloadError("ATTACHMENT_MISMATCH") from None
                actual_name = filename(frame.frame_element().get_attribute("title") or "")
                candidates.append((frame, original, actual_name))
            except FileDownloadError:
                raise
            except Exception:
                # Detached/loading frames are not selectable and may settle.
                continue
        if len(candidates) > 1:
            raise FileDownloadError("ATTACHMENT_AMBIGUOUS",
                                    candidates=[c[2] for c in candidates if c[2]])
        if candidates:
            frame, original, actual_name = candidates[0]
            if actual_name and expected_name and actual_name.casefold() != expected_name.casefold():
                raise FileDownloadError("ATTACHMENT_MISMATCH", candidates=[actual_name])
            fingerprint = (frame, original, actual_name)
            if fingerprint == previous:
                binding = {"method": "unique_visible_preview", "content_id": match[3],
                           "content_path": path}
                if actual_name:
                    binding["preview_filename"] = actual_name
                if expected_name:
                    binding["requested_filename"] = expected_name
                # The preview or HTTP header supplies the filename, never the label.
                return original, actual_name, binding
            previous = fingerprint
        else:
            previous = None
        time.sleep(0.2)
    raise FileDownloadError("PREVIEW_NOT_READY")
