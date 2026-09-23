"""Protected, temporary NMR sign-in on the computer running UoE Companion.

Only the local form receives passwords. Internal sessions must never be returned
as MCP payloads. Windows uses current-user DPAPI; other systems retain sessions
only in this process and disclose that limitation in the safe receipt.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.cookies import SimpleCookie, CookieError
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
import time
from urllib.parse import parse_qs

from .nmr_client import NomadClient, NmrError


LEGACY_GROUPS = ("3OR", "2OR")
PANEL_TTL_SECONDS = 600
MAX_PANELS = 4
MAX_POST_BYTES = 16 * 1024
MAX_SESSION_BYTES = 24 * 1024
MAX_VAULT_BYTES = MAX_SESSION_BYTES + 8 * 1024
MAX_MEMORY_SESSIONS = 32
_WINDOWS = os.name == "nt"
_LOCK = threading.RLock()
_MEMORY = {}
_PANELS = {}


def _provider(provider, group):
    if not ((provider == "nomad" and group is None)
            or (provider == "legacy" and group in LEGACY_GROUPS)):
        raise ValueError("NMR_AUTH_INVALID_PROVIDER_OR_GROUP")


def _root(root):
    try:
        return Path(root).resolve()
    except (OSError, TypeError, ValueError):
        raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE") from None


def _identity(root, provider, group):
    _provider(provider, group)
    return str(_root(root)), provider, group


def _text(value, maximum, *, empty=False):
    return (isinstance(value, str) and (empty or bool(value)) and len(value) <= maximum
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def _validated(session, provider, group, *, allow_expired=False):
    if not isinstance(session, dict):
        raise ValueError("NMR_AUTH_INVALID_SESSION")
    fields = ({"provider", "token", "user_id", "username", "group", "expires_at"}
              if provider == "nomad" else
              {"provider", "group", "password", "expires_at", "insecure_http_approved"})
    if set(session) - fields - {"authentication", "persistence", "remembered"} or not fields.issubset(session):
        raise ValueError("NMR_AUTH_INVALID_SESSION")
    remembered = session.get("remembered", False)
    if type(remembered) is not bool or (remembered and provider != "legacy"):
        raise ValueError("NMR_AUTH_INVALID_SESSION")
    # A remembered teaching credential is not a server session. Persist it until
    # explicit replacement/forget; clients receive a short-lived in-memory view.
    expires = session["expires_at"]
    if remembered and expires is None:
        expires = time.time() + 3600
    maximum_lifetime = 366 * 86400 if provider == "nomad" else 3600
    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
        raise ValueError("NMR_AUTH_INVALID_SESSION")
    try:
        expires = float(expires)
    except OverflowError:
        raise ValueError("NMR_AUTH_INVALID_SESSION") from None
    if (session["provider"] != provider or not math.isfinite(expires)
            or expires > time.time() + maximum_lifetime + 1
            or (not allow_expired and expires <= time.time())):
        raise ValueError("NMR_AUTH_INVALID_SESSION")
    if provider == "nomad":
        valid = (_text(session["token"], 16384)
                 and re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", session["token"])
                 and _text(session["user_id"], 24)
                 and re.fullmatch(r"[a-fA-F0-9]{24}", session["user_id"])
                 and _text(session["username"], 128) and _text(session["group"], 128, empty=True))
    else:
        valid = (session["group"] == group and _text(session["password"], 1024)
                 and session["insecure_http_approved"] is True)
    if not valid:
        raise ValueError("NMR_AUTH_INVALID_SESSION")
    value = {name: session[name] for name in fields}
    if remembered:
        value.update(remembered=True, expires_at=None)
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_SESSION_BYTES:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError("NMR_AUTH_INVALID_SESSION") from None
    return value


def _persistence():
    return "windows_dpapi" if _WINDOWS else "process_memory_only"


def _receipt(session):
    return {"provider": session["provider"], "expires_at": session["expires_at"],
            "persistence": _persistence(), "remembered": session.get("remembered", False),
            "authentication": "authenticated" if session["provider"] == "nomad" else "credentials_supplied"}


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(payload, provider, group, *, decrypt=False):
    """Use DPAPI in the current user's scope without UI or machine-wide keys."""
    if not _WINDOWS:
        raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE")
    source = ctypes.create_string_buffer(payload)
    entropy = ctypes.create_string_buffer(("UoE NMR vault v1:" + provider + ":" + (group or "")).encode())
    input_blob = _Blob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    entropy_blob = _Blob(len(entropy.raw) - 1, ctypes.cast(entropy, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _Blob()
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if decrypt:
            operation = crypt32.CryptUnprotectData
            description_type = ctypes.POINTER(wintypes.LPWSTR)
            description = None
        else:
            operation = crypt32.CryptProtectData
            description_type = wintypes.LPCWSTR
            description = "UoE Companion NMR session"
        operation.argtypes = [ctypes.POINTER(_Blob), description_type, ctypes.POINTER(_Blob),
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
        operation.restype = wintypes.BOOL
        if not operation(ctypes.byref(input_blob), description, ctypes.byref(entropy_blob),
                         None, None, 0x1, ctypes.byref(output_blob)):
            raise ValueError("NMR_AUTH_INVALID_VAULT" if decrypt else "NMR_AUTH_STORAGE_UNAVAILABLE")
        limit = MAX_SESSION_BYTES if decrypt else MAX_VAULT_BYTES
        if output_blob.cbData > limit:
            raise ValueError("NMR_AUTH_INVALID_VAULT")
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    except (OSError, AttributeError, ctypes.ArgumentError):
        raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE") from None
    finally:
        ctypes.memset(source, 0, len(source))
        ctypes.memset(entropy, 0, len(entropy))
        if output_blob.pbData:
            ctypes.memset(output_blob.pbData, 0, output_blob.cbData)
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def _vault_path(root, provider, group, *, create=False):
    directory = _root(root) / "secrets"
    try:
        if directory.resolve() != directory or directory.is_symlink():
            raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE")
        if create:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = hashlib.sha256((provider + ":" + (group or "")).encode()).hexdigest()[:24]
        path = directory / ("nmr-" + key + ".dpapi")
        if path.resolve() != path or path.is_symlink():
            raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE")
        return path
    except OSError:
        raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE") from None


def _expired(value):
    return not value.get("remembered", False) and value["expires_at"] <= time.time()


def _client_view(value):
    result = {**value, **_receipt(value)}
    if value.get("remembered"):
        result["expires_at"] = time.time() + 3600
    return result


def get_session(root: Path, provider: str, group: str | None = None) -> dict | None:
    """Return a private, client-compatible session. Never expose it as MCP output."""
    key = _identity(root, provider, group)
    with _LOCK:
        if not _WINDOWS:
            value = _MEMORY.get(key)
            if value is None or _expired(value):
                _MEMORY.pop(key, None)
                return None
            return _client_view(value)
        path = _vault_path(root, provider, group)
        try:
            with path.open("rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_VAULT_BYTES:
                    raise ValueError("NMR_AUTH_INVALID_VAULT")
                raw = stream.read(MAX_VAULT_BYTES + 1)
            if not raw or len(raw) > MAX_VAULT_BYTES:
                raise ValueError("NMR_AUTH_INVALID_VAULT")
        except FileNotFoundError:
            return None
        except OSError:
            raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE") from None
        try:
            value = _validated(json.loads(_crypt(raw, provider, group, decrypt=True)),
                               provider, group, allow_expired=True)
        except (ValueError, UnicodeError, TypeError, RecursionError):
            raise ValueError("NMR_AUTH_INVALID_VAULT") from None
        return None if _expired(value) else _client_view(value)


def save_session(root: Path, provider: str, session: dict, group: str | None = None) -> dict:
    """Save a bounded private session and return only a non-secret status receipt."""
    key = _identity(root, provider, group)
    value = _validated(session, provider, group)
    with _LOCK:
        if not _WINDOWS:
            for expired in [entry for entry, saved in _MEMORY.items() if _expired(saved)]:
                _MEMORY.pop(expired, None)
            if key not in _MEMORY and len(_MEMORY) >= MAX_MEMORY_SESSIONS:
                raise ValueError("NMR_AUTH_STORAGE_LIMIT")
            _MEMORY[key] = value
        else:
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
            encrypted = _crypt(raw, provider, group)
            path = _vault_path(root, provider, group, create=True)
            temporary = None
            try:
                descriptor, name = tempfile.mkstemp(prefix=".nmr-", suffix=".tmp", dir=path.parent)
                temporary = Path(name)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encrypted)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            except OSError:
                raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE") from None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass  # Only an encrypted temporary may remain after an OS failure.
    return _receipt(value)


def forget_session(root: Path, provider: str, group: str | None = None):
    """Revoke this provider/group's panels and forget its private session."""
    key = _identity(root, provider, group)
    with _LOCK:
        for panel_key, panel in _PANELS.items():
            if panel_key[:3] == key:
                panel.stop.set()
        _MEMORY.pop(key, None)
        if _WINDOWS:
            try:
                _vault_path(root, provider, group).unlink(missing_ok=True)
            except OSError:
                raise ValueError("NMR_AUTH_STORAGE_UNAVAILABLE") from None


class _LocalServer(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 4

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address

    def handle_error(self, *_):
        pass  # Never print HTTP bodies, capabilities, account names or stack traces.


class _Panel:
    def __init__(self, root, provider, group, request_id):
        self.root, self.provider, self.group, self.request_id = root, provider, group, request_id
        self.connection_id = secrets.token_hex(16)
        self.path = "/" + secrets.token_urlsafe(32) + "/"
        self.nonce = secrets.token_urlsafe(32)
        self.cookie_name = "uoe_nmr_" + self.connection_id
        self.cookie = secrets.token_urlsafe(32)
        self.rejected = False
        self.http_approved = False
        self.remembered = False
        self.stop = threading.Event()
        self.deadline = time.monotonic() + PANEL_TTL_SECONDS
        self.expires_at = datetime.fromtimestamp(time.time() + PANEL_TTL_SECONDS, timezone.utc).isoformat()
        self.attempts = 0
        self.last_error = None
        self.network_guidance = None

    def receipt(self):
        result = {"url": self.origin + self.path, "connection_id": self.connection_id,
                  "expires_at": self.expires_at, "reachability": "runtime_computer_browser"}
        if self.last_error: result["error_code"] = self.last_error
        if self.network_guidance:
            result.update({k: v for k, v in self.network_guidance.items() if k != "message"},
                          network_message=self.network_guidance["message"])
        return result

    def page(self, *, error=False, complete=False, locale="en"):
        from .nmr_form import render
        return render(self, error=error, complete=complete, locale=locale, persistent=_WINDOWS)



def _handler(panel):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_error(self, code, message=None, explain=None):
            self.respond(code, "The local connection request was rejected.")

        def respond(self, status, text):
            # Drain only a small declared request body before closing. Otherwise
            # Windows may reset a rejected connection and discard the 4xx reply.
            if (self.command == "POST" and getattr(self, "headers", None) is not None
                    and not getattr(self, "_body_consumed", False)):
                lengths = self.headers.get_all("Content-Length", [])
                if (not self.headers.get_all("Transfer-Encoding") and len(lengths) == 1
                        and re.fullmatch(r"[0-9]{1,6}", lengths[0])
                        and 0 < int(lengths[0]) <= MAX_POST_BYTES):
                    try:
                        self.rfile.read(int(lengths[0]))
                    except OSError:
                        pass
                self._body_consumed = True
            raw = text.encode("utf-8")
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            # no-referrer makes normal browser form POSTs send Origin: null.
            # same-origin retains local provenance without leaking it off-site.
            self.send_header("Referrer-Policy", "same-origin")
            if status == 200 and self.command == "GET":
                self.send_header("Set-Cookie", f"{panel.cookie_name}={panel.cookie}; Path={panel.path}; HttpOnly; SameSite=Strict; Max-Age={PANEL_TTL_SECONDS}")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except OSError:
                pass

        def allowed(self, post=False):
            hosts = self.headers.get_all("Host", [])
            origins = self.headers.get_all("Origin", [])
            if hosts != [panel.origin.removeprefix("http://")] or self.path != panel.path:
                return False
            if not post:
                return origins in ([], [panel.origin])
            fetch_site = self.headers.get_all("Sec-Fetch-Site", [])
            if fetch_site not in ([], ["same-origin"]):
                return False
            cookies = SimpleCookie()
            try:
                cookie_headers = self.headers.get_all("Cookie", [])
                if len(cookie_headers) != 1:
                    return False
                cookies.load(cookie_headers[0])
                cookie = cookies.get(panel.cookie_name)
                if not cookie or not secrets.compare_digest(cookie.value, panel.cookie):
                    return False
            except (CookieError, TypeError):
                return False
            if origins == [panel.origin]:
                return True
            # Older/privacy browsers may omit Origin. Accept only with an exact
            # local referrer, the independent cookie and the body nonce below.
            return (origins in ([], ["null"])
                    and self.headers.get_all("Referer", []) == [panel.origin + panel.path])

        def active(self):
            return not panel.stop.is_set() and time.monotonic() < panel.deadline

        def locale(self):
            return "zh" if self.headers.get("Accept-Language", "en").lower().startswith("zh") else "en"

        def do_GET(self):
            if not self.allowed():
                self.respond(403, "Open the exact connection link supplied by your agent.")
            elif not self.active():
                self.respond(410, "The connection panel expired. Return to your agent; the request is retained.")
            else:
                self.respond(200, panel.page(locale=self.locale()))

        def do_POST(self):
            if not self.allowed(post=True):
                panel.rejected = True
                self.respond(403, "Submit only from the protected local connection form.")
                return
            if not self.active():
                self.respond(410, "The connection panel expired. Return to your agent; the request is retained.")
                return
            if self.headers.get_all("Content-Type", []) != ["application/x-www-form-urlencoded"]:
                self.respond(415, "Use the protected connection form.")
                return
            lengths = self.headers.get_all("Content-Length", [])
            if (self.headers.get_all("Transfer-Encoding") or len(lengths) != 1
                    or not re.fullmatch(r"[0-9]{1,6}", lengths[0]) or not 0 < int(lengths[0]) <= MAX_POST_BYTES):
                self.respond(413, "The connection form exceeds its bounded request size.")
                return
            values = {}
            try:
                raw = self.rfile.read(int(lengths[0]))
                self._body_consumed = True
                if len(raw) != int(lengths[0]):
                    raise ValueError()
                values = parse_qs(raw.decode("utf-8"), strict_parsing=True, keep_blank_values=True,
                                  max_num_fields=6, encoding="utf-8", errors="strict")
                expected = {"nonce", "password", "username"} if panel.provider == "nomad" else {"nonce", "password"}
                optional = {"remember", "http_consent"} if panel.provider == "legacy" else set()
                if (not expected.issubset(values) or set(values) - expected - optional
                        or any(len(value) != 1 for value in values.values())
                        or any(values[k] != ["yes"] for k in optional if k in values)):
                    raise ValueError()
                nonce = values["nonce"][0]
                if not nonce.isascii() or not secrets.compare_digest(nonce, panel.nonce):
                    self.respond(403, "The connection form nonce is invalid.")
                    return
                if not _text(values["password"][0], 1024):
                    raise ValueError()
                if panel.provider == "nomad" and not _text(values["username"][0], 128):
                    raise ValueError()
            except (ValueError, UnicodeError, OSError):
                self.respond(400, "The connection form is invalid. The request is retained.")
                return
            try:
                panel.attempts += 1
                panel.last_error = None
                panel.network_guidance = None
                if panel.provider == "nomad":
                    with NomadClient() as connection:
                        session = connection.login(values["username"][0], values["password"][0])
                else:
                    if values.get("http_consent") != ["yes"]:
                        self.respond(400, panel.page(error="consent", locale=self.locale()))
                        return
                    remembered = values.get("remember") == ["yes"]
                    session = {"provider": "legacy", "group": panel.group, "password": values["password"][0],
                               "expires_at": None if remembered else time.time() + 3600,
                               "remembered": remembered, "insecure_http_approved": True}
                # Disconnect and the active-check/save transition share a lock:
                # either this save finishes before disconnect removes it, or a
                # revoked panel can never write a session back afterwards.
                with _LOCK:
                    saved = self.active()
                    if saved:
                        save_session(panel.root, panel.provider, session, panel.group)
                        panel.remembered = session.get("remembered", False)
                        panel.stop.set()
                if saved:
                    self.respond(200, panel.page(complete=True, locale=self.locale()))
                else:
                    self.respond(410, "The connection panel expired or was closed. Return to your agent; the request is retained.")
            except NmrError as exc:
                from .nmr_network import NETWORK_ERRORS, failure_guidance
                panel.last_error = exc.code
                if exc.code in NETWORK_ERRORS:
                    panel.network_guidance = failure_guidance()
                    self.respond(503, panel.page(error=panel.network_guidance["network"]["state"], locale=self.locale()))
                else:
                    self.respond(401, panel.page(error="authentication" if exc.code == "AUTH_REQUIRED" else True, locale=self.locale()))
                if panel.attempts >= 5:
                    panel.stop.set()
            except Exception:
                self.respond(401, panel.page(error=True, locale=self.locale()))
                if panel.attempts >= 5:
                    panel.stop.set()
            finally:
                values.clear()
    return Handler


def open_panel(root: Path, provider: str, group: str | None, request_id: str,
               allow_insecure_http: bool = False, *, renew: bool = False) -> dict:
    """Start a finite loopback panel; the caller may offer its URL through its host."""
    identity = _identity(root, provider, group)
    if (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id)):
        raise ValueError("NMR_AUTH_INVALID_REQUEST")
    if type(allow_insecure_http) is not bool or type(renew) is not bool:
        raise ValueError("NMR_AUTH_INVALID_REQUEST")
    key = (*identity, request_id)
    with _LOCK:
        previous = _PANELS.get(key)
        if previous is not None:
            if (not renew and not previous.rejected and not previous.stop.is_set()
                    and time.monotonic() < previous.deadline):
                return previous.receipt()
            previous.stop.set()
        active = sum(not p.stop.is_set() and time.monotonic() < p.deadline for p in _PANELS.values())
        if active >= MAX_PANELS:
            raise ValueError("NMR_AUTH_PANEL_LIMIT")
        panel = _Panel(_root(root), provider, group, request_id)
        panel.http_approved = allow_insecure_http
        try:
            server = _LocalServer(("127.0.0.1", 0), _handler(panel))
        except OSError:
            raise ValueError("NMR_AUTH_PANEL_UNAVAILABLE") from None
        server.timeout = min(0.5, PANEL_TTL_SECONDS)
        panel.origin = f"http://127.0.0.1:{server.server_port}"

        def serve():
            try:
                while not panel.stop.is_set() and time.monotonic() < panel.deadline:
                    server.handle_request()
            finally:
                server.server_close()
                with _LOCK:
                    if _PANELS.get(key) is panel:
                        _PANELS.pop(key, None)

        panel.thread = threading.Thread(target=serve, daemon=True, name="uoe-nmr-connection")
        _PANELS[key] = panel
        panel.thread.start()
        return panel.receipt()
