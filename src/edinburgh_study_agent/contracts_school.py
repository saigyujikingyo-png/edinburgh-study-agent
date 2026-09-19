"""Output contracts for school jobs and deterministic student workflows.

Public job envelopes stay compact.  JOB_RESULTS defines the independently
validated payload for every worker action and is discoverable on demand.
Nullable source fields are optional because compact() omits null recursively.
Published marks remain strings, including blanks and zero; a missing calculated
mean is not represented as zero.  No schema implies live access or delivery.
"""
from .contracts_common import (
    STR, BOOL, INT, NUM, ITEM, ARTIFACT, FILE_TEXT,
    obj, arr, nullable, enum,
)
from .school_errors import HOSTS, FAILURE_CODES


NN = {**INT, "minimum": 0}
POSITIVE = {**INT, "minimum": 1}
YEAR = {"type": "string", "pattern": r"^\d{4}/\d{2}$", "maxLength": 7}
YEAR_REQUEST = {"type": "string", "pattern": r"^(all|current|\d{4}/\d{2})$", "maxLength": 7}
DATE = {"type": "string", "format": "date", "maxLength": 10}
STAMP = {"type": "string", "format": "date-time", "maxLength": 64}
SHA256 = {"type": "string", "pattern": "^[a-f0-9]{64}$", "maxLength": 64}
AUTHENTICATION = enum("authenticated", "unknown", "login_required")
ACTION = enum("login", "courses", "resources", "download", "myed", "service",
              "read_resource", "results", "timetable", "materials", "messages")
STATE = enum("queued", "running", "waiting_for_login", "complete", "partial",
             "needs_login", "failed", "cancelled")


def union(*schemas):
    return {"anyOf": list(schemas)}


def mapping(value, limit=512):
    return {"type": "object", "additionalProperties": value, "maxProperties": limit}


# Legacy service dispatch and school_job pagination add these fields without
# changing the underlying rows. next_offset=null means there is no next page;
# compact results omit that null, while has_more/response_truncated remain.
CONTINUATION = obj({
    "tool": enum("study_read_service"), "service_id": enum("timetable", "learn", "events"),
    "item_id": nullable(STR), "query": STR,
}, ("tool", "service_id", "query"))
PAGING = {
    "offset": NN, "returned_count": NN, "total_items": NN,
    "next_offset": nullable(NN), "has_more": BOOL, "response_truncated": BOOL,
    "continuation_tool": enum("study_timetable", "study_materials", "study_messages", "study_school_job"),
    "continuation": CONTINUATION, "legacy_catalog_compatible": BOOL,
}
FRESHNESS = {
    "live": BOOL, "cache_hit": BOOL, "cache_age_seconds": {**NUM, "minimum": 0},
    "cache_ttl_seconds": NN, "remote_freshness_checked": BOOL,
}


def paged(props, required=()):
    return obj({**PAGING, **props}, required)


WORKFLOW_HINT = {
    "plugin_version": STR, "host_browser_required": enum(False),
    "available_workflows": obj({
        "course_results": obj({
            "tool": enum("study_results"),
            "arguments": obj({"academic_year": enum("all")}, ("academic_year",)),
            "status": enum("implemented"),
            "if_tool_not_listed": obj({
                "tool": enum("study_read_service"),
                "arguments": obj({"service_id": enum("euclid"), "section": enum("Courses"),
                                  "query": enum("all"), "max_pages": enum(1)},
                                 ("service_id", "section", "query", "max_pages")),
            }, ("tool", "arguments")),
            "scope": STR,
        }, ("tool", "arguments", "status", "if_tool_not_listed", "scope")),
    }, ("course_results",)),
}

