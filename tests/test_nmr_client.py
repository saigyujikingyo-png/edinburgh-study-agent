"""Synthetic transport checks against the published NOMAD request/response shapes.

No account, campus connection or real sample data is used. Frontend archive
records contain nested owner/group/instrument objects; v2 records contain IDs.
"""
import base64
from contextlib import ExitStack
import io
import json
import zipfile

import httpx
import pytest

from edinburgh_study_agent import nmr_client
from edinburgh_study_agent.nmr_client import NOMAD_ORIGIN, NmrError, NomadClient


NOW = 1_800_000_000.0
USER_ID = "a" * 24
OTHER_USER_ID = "b" * 24
GROUP_ID = "c" * 24
INSTRUMENT_ID = "d" * 24
USERNAME = "synthetic-student"
DATASET = "2609011000-1-2-synthetic-student"
TITLE = "Synthetic sample 0042 || 1H Observe"
PASSWORD = "SYNTHETIC_PASSWORD_NOT_A_CREDENTIAL"


def token_for(**claims):
    payload = {"_id": USER_ID, "iat": NOW, "exp": NOW + 3600, **claims}
    part = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return "eyJhbGciOiJIUzI1NiJ9." + part + ".synthetic-signature"


def auth_payload(**overrides):
    return {
        "username": USERNAME,
        "accessLevel": "user",
        "manualAccess": False,
        "accountsAccess": False,
        "groupName": "Synthetic teaching group",
        "token": token_for(),
        "expiresIn": 3600,
        **overrides,
    }


def session(**overrides):
    return {
        "provider": "nomad", "token": token_for(), "user_id": USER_ID,
        "username": USERNAME, "group": "Synthetic teaching group",
        "expires_at": NOW + 3600, **overrides,
    }


def archive_row(**overrides):
    return {
        "datasetName": DATASET,
        "key": DATASET,
        "title": TITLE,
        "submittedAt": "2026-09-01T10:00:00.000Z",
        "solvent": "CDCl3",
        "user": {"id": USER_ID, "username": USERNAME},
        "group": {"id": GROUP_ID, "name": "Synthetic teaching group"},
        "instrument": {"id": INSTRUMENT_ID, "name": "Synthetic 400 MHz"},
        "exps": [{"key": "e" * 24, "datasetName": DATASET, "expNo": "10",
                  "title": TITLE, "parameterSet": "1H", "parameters": "NS,16"}],
        **overrides,
    }


def experiment(**overrides):
    return {
        "id": DATASET + "-10", "datasetName": DATASET, "expNo": "10",
        "parameterSet": "1H", "parameters": "NS,16", "title": TITLE,
        "instrument": INSTRUMENT_ID, "user": USER_ID, "group": GROUP_ID,
        "solvent": "CDCl3", "submittedAt": "2026-09-01T10:00:00.000Z",
        **overrides,
    }


def archive_payload(rows=None, total=None):
    rows = [archive_row()] if rows is None else rows
    return {"data": rows, "total": len(rows) if total is None else total,
            "totalExps": sum(len(row.get("exps", [])) for row in rows)}


def raw_zip():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(DATASET + "/10/acqus", "##$NUC1= <1H>\n")
        archive.writestr(DATASET + "/10/fid", b"\x00\x01\x02\x03")
    return stream.getvalue()


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(nmr_client.time, "time", lambda: NOW)


@pytest.fixture
def transport_client():
    with ExitStack() as stack:
        def make(handler, *, saved_session=None):
            seen = []

            def dispatch(request):
                seen.append(request)
                return handler(request)

            http = stack.enter_context(httpx.Client(transport=httpx.MockTransport(dispatch)))
            api = NomadClient(session() if saved_session is None else saved_session, client=http)
            return api, seen

        yield make


def assert_error(code, operation):
    with pytest.raises(NmrError) as caught:
        operation()
    assert caught.value.code == code
    return caught.value


