"""Synthetic legacy teaching-archive form, scope and transfer checks."""
from contextlib import ExitStack
import html
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest

from edinburgh_study_agent.nmr_client import LEGACY_ORIGIN, LEGACY_PATH, NmrError
from edinburgh_study_agent.nmr_legacy import GROUPS, LegacyClient, archive_url, parse_results


NOW = 1_800_000_000.0
PASSWORD = "SYNTHETIC_LEGACY_SECRET"
USER = "SyntheticUser"
SAMPLE = "0042"
DATASET = "Synthetic_0042"


def saved_session(group="3OR", **overrides):
    return {"provider": "legacy", "group": group, "password": PASSWORD,
            "expires_at": NOW + 3600, "insecure_http_approved": True, **overrides}


def data_link(group="3OR", source="archive", owner=USER, dataset=DATASET):
    return f"/{source}/{group}/{owner}/{dataset}.zip"


def result_row(*, group="3OR", source="archive", owner=USER, sample=SAMPLE,
               dataset=DATASET, measured="15-09-26", exp="10", link=None, extra_links=""):
    raw_url = data_link(group, source, owner, dataset) if link is None else link
    credential_graph = (
        f"{LEGACY_PATH}?action=ShowGraph&number={exp}&password={PASSWORD}"
        f"&group={group}&user={owner}"
    )
    return (
        "<tr>"
        f"<td>{html.escape(group)}</td><td>{html.escape(owner)}</td>"
        f'<td><a href="{html.escape(raw_url, quote=True)}">{html.escape(sample)}</a>{extra_links}</td>'
        f"<td>{html.escape(measured)}</td>"
        f'<td><a href="{html.escape(credential_graph, quote=True)}">Synthetic 1H</a></td>'
        "<td>Synthetic400</td><td>Teaching sample, synthetic fixture only</td>"
        "</tr>"
    )


def search_page(*rows):
    return "<html><h2>Search Results</h2><p>Searched teaching archive</p><table>" + "".join(rows) + "</table></html>"


def assert_error(code, operation):
    with pytest.raises(NmrError) as caught:
        operation()
    assert caught.value.code == code
    assert PASSWORD not in str(caught.value)
    return caught.value


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: NOW)


@pytest.fixture
def transport_client():
    with ExitStack() as stack:
        def make(handler, *, group="3OR", consent=True, session=None):
            seen = []

            def dispatch(request):
                seen.append(request)
                return handler(request)

            http = stack.enter_context(httpx.Client(transport=httpx.MockTransport(dispatch)))
            api = LegacyClient(saved_session(group) if session is None else session,
                               allow_insecure_http=consent, client=http)
            return api, seen

        yield make


@pytest.mark.parametrize("group", ["3OR", "2OR"])
@pytest.mark.parametrize("source", ["archive", "backup"])
def test_parse_observed_seven_column_archive_and_backup_rows(group, source):
    rows = parse_results(search_page(result_row(group=group, source=source)), SAMPLE, group, source)
    assert GROUPS == ("3OR", "2OR")
    assert rows == [{
        "dataset_name": DATASET, "experiment_number": "10", "sample": SAMPLE,
        "group": group, "user": USER, "acquired_on": "2026-09-15",
        "parameter_set": "Synthetic 1H", "instrument": "Synthetic400",
        "title": "Teaching sample, synthetic fixture only",
        "download_url": LEGACY_ORIGIN + data_link(group, source),
        "parent_components": [group, USER], "archive": source,
    }]
    assert PASSWORD not in json.dumps(rows)
    assert "ShowGraph" not in json.dumps(rows)


@pytest.mark.parametrize("rendered", ["0042", "Synthetic_0042_A", "0042-1H"])
def test_four_digit_sample_token_preserves_leading_zeros(rendered):
    result = parse_results(search_page(result_row(sample=rendered)), "0042", "3OR")
    assert result[0]["sample"] == rendered


