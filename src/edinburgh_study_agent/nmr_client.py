"""Bounded clients for the University's NMR archives, without instrument writes.

The NOMAD protocol is independently implemented from its public API contract.
Passwords, tokens, response bodies and credential-bearing links never enter errors.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import math
import re
import time

import httpx

NOMAD_ORIGIN = "https://nmr-nomad.chem.ed.ac.uk"
LEGACY_ORIGIN = "http://nmr-server.chem.ed.ac.uk"
LEGACY_PATH = "/cgi-bin/nmrstation.pl"
MAX_JSON = 2 * 1024 * 1024


class NmrError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def check_cancel(event=None, deadline=None):
    if event is not None and event.is_set():
        raise NmrError("CANCELLED", "NMR acquisition cancelled. Resume the saved request only when requested.")
    if deadline is not None and time.monotonic() > deadline:
        raise NmrError("TIME_LIMIT", "NMR transfer exceeded its time budget. No verified download was recorded.")


def literal(value: str, label: str = "sample", maximum: int = 120) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be nonempty text within {maximum} characters.")
    if any(ord(c) < 32 for c in value) or "\x7f" in value:
        raise ValueError(f"{label} cannot contain control characters.")
    return value.strip()


def date_range(start: str | None, end: str | None):
    from datetime import date
    for value in (start, end):
        if value is not None and (date.fromisoformat(value).isoformat() != value):
            raise ValueError("Dates must be YYYY-MM-DD.")
    if start and end and start > end:
        raise ValueError("start_date must not follow end_date.")
    return start, end


def _bounded_response(response: httpx.Response, limit: int):
    deadline = time.monotonic() + 60
    length = response.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > limit):
        raise NmrError("RESPONSE_TOO_LARGE", "The NMR response exceeds the configured limit.")
    chunks, size = [], 0
    for chunk in response.iter_bytes(64 * 1024):
        check_cancel(deadline=deadline)
        size += len(chunk)
        if size > limit:
            raise NmrError("RESPONSE_TOO_LARGE", "The NMR response exceeds the configured limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _status(response, *, login=False):
    if 300 <= response.status_code < 400:
        raise NmrError("UNEXPECTED_REDIRECT", "The NMR service redirected the request; no credentials were forwarded.")
    if (login and response.status_code in (400, 401, 403)) or response.status_code in (401, 403):
        raise NmrError("AUTH_REQUIRED", "NMR authentication is missing, expired or rejected. Ask for secure sign-in, then resume this request.")
    if response.status_code == 404:
        raise NmrError("ENDPOINT_UNAVAILABLE", "The deployed NMR service does not provide this endpoint.")
    if response.status_code >= 400:
        raise NmrError("SERVICE_ERROR", "The NMR service could not complete the request. Preserve the selection; do not retry downloads blindly.")


class NomadClient:
    def __init__(self, session: dict | None = None, *, client: httpx.Client | None = None):
        self.session = session or {}
        self.client = client or httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=False)
        self.owned = client is None

    def __enter__(self): return self

    def __exit__(self, *_):
        if self.owned: self.client.close()

    def _headers(self):
        if not self.session.get("token") or self.session.get("expires_at", 0) <= time.time():
            raise NmrError("AUTH_REQUIRED", "NOMAD needs secure sign-in. Keep the sample selection and continue after connecting.")
        return {"Authorization": "Bearer " + self.session["token"], "Accept": "application/json"}

    def _json(self, method: str, path: str, *, params=None, data=None, login=False):
        try:
            with self.client.stream(method, NOMAD_ORIGIN + path, params=params, json=data,
                                    headers={} if login else self._headers(), follow_redirects=False) as response:
                _status(response, login=login)
                raw = _bounded_response(response, MAX_JSON)
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise NmrError("UNEXPECTED_RESPONSE", "The NMR service returned an unsupported response; no results were assumed.") from None
        except httpx.HTTPError:
            raise NmrError("NETWORK_UNAVAILABLE", "NMR cannot be reached with normal certificate verification. Check campus network/VPN access and resume.") from None

    def login(self, username: str, password: str) -> dict:
        username = literal(username, "username", 128)
        if not isinstance(password, str) or not password or len(password) > 1024:
            raise ValueError("Enter the NMR password in the protected connection panel.")
        payload = self._json("POST", "/api/auth/login", data={"username": username, "password": password}, login=True)
        try:
            token = payload["token"]
            if not isinstance(token, str) or len(token) > 16384 or len(token.split(".")) != 3:
                raise ValueError()
            part = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            user_id = claims["_id"]
            # Claims are accepted only from this HTTPS login response, never a caller-supplied JWT.
            if not isinstance(user_id, str) or not re.fullmatch(r"[a-fA-F0-9]{24}", user_id):
                raise ValueError()
            expiry, duration = float(claims["exp"]), float(payload["expiresIn"])
            if not math.isfinite(expiry) or not math.isfinite(duration):
                raise ValueError()
            expires = min(expiry, time.time() + duration)
            if expires <= time.time() or expires > time.time() + 366 * 86400:
                raise ValueError()
            self.session = {"provider": "nomad", "token": token, "user_id": user_id,
                            "username": literal(payload["username"], "username", 128),
                            "group": str(payload.get("groupName", ""))[:128], "expires_at": expires}
            return self.session
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise NmrError("UNEXPECTED_RESPONSE", "NOMAD login did not supply a valid bounded session.") from None

    def search(self, sample: str, *, page=1, limit=10, start_date=None, end_date=None, shared=False):
        self._headers()
        sample = literal(sample)
        date_range(start_date, end_date)
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100:
            raise ValueError("page must be 1..100.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("limit must be 1..20.")
        params = {"dataType": "auto", "title": re.escape(sample), "currentPage": page, "pageSize": limit}
        if not shared: params["userId"] = self.session["user_id"]
        if start_date or end_date:
            params["dateRange"] = (start_date or "1970-01-01") + "," + (end_date or datetime.now(timezone.utc).date().isoformat())
        value = self._json("GET", "/api/search/experiments", params=params)
        if not isinstance(value, dict) or not isinstance(value.get("data"), list) or len(value["data"]) > limit:
            raise NmrError("UNEXPECTED_RESPONSE", "NOMAD archive search has changed shape. Keep the request for adapter review.")
        if type(value.get("total")) is not int or value["total"] < 0:
            raise NmrError("UNEXPECTED_RESPONSE", "NOMAD archive pagination could not be verified.")
        rows = []
        for row in value["data"]:
            if not isinstance(row, dict) or not isinstance(row.get("user"), dict):
                raise NmrError("UNEXPECTED_RESPONSE", "NOMAD archive ownership is missing.")
            if not shared and row["user"].get("id") != self.session["user_id"]:
                raise NmrError("SCOPE_MISMATCH", "NOMAD returned data outside the requested personal scope; results were withheld.")
            title = str(row.get("title", ""))[:1000]
            if sample.casefold() not in title.casefold():
                raise NmrError("FILTER_MISMATCH", "NOMAD did not preserve the requested literal sample filter.")
            dataset = literal(row.get("datasetName"), "dataset name", 200)
            if any(row.get(key) is not None and not isinstance(row[key], dict) for key in ("group", "instrument")):
                raise NmrError("UNEXPECTED_RESPONSE", "NOMAD archive metadata has changed shape.")
            rows.append({"dataset_name": dataset, "title": title, "submitted_at": row.get("submittedAt"),
                         "user": str(row["user"].get("username", ""))[:128],
                         "group": str((row.get("group") or {}).get("name", ""))[:128],
                         "instrument": str((row.get("instrument") or {}).get("name", ""))[:128]})
        return {"datasets": rows, "page": page, "limit": limit, "total_datasets": value["total"],
                "has_more": page * limit < value["total"], "adapter": "nomad_frontend_archive",
                "coverage": "bounded_authenticated_sample_search"}

    def experiments(self, dataset: str, *, shared=False):
        self._headers()
        dataset = literal(dataset, "dataset name", 200)
        if "," in dataset: raise ValueError("Choose one observed dataset.")
        params = {"datasetName": dataset, "offset": 0, "limit": 101}
        if not shared: params["userId"] = self.session["user_id"]
        value = self._json("GET", "/api/v2/auto-experiments", params=params)
        if not isinstance(value, list) or len(value) > 100:
            raise NmrError("SELECTION_TOO_LARGE", "Choose a dataset containing at most 100 experiments.")
        rows = []
        for row in value:
            if not isinstance(row, dict) or row.get("datasetName") != dataset:
                raise NmrError("SCOPE_MISMATCH", "NOMAD returned a different dataset; results were withheld.")
            if not shared and row.get("user") != self.session["user_id"]:
                raise NmrError("SCOPE_MISMATCH", "NOMAD returned another user's experiment; results were withheld.")
            exp = str(row.get("expNo", ""))
            ident = row.get("id")
            if not re.fullmatch(r"[0-9]{1,8}", exp) or ident != dataset + "-" + exp:
                raise NmrError("UNEXPECTED_RESPONSE", "NOMAD experiment identity could not be verified.")
            rows.append({"experiment_id": ident, "dataset_name": dataset, "experiment_number": exp,
                         "title": str(row.get("title", ""))[:1000], "parameter_set": str(row.get("parameterSet", ""))[:128],
                         "solvent": str(row.get("solvent", ""))[:128], "submitted_at": row.get("submittedAt")})
        return rows

    def download(self, experiment_id: str, destination, max_bytes: int, *, cancel_event=None):
        ident = literal(experiment_id, "observed experiment ID", 256)
        if "," in ident: raise ValueError("Download one selected experiment per request.")
        deadline = time.monotonic() + 120
        check_cancel(cancel_event, deadline)
        try:
            with self.client.stream("POST", NOMAD_ORIGIN + "/api/v2/auto-experiments/download",
                                    params={"id": ident}, headers=self._headers(), follow_redirects=False) as response:
                _status(response)
                length = response.headers.get("content-length")
                if length and (not length.isdigit() or int(length) > max_bytes):
                    raise NmrError("DOWNLOAD_TOO_LARGE", "NMR data exceeds the selected download budget.")
                total = 0
                with destination.open("xb") as target:
                    for chunk in response.iter_bytes(64 * 1024):
                        check_cancel(cancel_event, deadline)
                        total += len(chunk)
                        if total > max_bytes:
                            raise NmrError("DOWNLOAD_TOO_LARGE", "NMR data exceeds the selected download budget.")
                        target.write(chunk)
            check_cancel(cancel_event, deadline)
            return total
        except httpx.HTTPError:
            raise NmrError("TRANSFER_FAILED", "NMR transfer did not finish. No verified download has been recorded.") from None
