"""Read the observed teaching archive form; never follow its credential links.

This adapter is limited to the two teaching groups documented in the supplied
handout. HTTP requires explicit consent on each saved acquisition request.
"""
from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import httpx

from .nmr_client import LEGACY_ORIGIN, LEGACY_PATH, NmrError, _bounded_response, _status, date_range, check_cancel

GROUPS = ("3OR", "2OR")


def archive_url(value, group):
    """A verified data link is different from a credential-bearing CGI link."""
    if group not in GROUPS or not isinstance(value, str):
        raise NmrError("SCOPE_MISMATCH", "Select a supported teaching archive group.")
    p = urlsplit(urljoin(LEGACY_ORIGIN + LEGACY_PATH, value))
    parts = unquote(p.path).split("/")
    if (p.scheme != "http" or p.hostname != "nmr-server.chem.ed.ac.uk"
            or p.port not in (None, 80) or p.username or p.password or p.query or p.fragment
            or len(parts) != 5 or parts[1] not in ("archive", "backup") or parts[2] != group
            or not parts[-1].endswith(".zip")
            or any(not x or x in (".", "..") or any(c in x for c in '\\<>:"|?*')
                   or any(ord(c) < 32 for c in x) for x in parts[1:])
            or "%" in p.path):
        raise NmrError("UNSAFE_DATA_LINK", "The old archive returned an unsupported data link; it was not followed.")
    return LEGACY_ORIGIN + p.path


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row, self.cell = [], None
        elif tag == "td" and self.row is not None:
            self.cell = {"text": [], "links": []}
            self.row.append(self.cell)
        elif tag == "a" and self.cell is not None:
            self.cell["links"].append(dict(attrs).get("href", ""))

    def handle_data(self, data):
        if self.cell is not None: self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "td": self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row, self.cell = None, None


def parse_results(html, sample, group, source="archive"):
    if not re.fullmatch(r"[0-9]{4}", sample) or group not in GROUPS or source not in ("archive", "backup"):
        raise ValueError("Use a four-digit sample, a supported teaching group and archive/backup.")
    if "Search Results" not in html or "Searched" not in html:
        code = "AUTH_REQUIRED" if re.search(r"(?i)(password|access denied|not authorised)", html) else "UNEXPECTED_RESPONSE"
        raise NmrError(code, "The archive did not return an authenticated search result. Preserve the request and check the connection.")
    parser = _Rows()
    parser.feed(html)
    candidates = []
    for row in parser.rows:
        has_zip = any(urlsplit(link).path.endswith(".zip") for cell in row for link in cell["links"])
        if not has_zip: continue
        if len(row) != 7 or not any(urlsplit(x).path.endswith(".zip") for x in row[2]["links"]):
            raise NmrError("UNSUPPORTED_LAYOUT", "The old archive's result layout changed; no empty result was assumed.")
        values = ["".join(c["text"]).strip() for c in row]
        if values[0] != group or not re.search(r"(?<![0-9])" + sample + r"(?![0-9])", values[2]):
            raise NmrError("FILTER_MISMATCH", "The archive returned a different sample or group; results were withheld.")
        links = [x for x in row[2]["links"] if urlsplit(x).path.endswith(".zip")]
        if len(links) != 1: raise NmrError("UNEXPECTED_RESPONSE", "Archive data selection is ambiguous.")
        url = archive_url(links[0], group)
        path = urlsplit(url).path.split("/")
        if path[1] != source or path[3] != values[1]:
            raise NmrError("SCOPE_MISMATCH", "Archive source or ownership changed; results were withheld.")
        experiments = set()
        for link in row[4]["links"]:
            query = parse_qs(urlsplit(link).query)
            if query.get("action") == ["ShowGraph"] and re.fullmatch(r"[0-9]{1,8}", query.get("number", [""])[0]):
                experiments.add(query["number"][0])
        if len(experiments) != 1:
            raise NmrError("UNSUPPORTED_LAYOUT", "This archive row does not identify one verifiable experiment.")
        try: measured = datetime.strptime(values[3], "%d-%m-%y").date().isoformat()
        except ValueError: raise NmrError("UNEXPECTED_RESPONSE", "Archive acquisition date is unrecognised.") from None
        candidates.append({"dataset_name": path[4][:-4], "experiment_number": experiments.pop(),
                           "sample": values[2][:120], "group": group, "user": values[1][:128],
                           "acquired_on": measured, "parameter_set": values[4][:128],
                           "instrument": values[5][:128], "title": values[6][:500],
                           "download_url": url, "parent_components": path[2:4], "archive": source})
        if len(candidates) > 50:
            raise NmrError("SELECTION_TOO_LARGE", "More than 50 matches. Ask for the experiment date to narrow the request.")
    return candidates