@pytest.mark.parametrize("expires_in,jwt_seconds,expected_seconds", [
    (3600, 7200, 3600), (7200, 1200, 1200),
])
def test_login_uses_https_json_and_conservative_expiry(
    transport_client, expires_in, jwt_seconds, expected_seconds,
):
    api, seen = transport_client(lambda request: httpx.Response(200, json=auth_payload(
        token=token_for(exp=NOW + jwt_seconds), expiresIn=expires_in,
    )), saved_session={})
    result = api.login(USERNAME, PASSWORD)
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == NOMAD_ORIGIN + "/api/auth/login"
    assert "authorization" not in request.headers
    assert json.loads(request.content) == {"username": USERNAME, "password": PASSWORD}
    assert result["user_id"] == USER_ID
    assert result["expires_at"] == NOW + expected_seconds
    assert result["username"] == USERNAME
    assert "password" not in result


@pytest.mark.parametrize("payload", [
    auth_payload(token="not-a-jwt"),
    auth_payload(token=token_for(_id="not-an-object-id")),
    auth_payload(token=token_for(exp=NOW - 1)),
    auth_payload(expiresIn=-1),
    auth_payload(expiresIn="not-seconds"),
    auth_payload(token=token_for(exp=float("nan"))),
    [],
])
def test_login_rejects_invalid_session_payload(transport_client, payload):
    api, seen = transport_client(lambda request: httpx.Response(200, json=payload), saved_session={})
    assert_error("UNEXPECTED_RESPONSE", lambda: api.login(USERNAME, PASSWORD))
    assert len(seen) == 1
    assert api.session == {}


@pytest.mark.parametrize("status", [400, 401, 403])
def test_rejected_login_is_actionable_and_does_not_echo_body(transport_client, status):
    api, seen = transport_client(
        lambda request: httpx.Response(status, json={"message": PASSWORD, "token": "DO_NOT_ECHO"}),
        saved_session={},
    )
    error = assert_error("AUTH_REQUIRED", lambda: api.login(USERNAME, PASSWORD))
    assert PASSWORD not in str(error)
    assert "DO_NOT_ECHO" not in str(error)
    assert len(seen) == 1


@pytest.mark.parametrize("operation", ["search", "experiments", "download"])
@pytest.mark.parametrize("saved", [{}, session(expires_at=NOW)])
def test_missing_or_expired_session_stops_before_http(transport_client, tmp_path, operation, saved):
    api, seen = transport_client(
        lambda request: pytest.fail("Authentication must be checked before sending a request"),
        saved_session=saved,
    )
    invoke = {
        "search": lambda: api.search("0042"),
        "experiments": lambda: api.experiments(DATASET),
        "download": lambda: api.download(DATASET + "-10", tmp_path / "raw.zip", 4096),
    }[operation]
    assert_error("AUTH_REQUIRED", invoke)
    assert seen == []


def test_search_preserves_leading_zero_own_scope_and_nested_labels(transport_client):
    api, seen = transport_client(lambda request: httpx.Response(200, json=archive_payload(total=3)))
    result = api.search("0042", page=1, limit=2,
                        start_date="2026-09-01", end_date="2026-09-16")
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/api/search/experiments"
    assert dict(request.url.params) == {
        "dataType": "auto", "title": "0042", "currentPage": "1", "pageSize": "2",
        "userId": USER_ID, "dateRange": "2026-09-01,2026-09-16",
    }
    assert request.headers["authorization"] == "Bearer " + api.session["token"]
    assert result["total_datasets"] == 3
    assert result["has_more"] is True
    assert result["datasets"] == [{
        "dataset_name": DATASET, "title": TITLE,
        "submitted_at": "2026-09-01T10:00:00.000Z", "user": USERNAME,
        "group": "Synthetic teaching group", "instrument": "Synthetic 400 MHz",
    }]


def test_search_escapes_sample_metacharacters(transport_client):
    sample = "0042 (A)+?"
    api, seen = transport_client(lambda request: httpx.Response(
        200, json=archive_payload([archive_row(title="Synthetic " + sample)]),
    ))
    assert len(api.search(sample)["datasets"]) == 1
    assert seen[0].url.params["title"] == r"0042\ \(A\)\+\?"


def test_personal_search_rejects_another_owner(transport_client):
    api, _ = transport_client(lambda request: httpx.Response(200, json=archive_payload([
        archive_row(user={"id": OTHER_USER_ID, "username": "different-student"}),
    ])))
    assert_error("SCOPE_MISMATCH", lambda: api.search("0042"))