@pytest.mark.parametrize("rendered", ["42", "10042", "00420", "9999"])
def test_different_or_embedded_longer_sample_number_is_withheld(rendered):
    assert_error("FILTER_MISMATCH", lambda: parse_results(
        search_page(result_row(sample=rendered)), SAMPLE, "3OR",
    ))


def test_wrong_result_group_is_withheld():
    assert_error("FILTER_MISMATCH", lambda: parse_results(
        search_page(result_row(group="2OR")), SAMPLE, "3OR",
    ))


@pytest.mark.parametrize("link,source", [
    (data_link(owner="DifferentUser"), "archive"),
    (data_link(source="backup"), "archive"),
])
def test_zip_link_must_match_observed_owner_and_archive_source(link, source):
    assert_error("SCOPE_MISMATCH", lambda: parse_results(
        search_page(result_row(link=link)), SAMPLE, "3OR", source,
    ))


@pytest.mark.parametrize("link", [
    "https://outside.invalid/archive/3OR/SyntheticUser/Synthetic_0042.zip",
    "http://nmr-server.chem.ed.ac.uk:81/archive/3OR/SyntheticUser/Synthetic_0042.zip",
    "http://SyntheticUser:secret@nmr-server.chem.ed.ac.uk/archive/3OR/SyntheticUser/Synthetic_0042.zip",
    "/archive/2OR/SyntheticUser/Synthetic_0042.zip",
    "/archive/3OR/SyntheticUser/../Synthetic_0042.zip",
    "/archive/3OR/SyntheticUser/%2e%2e.zip",
    "/archive/3OR/SyntheticUser/Synthetic_0042.zip?password=SYNTHETIC_LEGACY_SECRET",
    "/archive/3OR/SyntheticUser/Synthetic_0042.zip#fragment",
    "/cgi-bin/nmrstation.pl?action=Download&password=SYNTHETIC_LEGACY_SECRET",
    "//outside.invalid/archive/3OR/SyntheticUser/Synthetic_0042.zip",
    "/archive/3OR/SyntheticUser/subdir/Synthetic_0042.zip",
])
def test_archive_url_rejects_credential_links_and_scope_escapes(link):
    assert_error("UNSAFE_DATA_LINK", lambda: archive_url(link, "3OR"))


def test_parser_never_returns_password_link_as_data():
    page = search_page(result_row(link=data_link() + "?password=" + PASSWORD))
    assert_error("UNSAFE_DATA_LINK", lambda: parse_results(page, SAMPLE, "3OR"))


def test_multiple_raw_links_are_ambiguous():
    extra = '<a href="/archive/3OR/SyntheticUser/Other.zip">Other</a>'
    assert_error("UNEXPECTED_RESPONSE", lambda: parse_results(
        search_page(result_row(extra_links=extra)), SAMPLE, "3OR",
    ))


@pytest.mark.parametrize("exp", ["", "../10", "not-an-experiment"])
def test_parser_requires_one_numeric_observed_experiment(exp):
    assert_error("UNSUPPORTED_LAYOUT", lambda: parse_results(
        search_page(result_row(exp=exp)), SAMPLE, "3OR",
    ))


def test_parser_rejects_two_different_experiment_links():
    row = result_row().replace("</td><td>Synthetic400", '<a href="?action=ShowGraph&amp;number=11">Other</a></td><td>Synthetic400')
    assert_error("UNSUPPORTED_LAYOUT", lambda: parse_results(search_page(row), SAMPLE, "3OR"))


def test_parser_rejects_invalid_acquisition_date():
    assert_error("UNEXPECTED_RESPONSE", lambda: parse_results(
        search_page(result_row(measured="31-02-26")), SAMPLE, "3OR",
    ))


