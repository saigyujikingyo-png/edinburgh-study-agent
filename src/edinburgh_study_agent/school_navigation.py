"""Observe only Learn's top-level navigation; never retain URLs or error text."""
from urllib.parse import urlsplit

from .school_errors import HOSTS, LoginRequired, SchoolNetworkError, SchoolPageNotReady

NAVIGATION_TIMEOUT_MS = 12000


def error_code(error):
    text = str(error)
    if "ERR_ABORTED" in text or "ERR_BLOCKED_BY_CLIENT" in text:
        return None  # Ordinary redirects and deliberately blocked assets are not outages.
    if "TIMED_OUT" in text or isinstance(error, TimeoutError) or type(error).__name__ == "TimeoutError":
        return "NETWORK_TIMEOUT"
    if "ERR_NAME_NOT_RESOLVED" in text:
        return "NETWORK_DNS"
    if any(s in text for s in ("ERR_CERT_", "ERR_SSL_", "ERR_TLS_")):
        return "TLS_ERROR"
    if any(s in text for s in ("ERR_CONNECTION_", "ERR_INTERNET_DISCONNECTED", "ERR_NETWORK_", "ERR_PROXY_", "ERR_TUNNEL_", "ERR_ADDRESS_")):
        return "NETWORK_CONNECTION"
    return None


class Navigation:
    def __init__(self, page):
        self.page = page
        self.host = None
        self.stage = "learn"
        self.http_status = None
        self.authentication_required = False
        self.failure_code = None
        if hasattr(page, "on"):
            page.on("request", self.request)
            page.on("requestfailed", self.request_failed)
            page.on("response", self.response)

    def context(self):
        return {"host":self.host, "stage":self.stage, "http_status":self.http_status,
                "authentication_required":self.authentication_required}

    def target(self, url):
        try:
            parsed = urlsplit(url)
            host = parsed.hostname if not parsed.username else None
        except ValueError:
            return
        self.host = host if host in HOSTS else None
        self.stage = "campus_sign_in" if (self.host in HOSTS[2:] or
            (self.host in HOSTS[:2] and parsed.path.startswith("/auth-"))) else "learn"

    def top_document(self, request):
        try:
            return request.is_navigation_request() and request.frame == self.page.main_frame
        except Exception:
            return False

    def request(self, request):
        if self.top_document(request):
            self.target(request.url)
            self.failure_code = None
            self.http_status = None

    def request_failed(self, request):
        if self.top_document(request):
            code = error_code(request.failure)
            if code:
                self.target(request.url)
                self.failure_code = code

    def response(self, response):
        try:
            host = urlsplit(response.url).hostname
            if host in HOSTS[:2] and response.status == 401:
                self.authentication_required = True
            if self.top_document(response.request):
                self.target(response.url)
                self.http_status = response.status
                if response.status >= 400:
                    self.failure_code = "HTTP_ERROR"
        except Exception:
            pass  # Optional diagnostics cannot break a successful navigation.

    def check(self):
        if self.failure_code:
            if self.failure_code == "HTTP_ERROR" and self.http_status == 401:
                raise LoginRequired(**self.context())
            raise SchoolNetworkError(self.failure_code, **self.context())

    def navigate(self, url):
        self.target(url)
        self.failure_code = None
        self.http_status = None
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        except Exception as error:
            self.check()
            code = error_code(error)
            if code:
                raise SchoolNetworkError(code, **self.context()) from None
            if "ERR_ABORTED" not in str(error):
                raise SchoolPageNotReady(**self.context()) from None
        self.check()


def observe(page):
    observer = getattr(page, "_uoe_navigation", None)
    if observer is None:
        observer = Navigation(page)
        page._uoe_navigation = observer
    return observer