PREVIOUS_CHECK = obj({
    "checked_at": STAMP, "authenticated": BOOL, "service": enum("learn"),
    "scope": enum("dedicated_local_browser"), "credentials_exported": enum(False),
})
SCHOOL_STATUS = obj({
    "browser_owner": enum("edinburgh_plugin"), "profile_location": STR,
    "previous_check": PREVIOUS_CHECK, "live_connection_checked": enum(False),
    "active_jobs": arr(obj({"job_id": STR, "action": nullable(ACTION),
                            "state": STATE, "updated_at": STAMP},
                           ("job_id", "state", "updated_at")), 30),
    "login_method": STR, "session_expiry": STR,
    "host_browser_required": enum(False), "credentials_exposed_to_agent": enum(False),
}, ("browser_owner", "previous_check", "live_connection_checked", "active_jobs",
    "login_method", "session_expiry", "host_browser_required", "credentials_exposed_to_agent"))

# A denied/closed course is a partial result rather than an expired-login claim.
# page_job may attach ordinary item-page counters to this empty array.
COURSE_UNAVAILABLE = paged({
    "coverage": enum("unavailable"), "items": arr(ITEM, 0),
    "warning": STR, "next_step": STR,
}, ("coverage", "items", "warning", "next_step"))

LOGIN_RESULT = obj({"authenticated": BOOL, "service": enum("learn"), "next_step": STR},
                   ("authenticated", "service", "next_step"))

COURSE_LIST = paged({
    "live": BOOL, "items": arr(ITEM), "observed_at": STAMP,
    "coverage": enum("partial", "complete_visible_scope"), "pages": NN,
    "observation_id": STR, "warning": STR,
}, ("live", "items", "coverage"))
RESOURCE_LIST = paged({
    "live": BOOL, "items": arr(ITEM, 500), "observed_at": STAMP,
    "coverage": enum("partial"), "expanded_folders": NN,
    "folders_not_opened": arr(STR, 150), "remaining_collapsed": NN,
    "observation_id": STR, "warning": STR, "note": STR,
}, ("live", "items", "coverage"))

DOWNLOAD_FAILURE = obj({"item_id": STR, "title": STR, "error_type": STR, "error": STR},
                       ("item_id", "error"))
DOWNLOAD_RESULT = obj({
    **FRESHNESS, "saved": arr(ARTIFACT, 30), "failed": arr(DOWNLOAD_FAILURE, 30),
    "complete": BOOL, "needs_login": BOOL, "remaining_item_ids": arr(STR, 30),
}, ("saved", "failed"))

RESOURCE_FILE = obj({**FRESHNESS, "download": ARTIFACT, "content": FILE_TEXT},
                    ("live", "download", "content"))
RESOURCE_PAGE = obj({
    "live": BOOL, "item_id": STR, "title": STR, "url": STR,
    "text": STR, "text_truncated": BOOL, "text_length": NN,
    "coverage": enum("partial"), "observation_id": STR, "observed_at": STAMP,
    "source_content_is_untrusted": enum(True),
}, ("live", "item_id", "title", "url", "text", "text_truncated", "coverage",
    "observation_id", "observed_at", "source_content_is_untrusted"))