def test_empty_authenticated_result_is_distinct_from_login_page():
    assert parse_results(search_page(), SAMPLE, "3OR") == []
    assert_error("AUTH_REQUIRED", lambda: parse_results(
        "<html>Access denied. Enter group password.</html>", SAMPLE, "3OR",
    ))
    assert_error("UNEXPECTED_RESPONSE", lambda: parse_results(
        "<html>Maintenance</html>", SAMPLE, "3OR",
    ))


def test_parser_bounds_match_count():
    assert len(parse_results(search_page(*[result_row()] * 50), SAMPLE, "3OR")) == 50
    assert_error("SELECTION_TOO_LARGE", lambda: parse_results(
        search_page(*[result_row()] * 51), SAMPLE, "3OR",
    ))


@pytest.mark.parametrize("consent", [False, None])
def test_http_requires_explicit_consent(transport_client, consent):
    assert_error("CONSENT_REQUIRED", lambda: transport_client(
        lambda request: pytest.fail("No HTTP request should be sent without consent"), consent=consent,
    ))


@pytest.mark.parametrize("session", [
    {}, saved_session(group="UNVERIFIED"), saved_session(password=""), saved_session(expires_at=NOW),
])
def test_client_requires_unexpired_supported_group_session(transport_client, session):
    assert_error("AUTH_REQUIRED", lambda: transport_client(
        lambda request: pytest.fail("No HTTP request should be sent without authentication"), session=session,
    ))


@pytest.mark.parametrize("group", ["3OR", "2OR"])
def test_search_sends_credential_in_post_body_and_observed_date_format(transport_client, group):
    api, seen = transport_client(lambda request: httpx.Response(
        200, text=search_page(result_row(group=group, source="backup")),
    ), group=group)
    result = api.search(SAMPLE, start_date="2026-09-15", end_date="2026-09-16", source="backup")
    assert len(result) == 1
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == LEGACY_ORIGIN + LEGACY_PATH
    assert request.url.query == b""
    assert PASSWORD not in str(request.url)
    assert "authorization" not in request.headers
    assert parse_qs(request.content.decode(), keep_blank_values=True) == {
        "action": ["ListSearch"], "source": ["backup"], "group": [group],
        "password": [PASSWORD], "user": [""], "sampleName": ["0042"],
        "experimentName": [""], "title": [""], "spectrometer": [""], "comments": [""],
        "dateFrom": ["15-09-26"], "dateTo": ["16-09-26"],
    }
    assert PASSWORD not in json.dumps(result)


@pytest.mark.parametrize("sample", [42, "42", "00042", "00.2", "0042\n"])
def test_search_requires_four_digit_text_before_http(transport_client, sample):
    api, seen = transport_client(lambda request: pytest.fail("Invalid sample reached HTTP"))
    with pytest.raises(ValueError):
        api.search(sample)
    assert seen == []


@pytest.mark.parametrize("kwargs", [
    {"source": "unobserved"},
    {"start_date": "2026-09-16", "end_date": "2026-09-15"},
    {"start_date": "2026-02-30"},
])
def test_invalid_archive_or_date_is_rejected_before_http(transport_client, kwargs):
    api, seen = transport_client(lambda request: pytest.fail("Invalid bounds reached HTTP"))
    with pytest.raises(ValueError):
        api.search(SAMPLE, **kwargs)
    assert seen == []


@pytest.mark.parametrize("measured", ["14-09-26", "17-09-26"])
def test_search_withholds_rows_outside_requested_dates(transport_client, measured):
    api, _ = transport_client(lambda request: httpx.Response(200, text=search_page(result_row(measured=measured))))
    assert_error("FILTER_MISMATCH", lambda: api.search(
        SAMPLE, start_date="2026-09-15", end_date="2026-09-16",
    ))