def test_explicit_shared_search_retains_literal_sample_filter(transport_client):
    api, seen = transport_client(lambda request: httpx.Response(200, json=archive_payload([
        archive_row(user={"id": OTHER_USER_ID, "username": "shared-teaching-account"}),
    ])))
    result = api.search("0042", shared=True)
    assert "userId" not in seen[0].url.params
    assert seen[0].url.params["title"] == "0042"
    assert result["datasets"][0]["user"] == "shared-teaching-account"


def test_search_rejects_server_ignoring_sample_filter(transport_client):
    api, _ = transport_client(lambda request: httpx.Response(
        200, json=archive_payload([archive_row(title="Different sample 9999")]),
    ))
    assert_error("FILTER_MISMATCH", lambda: api.search("0042"))


@pytest.mark.parametrize("payload", [
    [], {"data": [], "total": True}, {"data": [], "total": -1},
    {"data": "not-an-array", "total": 0},
    archive_payload([archive_row(group="not-an-object")]),
    archive_payload([archive_row(instrument="not-an-object")]),
    archive_payload([archive_row(user="not-an-object")]),
])
def test_search_rejects_malformed_frontend_response(transport_client, payload):
    api, _ = transport_client(lambda request: httpx.Response(200, json=payload))
    assert_error("UNEXPECTED_RESPONSE", lambda: api.search("0042"))


def test_search_rejects_server_ignoring_page_limit(transport_client):
    api, _ = transport_client(lambda request: httpx.Response(200, json=archive_payload(
        [archive_row(), archive_row(datasetName=DATASET + "-other")],
    )))
    assert_error("UNEXPECTED_RESPONSE", lambda: api.search("0042", limit=1))


@pytest.mark.parametrize("kwargs", [
    {"page": 0}, {"page": True}, {"page": 101},
    {"limit": 0}, {"limit": True}, {"limit": 21},
    {"start_date": "2026-09-17", "end_date": "2026-09-16"},
    {"start_date": "2026-02-30"},
])
def test_invalid_search_bounds_never_reach_http(transport_client, kwargs):
    api, seen = transport_client(lambda request: pytest.fail("Invalid request reached HTTP"))
    with pytest.raises(ValueError):
        api.search("0042", **kwargs)
    assert not seen


def test_v2_experiments_use_user_id_and_exact_observed_identity(transport_client):
    api, seen = transport_client(lambda request: httpx.Response(200, json=[experiment()]))
    result = api.experiments(DATASET)
    assert seen[0].url.path == "/api/v2/auto-experiments"
    assert dict(seen[0].url.params) == {
        "datasetName": DATASET, "offset": "0", "limit": "101", "userId": USER_ID,
    }
    assert result[0]["experiment_id"] == DATASET + "-10"
    assert result[0]["experiment_number"] == "10"
    assert result[0]["solvent"] == "CDCl3"


@pytest.mark.parametrize("row,code", [
    (experiment(datasetName="another-dataset"), "SCOPE_MISMATCH"),
    (experiment(user=OTHER_USER_ID), "SCOPE_MISMATCH"),
    (experiment(id="e" * 24), "UNEXPECTED_RESPONSE"),
    (experiment(id=DATASET + "-11"), "UNEXPECTED_RESPONSE"),
    (experiment(expNo="../10"), "UNEXPECTED_RESPONSE"),
])
def test_v2_rejects_scope_and_identity_mismatch(transport_client, row, code):
    api, _ = transport_client(lambda request: httpx.Response(200, json=[row]))
    assert_error(code, lambda: api.experiments(DATASET))


def test_v2_rejects_experiment_count_over_budget(transport_client):
    api, _ = transport_client(lambda request: httpx.Response(200, json=[experiment()] * 101))
    assert_error("SELECTION_TOO_LARGE", lambda: api.experiments(DATASET))