# Original EUCLID fields preserve their published strings verbatim; no numeric
# mark is fabricated from an empty field. The optional course code is explicitly
# nullable when the displayed title has no recognised course-code suffix.
RESULT_ROW = obj({
    "item_id": STR, "academic_year": YEAR, "course_code": nullable(STR),
    "title": STR, "mark": STR, "grade": STR, "credits": STR, "result": STR, "sit": STR,
}, ("item_id", "academic_year", "title", "mark", "grade", "credits", "result", "sit"))
SUMMARY_BASE = {"numeric_marks": NN, "marks_not_in_mean": NN}
YEAR_SUMMARY = union(
    obj({**SUMMARY_BASE, "mean_status": enum("calculated"),
         "credits_used": {**NUM, "exclusiveMinimum": 0},
         "credit_weighted_mean": {**NUM, "minimum": 0, "maximum": 100}},
        ("numeric_marks", "marks_not_in_mean", "mean_status", "credits_used", "credit_weighted_mean")),
    obj({**SUMMARY_BASE, "mean_status": enum("incomplete_panel", "no_numeric_marks", "missing_or_nonpositive_credits")},
        ("numeric_marks", "marks_not_in_mean", "mean_status")),
)
RESULT_YEAR = obj({
    "academic_year": YEAR, "record_count": NN, "observation_id": STR,
    "complete_loaded_panel": BOOL, "summary": YEAR_SUMMARY,
}, ("academic_year", "record_count", "complete_loaded_panel", "summary"))
RESULTS = paged({
    **FRESHNESS, "service_id": enum("euclid"), "section": enum("Courses"),
    "academic_year": YEAR_REQUEST, "observed_at": STAMP,
    "authentication": enum("authenticated"), "source_url": STR,
    "available_years": arr(YEAR, 30), "years": arr(RESULT_YEAR, 30),
    "items": arr(RESULT_ROW, 15000), "record_count": NN,
    "coverage": enum("partial", "complete_loaded_years"), "failed": arr(STR),
    "source_content_is_untrusted": enum(True), "note": STR,
    "summary_method": STR, "answer_guidance": STR,
}, ("live", "service_id", "section", "academic_year", "observed_at", "authentication",
    "source_url", "available_years", "years", "items", "record_count", "coverage", "failed",
    "source_content_is_untrusted", "note", "summary_method", "answer_guidance"))

PORTAL_FAILURE = obj({
    "live": BOOL, "service_id": STR, "observed_at": STAMP,
    "coverage": enum("entry_only", "login_required", "external_provider"),
    "authentication": AUTHENTICATION, "entry_url": STR,
    "warning": STR, "page_count": enum(0), "needs_login": BOOL,
}, ("live", "service_id", "observed_at", "coverage", "authentication", "entry_url", "warning", "page_count"))
UNAUTHENTICATED_RESULTS = paged({
    "live": BOOL, "service_id": enum("euclid"), "authentication": AUTHENTICATION,
    "coverage": enum("unavailable"), "failed": arr(STR), "items": arr(RESULT_ROW, 0),
}, ("live", "service_id", "authentication", "coverage", "failed", "items"))
PORTAL_LINK = obj({"item_id": STR, "title": STR, "url": STR}, ("item_id", "title", "url"))
PORTAL_PAGE = obj({
    "item_id": STR, "title": STR, "url": STR, "observation_id": STR, "excerpt": STR,
    "available_sections": arr(STR, 300), "links": arr(PORTAL_LINK, 100),
    "links_total": NN, "links_truncated": BOOL, "expand_links": STR,
    "excerpt_truncated": BOOL, "excerpt_length": NN,
}, ("item_id", "title", "url", "observation_id", "excerpt", "available_sections", "links"))
PORTAL_PAGES = obj({
    **WORKFLOW_HINT, "live": BOOL, "service_id": STR, "observed_at": STAMP,
    "coverage": enum("partial", "unavailable"), "authentication": AUTHENTICATION,
    "entry_url": STR, "page_count": NN, "pages": arr(PORTAL_PAGE, 10),
    "failed": arr(STR), "source_content_is_untrusted": enum(True), "note": STR, "next_tool": STR,
}, ("live", "service_id", "observed_at", "coverage", "authentication", "entry_url",
    "page_count", "pages", "failed", "source_content_is_untrusted", "note"))