@pytest.mark.parametrize("status,code", [
    (302, "UNEXPECTED_REDIRECT"), (307, "UNEXPECTED_REDIRECT"),
    (403, "AUTH_REQUIRED"), (500, "SERVICE_ERROR"),
])
def test_search_errors_never_forward_password_or_retry(transport_client, status, code):
    api, seen = transport_client(lambda request: httpx.Response(
        status, text=PASSWORD, headers={"Location": "https://outside.invalid/?password=" + PASSWORD},
    ))
    assert_error(code, lambda: api.search(SAMPLE))
    assert len(seen) == 1
    assert seen[0].url.host == "nmr-server.chem.ed.ac.uk"


def test_oversized_html_response_is_bounded_before_parsing(transport_client):
    api, seen = transport_client(lambda request: httpx.Response(
        200, content=b"x", headers={"Content-Length": str(2 * 1024 * 1024 + 1)},
    ))
    assert_error("RESPONSE_TOO_LARGE", lambda: api.search(SAMPLE))
    assert len(seen) == 1


def test_search_timeout_is_sanitized(transport_client):
    def fail(request):
        raise httpx.ConnectTimeout(PASSWORD, request=request)

    api, seen = transport_client(fail)
    assert_error("NETWORK_UNAVAILABLE", lambda: api.search(SAMPLE))
    assert len(seen) == 1


def test_download_only_follows_clean_observed_zip_url(transport_client, tmp_path):
    original = b"PK\x03\x04synthetic archive bytes checked separately by archive verifier"
    api, seen = transport_client(lambda request: httpx.Response(200, content=original))
    destination = tmp_path / "original.zip"
    assert api.download(data_link(), destination, len(original)) == len(original)
    assert destination.read_bytes() == original
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == LEGACY_ORIGIN + data_link()
    assert seen[0].url.query == b""
    assert seen[0].content == b""
    assert PASSWORD not in str(seen[0].url)
    assert PASSWORD not in str(seen[0].headers)


def test_download_rejects_credential_url_before_request(transport_client, tmp_path):
    api, seen = transport_client(lambda request: pytest.fail("Credential-bearing link was followed"))
    assert_error("UNSAFE_DATA_LINK", lambda: api.download(
        data_link() + "?password=" + PASSWORD, tmp_path / "original.zip", 1024,
    ))
    assert seen == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("announced", [True, False])
def test_download_size_bound_does_not_retry(transport_client, tmp_path, announced):
    def respond(request):
        response = httpx.Response(200, content=b"x" * 1025)
        if not announced:
            del response.headers["content-length"]
        return response

    api, seen = transport_client(respond)
    assert_error("DOWNLOAD_TOO_LARGE", lambda: api.download(data_link(), tmp_path / "raw.zip", 1024))
    assert len(seen) == 1
    if announced:
        assert list(tmp_path.iterdir()) == []


def test_download_redirect_creates_no_file_and_forwards_no_credential(transport_client, tmp_path):
    api, seen = transport_client(lambda request: httpx.Response(
        307, headers={"Location": LEGACY_ORIGIN + LEGACY_PATH + "?password=" + PASSWORD},
    ))
    assert_error("UNEXPECTED_REDIRECT", lambda: api.download(data_link(), tmp_path / "raw.zip", 1024))
    assert len(seen) == 1
    assert list(tmp_path.iterdir()) == []


def test_download_preserves_an_existing_file(transport_client, tmp_path):
    api, _ = transport_client(lambda request: httpx.Response(200, content=b"new-content"))
    path = tmp_path / "original.zip"
    path.write_bytes(b"existing-original")
    with pytest.raises(FileExistsError):
        api.download(data_link(), path, 1024)
    assert path.read_bytes() == b"existing-original"


def test_download_timeout_is_sanitized_and_not_retried(transport_client, tmp_path):
    def fail(request):
        raise httpx.ReadTimeout(PASSWORD, request=request)

    api, seen = transport_client(fail)
    assert_error("TRANSFER_FAILED", lambda: api.download(data_link(), tmp_path / "raw.zip", 1024))
    assert len(seen) == 1