@pytest.mark.parametrize("status,code", [
    (302, "UNEXPECTED_REDIRECT"), (401, "AUTH_REQUIRED"), (403, "AUTH_REQUIRED"),
    (404, "ENDPOINT_UNAVAILABLE"), (429, "SERVICE_ERROR"), (503, "SERVICE_ERROR"),
])
def test_response_errors_are_sanitized_and_not_retried(transport_client, status, code):
    api, seen = transport_client(lambda request: httpx.Response(
        status, text=PASSWORD, headers={"Location": "https://outside.invalid/private?token=SECRET"},
    ))
    error = assert_error(code, lambda: api.search("0042"))
    assert len(seen) == 1
    assert seen[0].url.host == "nmr-nomad.chem.ed.ac.uk"
    assert PASSWORD not in str(error)
    assert "SECRET" not in str(error)


def test_search_timeout_does_not_echo_transport_details(transport_client):
    def fail(request):
        raise httpx.ReadTimeout(PASSWORD, request=request)

    api, seen = transport_client(fail)
    error = assert_error("NETWORK_UNAVAILABLE", lambda: api.search("0042"))
    assert PASSWORD not in str(error)
    assert len(seen) == 1


@pytest.mark.parametrize("announced", [True, False])
def test_json_payload_budget_is_enforced_with_and_without_header(
    transport_client, monkeypatch, announced,
):
    monkeypatch.setattr(nmr_client, "MAX_JSON", 100)
    content = b"x" * 101

    def handler(request):
        response = httpx.Response(200, content=content)
        if not announced:
            del response.headers["content-length"]
        return response

    api, _ = transport_client(handler)
    assert_error("RESPONSE_TOO_LARGE", lambda: api.search("0042"))


def test_download_posts_one_id_and_preserves_binary_bytes(transport_client, tmp_path):
    binary = raw_zip()
    api, seen = transport_client(lambda request: httpx.Response(
        200, content=binary, headers={"Content-Type": "application/octet-stream"},
    ))
    path = tmp_path / "raw.zip"
    assert api.download(DATASET + "-10", path, len(binary)) == len(binary)
    assert path.read_bytes() == binary
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v2/auto-experiments/download"
    assert dict(request.url.params) == {"id": DATASET + "-10"}
    assert request.content == b""


@pytest.mark.parametrize("ident", ["", "  ", DATASET + "-10,other-10", "x\nheader"])
def test_download_rejects_missing_or_multiple_ids(transport_client, tmp_path, ident):
    api, seen = transport_client(lambda request: pytest.fail("Invalid selection reached HTTP"))
    with pytest.raises(ValueError):
        api.download(ident, tmp_path / "raw.zip", 4096)
    assert seen == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("announced", [True, False])
def test_download_byte_budget_is_enforced_without_retry(transport_client, tmp_path, announced):
    def handler(request):
        response = httpx.Response(200, content=b"x" * 1025)
        if not announced:
            del response.headers["content-length"]
        return response

    api, seen = transport_client(handler)
    assert_error("DOWNLOAD_TOO_LARGE", lambda: api.download(DATASET + "-10", tmp_path / "raw.zip", 1024))
    assert len(seen) == 1
    if announced:
        assert list(tmp_path.iterdir()) == []


def test_download_redirect_never_forwards_auth_or_creates_output(transport_client, tmp_path):
    api, seen = transport_client(lambda request: httpx.Response(
        307, headers={"Location": "https://outside.invalid/raw.zip?token=PRIVATE"},
    ))
    error = assert_error("UNEXPECTED_REDIRECT", lambda: api.download(DATASET + "-10", tmp_path / "raw.zip", 4096))
    assert len(seen) == 1
    assert "PRIVATE" not in str(error)
    assert list(tmp_path.iterdir()) == []


def test_download_does_not_overwrite_existing_file(transport_client, tmp_path):
    api, _ = transport_client(lambda request: httpx.Response(200, content=raw_zip()))
    path = tmp_path / "existing.zip"
    path.write_bytes(b"existing-original")
    with pytest.raises(FileExistsError):
        api.download(DATASET + "-10", path, 4096)
    assert path.read_bytes() == b"existing-original"


def test_download_timeout_is_sanitized_and_not_retried(transport_client, tmp_path):
    def fail(request):
        raise httpx.ReadTimeout(PASSWORD, request=request)

    api, seen = transport_client(fail)
    error = assert_error("TRANSFER_FAILED", lambda: api.download(DATASET + "-10", tmp_path / "raw.zip", 4096))
    assert PASSWORD not in str(error)
    assert len(seen) == 1