class LegacyClient:
    def __init__(self, session, *, allow_insecure_http=False, client=None):
        import time
        if not allow_insecure_http:
            raise NmrError("CONSENT_REQUIRED", "Ask permission before sending the course group credential over unencrypted HTTP.")
        if (not session or session.get("group") not in GROUPS or not session.get("password")
                or session.get("expires_at", 0) <= time.time()):
            raise NmrError("AUTH_REQUIRED", "Enter the old teaching-group credential in the protected plugin connection panel, then resume.")
        self.session = session
        self.client = client or httpx.Client(timeout=httpx.Timeout(25, connect=8), follow_redirects=False)
        self.owned = client is None

    def __enter__(self): return self
    def __exit__(self, *_):
        if self.owned: self.client.close()

    def search(self, sample, *, start_date=None, end_date=None, source="archive"):
        if not isinstance(sample, str) or not re.fullmatch(r"[0-9]{4}", sample):
            raise ValueError("Use the four-digit sample number as text, including leading zeros.")
        if source not in ("archive", "backup"): raise ValueError("Select archive or backup.")
        date_range(start_date, end_date)
        start, end = start_date or "2015-01-01", end_date or date.today().isoformat()
        body = {"action": "ListSearch", "source": source, "group": self.session["group"],
                "password": self.session["password"], "user": "", "sampleName": sample,
                "experimentName": "", "title": "", "spectrometer": "", "comments": "",
                "dateFrom": date.fromisoformat(start).strftime("%d-%m-%y"),
                "dateTo": date.fromisoformat(end).strftime("%d-%m-%y")}
        try:
            with self.client.stream("POST", LEGACY_ORIGIN + LEGACY_PATH, data=body, follow_redirects=False) as response:
                _status(response)
                html = _bounded_response(response, 2*1024*1024).decode("iso-8859-1")
            rows = parse_results(html, sample, self.session["group"], source)
            if any(not start <= row["acquired_on"] <= end for row in rows):
                raise NmrError("FILTER_MISMATCH", "Archive dates fall outside the requested interval.")
            return rows
        except httpx.HTTPError:
            raise NmrError("NETWORK_UNAVAILABLE", "The teaching archive is unreachable. Check campus network/VPN and resume.") from None

    def download(self, observed_url, destination, max_bytes, *, cancel_event=None):
        import time
        url = archive_url(observed_url, self.session["group"])
        deadline = time.monotonic() + 120
        check_cancel(cancel_event, deadline)
        try:
            with self.client.stream("GET", url, follow_redirects=False) as response:
                _status(response)
                length = response.headers.get("content-length")
                if length and (not length.isdigit() or int(length) > max_bytes):
                    raise NmrError("DOWNLOAD_TOO_LARGE", "NMR data exceeds the selected byte budget.")
                total = 0
                with destination.open("xb") as output:
                    for chunk in response.iter_bytes(65536):
                        check_cancel(cancel_event, deadline)
                        total += len(chunk)
                        if total > max_bytes: raise NmrError("DOWNLOAD_TOO_LARGE", "NMR data exceeds the selected byte budget.")
                        output.write(chunk)
            check_cancel(cancel_event, deadline)
            return total
        except httpx.HTTPError:
            raise NmrError("TRANSFER_FAILED", "NMR transfer did not finish. No verified download has been recorded.") from None
