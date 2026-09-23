"""Closed, compact result contract for the resumable NMR acquisition tool."""
from .contracts_common import obj, arr, enum, nullable, BOOL, COUNT, SHA256, TIMESTAMP, DATE, PRESENTATION

TEXT = {"type": "string", "maxLength": 2000}
ID = {"type": "string", "minLength": 1, "maxLength": 256}
PROVIDER = enum("auto", "nomad", "legacy")
FILE = obj({"item_id": ID, "filename": TEXT, "size_bytes": COUNT, "sha256": SHA256, "downloaded_at": TIMESTAMP},
           ("item_id", "filename", "size_bytes", "sha256", "downloaded_at"))
RESULT = obj({"id": ID, "dataset_name": ID, "experiment_number": ID, "sample": TEXT, "title": TEXT,
              "acquired_on": DATE, "parameter_set": TEXT, "solvent": TEXT, "instrument": TEXT,
              "group": TEXT, "submitted_at": nullable(TEXT), "observed_at": TIMESTAMP}, ("id", "dataset_name", "experiment_number", "observed_at"))
DATASET = obj({"dataset_name": ID, "title": TEXT, "submitted_at": nullable(TEXT),
               "user": TEXT, "group": TEXT, "instrument": TEXT}, ("dataset_name", "title", "user", "group", "instrument"))
NETWORK = obj({"state": enum("vpn_disconnected", "vpn_active_service_unreachable", "network_unavailable"),
               "vpn_client": enum("FortiClient"), "vpn_adapter_active": nullable(BOOL),
               "observed_at": TIMESTAMP}, ("state", "vpn_client", "vpn_adapter_active", "observed_at"))
FIELDS = {
    "state": enum("status", "needs_input", "needs_auth", "needs_selection", "ready", "downloaded",
                  "no_matches", "unavailable", "authentication_pending", "connected", "disconnected"),
    "provider": PROVIDER, "message": TEXT, "request_id": ID, "sample": nullable(TEXT), "code": ID,
    "needed": arr(enum("provider", "sample", "group", "connection", "insecure_http_consent"), 5),
    "results": arr(RESULT, 50), "datasets": arr(DATASET, 20), "has_more": BOOL,
    "page": {"type": "integer", "minimum": 1, "maximum": 100},
    "limit": {"type": "integer", "minimum": 1, "maximum": 20}, "total_datasets": COUNT,
    "observed_at": TIMESTAMP, "source_page_url": TEXT,
    "coverage": enum("bounded_authenticated_sample_search", "bounded_personal_archive"),
    "order": enum("last_archived_desc"),
    "network": NETWORK, "automatic_retry": {"const": False, "type": "boolean"},
    "recovery_action": enum("connect_campus_vpn_then_resume", "check_campus_vpn_or_service_then_resume"),
    "connections": arr(obj({"provider": enum("nomad", "legacy"), "group": enum("3OR", "2OR"), "credentials_available": BOOL,
                            "authentication": enum("missing", "authenticated", "credentials_supplied"),
                            "remembered": BOOL, "persistence": enum("windows_dpapi", "process_memory_only", "none")},
                           ("provider", "credentials_available", "authentication")), 3),
    "connection": obj({"url": TEXT, "connection_id": ID, "expires_at": TIMESTAMP,
                       "reachability": enum("runtime_computer_browser"), "error_code": enum("NETWORK_UNAVAILABLE", "TRANSFER_FAILED", "AUTH_REQUIRED", "SERVICE_ERROR", "UNEXPECTED_RESPONSE", "UNEXPECTED_REDIRECT", "ENDPOINT_UNAVAILABLE", "RESPONSE_TOO_LARGE")}, ("url", "connection_id", "expires_at", "reachability")),
    "files": arr(FILE, 1), "cache_hit": BOOL, "source_transport": enum("https", "plaintext_http"),
    "integrity": obj({"member_count": COUNT, "file_count": COUNT, "total_uncompressed_bytes": COUNT,
                      "raw_files": arr(enum("fid", "ser"), 2), "acquisition_files": arr(TEXT, 10)},
                     ("member_count", "file_count", "total_uncompressed_bytes", "raw_files", "acquisition_files")),
    "presentation": PRESENTATION,
}
SCHEMA = obj(FIELDS, ("state", "provider", "message"))
SCHEMA["allOf"] = [{"oneOf": [
    {"properties": {"state": {"enum": [state]}}, "required": fields}
    for state, fields in {
        "status": ["connections"], "connected": ["request_id", "connections"], "needs_input": ["request_id", "needed"],
        "needs_auth": ["request_id"], "needs_selection": ["request_id"],
        "ready": ["request_id", "results", "source_transport"],
        "downloaded": ["request_id", "files", "cache_hit", "source_transport"],
        "authentication_pending": ["request_id", "connection"],
        "unavailable": ["request_id", "code"], "no_matches": ["request_id"],
        "disconnected": ["request_id"],
    }.items()
]}]
OUTPUTS = {"study_nmr": SCHEMA}
