"""Shared worker exceptions and strictly bounded, credential-free diagnostics."""

HOSTS = ("learn.ed.ac.uk", "www.learn.ed.ac.uk", "idp.ed.ac.uk", "auth.ed.ac.uk",
         "login.ed.ac.uk", "login.microsoftonline.com")
NETWORK_CODES = ("NETWORK_TIMEOUT", "NETWORK_DNS", "NETWORK_CONNECTION", "TLS_ERROR", "HTTP_ERROR")
FAILURE_CODES = (*NETWORK_CODES, "LOGIN_REQUIRED", "PAGE_NOT_READY")


def diagnostic(code, *, host=None, stage="learn", http_status=None, authentication_required=False):
    if code not in FAILURE_CODES:
        raise ValueError("Unsupported school failure code.")
    value = {"code":code, "stage":stage if stage in ("learn", "campus_sign_in") else "learn",
             "automatic_retry":False,
             "recovery_action":"sign_in" if code == "LOGIN_REQUIRED" else
                               "check_connection" if code in NETWORK_CODES else "retry_once"}
    if host in HOSTS:
        value["target_host"] = host
    if isinstance(http_status, int) and 100 <= http_status <= 599:
        value["http_status"] = http_status
    if authentication_required:
        value["authentication_required"] = True
    return value


class LoginRequired(Exception):
    def __init__(self, **context):
        self.failure = diagnostic("LOGIN_REQUIRED", **context)
        super().__init__("Campus sign-in is required.")


class CourseUnavailable(Exception):
    pass


class SchoolPageNotReady(Exception):
    def __init__(self, **context):
        self.failure = diagnostic("PAGE_NOT_READY", **context)
        super().__init__("Supported school content was not ready.")


class SchoolNetworkError(Exception):
    def __init__(self, code="NETWORK_CONNECTION", **context):
        if code not in NETWORK_CODES:
            raise ValueError("Unsupported network failure code.")
        self.failure = diagnostic(code, **context)
        super().__init__("The school connection could not be completed.")


class BrowserBusy(Exception):
    pass