TIMETABLE_OCCURRENCE = obj({
    "id": STR, "title": STR, "type": STR, "starts_at": STAMP, "ends_at": STAMP,
    "location": STR, "academic_year": nullable(YEAR), "semester": nullable(enum(1, 2)),
    "week": nullable(NN), "week_label": STR, "modules": STR, "groups": STR,
    "source_text": STR,
}, ("id", "title", "type", "starts_at", "ends_at", "location", "week_label", "modules", "groups", "source_text"))
TIMETABLE_PATTERN = obj({
    "title": STR, "type": STR, "weekday": enum("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "start_time": {"type": "string", "pattern": r"^\d{2}:\d{2}$", "maxLength": 5},
    "end_time": {"type": "string", "pattern": r"^\d{2}:\d{2}$", "maxLength": 5},
    "location": STR, "modules": STR, "groups": STR, "dates": arr(DATE),
}, ("title", "type", "weekday", "start_time", "end_time", "location", "modules", "groups", "dates"))
TIMETABLE_WEEK_OVERVIEW = obj({
    "academic_year": nullable(YEAR), "semester": nullable(enum(1, 2)), "week": nullable(NN),
    "first_class_date": DATE, "last_class_date": DATE, "active_dates": POSITIVE,
    "occurrences": POSITIVE, "types": mapping(NN),
}, ("first_class_date", "last_class_date", "active_dates", "occurrences", "types"))
TIMETABLE_OVERVIEW = obj({
    "first_class_date": nullable(DATE), "last_class_date": nullable(DATE),
    "occurrence_count": NN, "types": mapping(NN), "weeks": arr(TIMETABLE_WEEK_OVERVIEW, 30),
    "weeks_truncated": BOOL, "note": STR,
}, ("occurrence_count", "types", "weeks", "weeks_truncated", "note"))
PERSONAL_TIMETABLE = paged({
    "items": arr(union(TIMETABLE_OCCURRENCE, TIMETABLE_PATTERN)),
    "unparsed_rows": NN, "coverage": enum("partial", "exported_personal_timetable"),
    "source_url": STR, "observed_at": STAMP, "timezone": enum("Europe/London"),
    "timezone_basis": STR, "scope": STR, "academic_year": YEAR_REQUEST,
    "academic_year_basis": STR, "semester": nullable(enum(1, 2)),
    "view": enum("summary", "occurrences"), "occurrence_count": NN,
    "overview": TIMETABLE_OVERVIEW, "available_years": arr(YEAR),
    "cache_hit": BOOL, "remote_freshness_checked": BOOL,
    "source_content_is_untrusted": enum(True), "response_guidance": STR,
    "warning": STR, "next_step": STR,
}, ("items", "total_items", "offset", "has_more", "unparsed_rows", "coverage", "source_url", "observed_at",
    "timezone", "timezone_basis", "scope", "academic_year", "academic_year_basis", "view",
    "occurrence_count", "overview", "available_years", "cache_hit", "remote_freshness_checked",
    "source_content_is_untrusted", "response_guidance"))
PERSONAL_TIMETABLE["allOf"] = [{
    "if": {"properties": {"view": enum("summary")}, "required": ["view"]},
    "then": {"properties": {"items": arr(TIMETABLE_PATTERN)}},
    "else": {"properties": {"items": arr(TIMETABLE_OCCURRENCE)}},
}]
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
PDF_WEEK = obj({
    "semester": nullable(enum(1, 2)), "week": {**NN, "maximum": 99},
    "pages": arr(POSITIVE, 150), "days": obj({day: STR for day in DAYS}),
    "truncated_days": arr(enum(*DAYS), 7),
}, ("week", "pages", "days"))
PDF_TIMETABLE = paged({
    "items": arr(PDF_WEEK), "item_id": STR, "filename": STR, "sha256": SHA256,
    "source_url": nullable(STR), "scope": STR, "date_mapping": STR,
    "coverage": enum("course_document_week_grid", "partial"), "problems": arr(STR),
    "extraction_cache_hit": BOOL, "verified": BOOL, "remote_freshness_checked": BOOL,
    "source_content_is_untrusted": enum(True), "view": enum("week_previews", "week_cells"),
    "detail_tool": obj({
        "tool": enum("study_timetable"), "arguments": obj({
            "item_id": STR, "semester": nullable(enum(1, 2)), "view": enum("occurrences"),
        }, ("item_id", "view")), "optional_filter": STR,
    }, ("tool", "arguments", "optional_filter")),
    "response_guidance": STR,
}, ("items", "total_items", "offset", "has_more", "item_id", "filename", "sha256", "scope", "date_mapping",
    "coverage", "problems", "extraction_cache_hit", "verified", "remote_freshness_checked",
    "source_content_is_untrusted", "view", "detail_tool", "response_guidance"))

FAILURE = obj({
    "code":enum(*FAILURE_CODES),"stage":enum("learn","campus_sign_in"),
    "target_host":enum(*HOSTS),"http_status":{**INT,"minimum":100,"maximum":599},
    "authentication_required":BOOL,"automatic_retry":enum(False),
    "recovery_action":enum("sign_in","check_connection","retry_once"),
}, ("code","stage","automatic_retry","recovery_action"))
COURSE_CHOICE = obj({
    "coverage": enum("partial"), "needs_course_selection": BOOL,
    "courses": arr(obj({"course": STR, "title": STR}, ("course", "title")), 20), "note": STR,
    "remote_freshness_checked": enum(False),
}, ("coverage", "needs_course_selection", "courses", "note"))
MATERIAL_ROW = obj({
    "id": STR, "title": STR, "course_title": nullable(STR),
    "url": nullable(STR), "observed_at": STAMP,
}, ("id", "title", "observed_at"))
MATERIAL_LIST = paged({
    "items": arr(MATERIAL_ROW, 500), "live": BOOL, "coverage": enum("partial"),
    "remote_freshness_checked": BOOL, "note": STR, "next_step": STR,
    "response_guidance": STR, "needs_resource_selection": BOOL,
    "suggested_observed_files": arr(obj({"id": STR, "title": STR}, ("id", "title")), 5),
}, ("items", "total_items", "offset", "has_more", "live", "coverage", "remote_freshness_checked",
    "note", "next_step", "response_guidance"))
MATERIAL_FILE = obj({"content": FILE_TEXT, "remote_freshness_checked": BOOL, "cache_hit": BOOL},
                    ("content", "remote_freshness_checked"))

MATERIAL_CHANGE = obj({
    **MATERIAL_ROW["properties"], "change":enum("newly_observed","metadata_changed","baseline","comparison_unknown"),
    "changed_fields":arr(enum("title","url","status","excerpt"),4),"previous_observed_at":STAMP,
}, ("id","title","observed_at","change","changed_fields"))
MATERIAL_CHECK = obj({
    "course":STR,"title":STR,"checked":BOOL,"status":enum("checked","unavailable","interrupted"),
    "observed_at":STAMP,"observed_resources":NN,"not_seen_in_scan":NN,
    "remaining_collapsed":NN,"failed_folders":NN,"baseline_truncated":BOOL,
}, ("course","title","checked","status"))
MATERIAL_UPDATES = paged({
    "operation":enum("updates"),"items":arr(MATERIAL_CHANGE,1500),
    "counts":obj({key:NN for key in ("newly_observed","metadata_changed","baseline","unchanged_metadata","comparison_unknown")},
                 ("newly_observed","metadata_changed","baseline","unchanged_metadata","comparison_unknown")),
    "courses":arr(MATERIAL_CHECK,3),"observed_at":STAMP,"coverage":enum("partial"),
    "live":BOOL,"remote_freshness_checked":BOOL,"content_change_checked":enum(False),
    "course_offset":NN,"next_course_offset":nullable(NN),"has_more_courses":BOOL,
    "total_courses":NN,"checked_courses":{**NN,"maximum":3},
    "catalog_refreshed":BOOL,"catalog_truncated":BOOL,
    "source_content_is_untrusted":enum(True),"note":STR,"next_step":STR,"response_guidance":STR,
    "failure":FAILURE,"needs_login":BOOL,
}, ("operation","items","counts","courses","observed_at","coverage","live","remote_freshness_checked",
    "content_change_checked","course_offset","has_more_courses","total_courses","checked_courses",
    "catalog_refreshed","catalog_truncated","source_content_is_untrusted","note","next_step","response_guidance"))

ACTIVITY_ROW = obj({
    "id": STR, "title": STR, "url": STR, "course": STR, "course_url": nullable(STR),
    "published_text": STR, "text": STR, "text_truncated": BOOL, "text_length": NN,
}, ("id", "title", "url", "course", "published_text", "text"))
INBOX_ROW = obj({
    "title": STR, "course_code": STR, "unread_text": STR, "url": STR,
    "unread_count": nullable(NN),
}, ("title", "course_code", "unread_text", "url"))
MESSAGE_COMMON = {
    "source_url": STR, "observed_at": STAMP, "coverage": enum("partial"), "scope": STR,
    "cache_hit": BOOL, "remote_freshness_checked": BOOL,
    "source_content_is_untrusted": enum(True), "response_guidance": STR,
}
MESSAGE_REQUIRED = ("items", "total_items", "offset", "has_more", "source_url", "observed_at", "coverage",
                    "scope", "view", "cache_hit", "remote_freshness_checked",
                    "source_content_is_untrusted", "response_guidance")
MESSAGES = union(
    paged({**MESSAGE_COMMON, "view": enum("activity"), "items": arr(ACTIVITY_ROW, 100)}, MESSAGE_REQUIRED),
    paged({**MESSAGE_COMMON, "view": enum("inboxes"), "items": arr(INBOX_ROW, 100)}, MESSAGE_REQUIRED),
)
MESSAGES_UNAVAILABLE = paged({
    "coverage": enum("unavailable"), "items": arr(ACTIVITY_ROW, 0), "source_url": STR,
    "warning": STR, "next_step": STR,
}, ("coverage", "items", "source_url", "warning", "next_step"))

ACADEMIC_DATE = obj({
    "title": STR, "date_text": STR, "start_date": nullable(DATE), "end_date": nullable(DATE),
    "semester": enum(1, 2), "academic_year": YEAR, "source": enum("academic_dates"), "url": STR,
}, ("title", "date_text", "semester", "academic_year", "source", "url"))
PHYSICS_EVENT = obj({
    "title": STR, "starts_at": STAMP, "start_date": DATE, "end_date": DATE,
    "location": nullable(STR), "source": enum("physics_events"), "url": STR,
}, ("title", "starts_at", "start_date", "end_date", "source", "url"))
EVENT_SOURCE = union(
    obj({"source": enum("academic_dates", "physics_events"), "url": STR,
         "observed_at": STAMP, "cache_hit": BOOL, "record_count": NN},
        ("source", "url", "observed_at", "cache_hit", "record_count")),
    obj({"source": enum("academic_dates", "physics_events"), "error": STR,
         "coverage": enum("unavailable"), "warning": STR, "record_count": enum(0)},
        ("source", "error", "coverage", "warning", "record_count")),
)
EVENTS = paged({
    "items": arr(union(ACADEMIC_DATE, PHYSICS_EVENT)), "coverage": enum("partial"),
    "sources": arr(EVENT_SOURCE, 2), "undated_records": NN, "scope": STR,
    "source_content_is_untrusted": enum(True), "response_guidance": STR,
}, ("items", "total_items", "offset", "has_more", "coverage", "sources", "undated_records",
    "scope", "source_content_is_untrusted", "response_guidance"))

SERVICE_RESULT = union(PORTAL_FAILURE, PORTAL_PAGES, RESULTS, UNAUTHENTICATED_RESULTS)
JOB_RESULTS = {
    "login": union(LOGIN_RESULT, COURSE_UNAVAILABLE),
    "courses": union(COURSE_LIST, COURSE_UNAVAILABLE),
    "resources": union(RESOURCE_LIST, COURSE_UNAVAILABLE),
    "download": union(DOWNLOAD_RESULT, COURSE_UNAVAILABLE),
    "myed": union(SERVICE_RESULT, COURSE_UNAVAILABLE),
    "service": union(SERVICE_RESULT, COURSE_UNAVAILABLE),
    "read_resource": union(RESOURCE_FILE, RESOURCE_PAGE, COURSE_UNAVAILABLE),
    "results": union(RESULTS, PORTAL_FAILURE, UNAUTHENTICATED_RESULTS, COURSE_UNAVAILABLE),
    "timetable": union(PERSONAL_TIMETABLE, PDF_TIMETABLE, COURSE_UNAVAILABLE),
    "materials": union(COURSE_CHOICE, MATERIAL_LIST, MATERIAL_FILE, MATERIAL_UPDATES, RESOURCE_FILE,
                       RESOURCE_PAGE, DOWNLOAD_RESULT, COURSE_UNAVAILABLE),
    "messages": union(MESSAGES, MESSAGES_UNAVAILABLE, COURSE_UNAVAILABLE),
}

# The default catalog identifies common result metadata without repeating all
# eleven action payloads for every job tool. The registry must validate a
# non-null result against JOB_RESULTS[action] before public delivery.
JOB_RESULT_METADATA = obj({
    **FRESHNESS, **PAGING, "coverage": STR, "observed_at": STAMP,
    "source_url": STR, "source_content_is_untrusted": enum(True),
    "service_id": STR, "scope": STR, "note": STR,
}, extra=True)
JOB_RESULT_METADATA["description"] = (
    "Action-specific result; discover its contract by job action. Declared common "
    "metadata and bounded extensions are additionally validated against that action. "
    "Omitted or null result means no payload is available, not an empty success."
)
JOB = obj({
    **WORKFLOW_HINT, "job_id": {"type": "string", "pattern": "^[a-f0-9]{32}$", "maxLength": 32},
    "action": ACTION, "state": STATE, "created_at": STAMP, "updated_at": STAMP,
    "progress": STR, "result": nullable(JOB_RESULT_METADATA), "worker_pid": POSITIVE,
    "timings_ms": obj({"worker_start_delay": INT, "browser_ready": NN, "read_complete": NN, "worker_total": NN}),
    "source_content_is_untrusted": enum(True), "poll_after_seconds": {**NN, "maximum": 3},
    "browser_started": BOOL, "reused_cached_job": BOOL, "reused_active_job": BOOL,
    "reconciled_dead_worker": BOOL, "error_type": STR, "unchanged": BOOL,
    "failure":FAILURE,"blocked_by_job_id":{"type":"string","pattern":"^[a-f0-9]{32}$","maxLength":32},
    "retry_after_seconds":{**NN,"maximum":60},"reused_failed_job":BOOL,
}, ("job_id", "state", "updated_at", "poll_after_seconds"))
JOB["allOf"] = [{"anyOf": [{"required": ["action"]}, {"properties": {"unchanged": enum(True)}, "required": ["unchanged"]}]}]
JOB["description"] = (
    "Dated school job. queued/running/waiting_for_login are pending; complete/partial/"
    "needs_login/failed/cancelled are terminal. unchanged polling may omit action and "
    "payload. Failure/login states may omit result. A partial payload reports its own "
    "coverage; completion alone does not establish freshness, enrolment or delivery."
)

OUTPUTS = {
    "study_school_status": SCHOOL_STATUS,
    **{name: JOB for name in (
        "study_connect_school", "study_live_courses", "study_live_resources",
        "study_download_files", "study_school_job", "study_live_myed", "study_results",
        "study_read_resource", "study_timetable", "study_materials", "study_messages",
    )},
    "study_read_service": union(JOB, EVENTS),
    "study_events": EVENTS,
}
