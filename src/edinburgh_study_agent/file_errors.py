"""Bounded file failures; messages and recovery never contain transfer URLs."""
FILE_FAILURES = {
    "UNSUPPORTED_CONTAINER": ("This entry is a page, not a directly downloadable file. Read the page and choose an observed attachment.", "read_page"),
    "ATTACHMENT_AMBIGUOUS": ("More than one visible attachment preview was found. No file was selected.", "choose_attachment"),
    "ATTACHMENT_MISMATCH": ("The current page or preview does not match the requested resource. No file was selected.", "refresh_resource"),
    "PREVIEW_NOT_READY": ("A unique visible original-file preview did not become ready.", "refresh_resource"),
    "UNSUPPORTED_FILE": ("The attachment does not have a supported original-file name.", "read_page"),
    "DOWNLOAD_HTTP_ERROR": ("The file server returned an unsuccessful HTTP status.", "check_connection"),
    "DOWNLOAD_NETWORK_ERROR": ("The file transfer could not reach the server.", "check_connection"),
    "FILE_VERIFICATION_FAILED": ("The transferred file failed verification; no successful file was recorded.", "inspect_source"),
    "FILE_SAVE_FAILED": ("The file could not be saved or verified; check local storage.", "check_storage"),
    "DOWNLOAD_FAILED": ("The file operation failed; inspect its source before another attempt.", "inspect_source"),
}


class FileDownloadError(ValueError):
    def __init__(self, code, message=None, *, http_status=None, candidates=()):
        default, recovery = FILE_FAILURES[code]
        super().__init__(message or default)
        self.code = code
        self.recovery_action = recovery
        self.http_status = http_status
        self.candidates = list(candidates)[:5]

    def fields(self):
        value = {"code": self.code, "error": str(self),
                 "recovery_action": self.recovery_action, "automatic_retry": False}
        if isinstance(self.http_status, int) and 100 <= self.http_status <= 599:
            value["http_status"] = self.http_status
        if self.candidates:
            value["candidates"] = self.candidates
        return value
