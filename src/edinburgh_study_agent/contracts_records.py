"""Success contracts for cached records, local organisation and file operations.

These definitions follow the existing producers. Optional nullable fields are
omitted by compact responses and retained as null by full responses. Local
writes and cached observations do not establish changes at the University.
"""
from __future__ import annotations

from .contracts_common import (
    STR, BOOL, JSON_OBJECT, ITEM, RECORD_ITEM, ARTIFACT, FILE_TEXT,
    IDENTIFIER, DATE, TIMESTAMP, SHA256, COUNT, SOURCE, KIND, AUTHENTICATION,
    PRESENTATION, obj, arr, nullable, enum,
)


def response(props, required=()):
    return obj({**props, "presentation": PRESENTATION}, required)


def variants(*branches):
    return {"type": "object", "anyOf": list(branches)}


PREFERENCES = obj({
    "locale": {"type": "string", "maxLength": 63},
    "display_timezone": {"type": "string", "maxLength": 100},
    "bilingual_titles": BOOL,
}, ("locale", "display_timezone", "bilingual_titles"), extra=True)
CAPABILITIES = obj({
    "implemented": arr(STR), "not_implemented": arr(STR),
    "out_of_scope": arr(STR), "unverified": arr(STR), "sharing": STR,
}, ("implemented", "not_implemented", "out_of_scope", "unverified", "sharing"))
LAST_OBSERVATION = obj({
    "source_url": STR, "observed_at": TIMESTAMP, "scope": STR,
    "coverage": enum("partial", "complete_visible_scope"),
    "authentication": AUTHENTICATION,
}, ("source_url", "observed_at", "scope", "coverage", "authentication"))
SERVICE_CHECK = variants(LAST_OBSERVATION, obj({
    "observed_at": TIMESTAMP, "coverage": STR, "authentication": AUTHENTICATION,
    "needs_login": BOOL, "page_count": COUNT, "warning": STR, "entry_url": STR,
}, ("observed_at", "coverage", "authentication")))

TASK_PROPERTIES = {
    "id": IDENTIFIER, "title": {"type": "string", "minLength": 1, "maxLength": 500},
    "estimate_minutes": {"type": "integer", "minimum": 5, "maximum": 6000,
                         "description": "User-supplied effort in minutes."},
    "item_id": nullable(IDENTIFIER), "deadline_mode": enum("linked", "manual"),
    "due_at": nullable(TIMESTAMP), "due_date": nullable(DATE),
    "priority": {"type": "integer", "minimum": 1, "maximum": 5},
    "notes": {"type": "string", "maxLength": 4000},
    "status": enum("todo", "doing", "done", "archived"),
    "created_at": TIMESTAMP, "updated_at": TIMESTAMP, "local_only": enum(True),
}
TASK_REQUIRED = ("id", "title", "estimate_minutes", "deadline_mode", "priority", "notes",
                 "status", "created_at", "updated_at", "local_only")
TASK = obj(TASK_PROPERTIES, TASK_REQUIRED)
TASK_AGENDA = obj({
    **TASK_PROPERTIES, "kind": enum("task"), "source": enum("local"),
    "timing": enum("date_only", "exact", "unknown"),
    "display_due_at": TIMESTAMP, "display_starts_at": TIMESTAMP, "display_ends_at": TIMESTAMP,
}, (*TASK_REQUIRED, "kind", "source", "timing"))
AGENDA_ITEM = {**RECORD_ITEM, "required": [*RECORD_ITEM["required"], "timing"]}

COLLECTION_PROPERTIES = {
    "id": IDENTIFIER, "item_id": IDENTIFIER,
    "collection": {"type": "string", "minLength": 1, "maxLength": 100},
    "tags": arr({"type": "string", "maxLength": 60}, 20),
    "notes": {"type": "string", "maxLength": 4000}, "archived": BOOL,
    "updated_at": TIMESTAMP, "local_only": enum(True),
}
COLLECTION_REQUIRED = tuple(COLLECTION_PROPERTIES)
COLLECTION_ENTRY = obj(COLLECTION_PROPERTIES, COLLECTION_REQUIRED)
COLLECTION_WITH_ITEM = obj({**COLLECTION_PROPERTIES, "item": RECORD_ITEM},
                           (*COLLECTION_REQUIRED, "item"))

SERVICE_PROPERTIES = {
    "id": IDENTIFIER, "title": STR, "official_name": STR,
    "category": STR, "category_id": enum("portal", "study", "record", "resources", "careers", "events", "support"),
    "url": STR, "access": enum("campus", "public", "mixed"),
    "topics": STR, "adapter": enum("learn"), "launch_label": STR, "recommended_section": STR,
    "supported_actions": arr(STR), "last_check": nullable(SERVICE_CHECK), "coverage": STR,
}
SERVICE = obj(SERVICE_PROPERTIES, ("id", "title", "official_name", "category", "category_id", "url",
                                   "access", "supported_actions", "coverage"))
HOME_SERVICE = obj({k: SERVICE_PROPERTIES[k] for k in
                   ("id", "title", "official_name", "category", "url", "coverage", "last_check")},
                  ("id", "title", "official_name", "category", "url", "coverage"))

CAPTURE_FIELDS = {
    "observation_id": IDENTIFIER, "duplicate": BOOL,
    "inserted": arr(IDENTIFIER, 500), "updated": arr(IDENTIFIER, 500),
    "older_items_ignored": arr(IDENTIFIER, 500),
    "coverage": enum("partial", "complete_visible_scope"), "note": STR,
}
CAPTURE_BASE = ("observation_id", "duplicate", "inserted", "updated")
CAPTURE = variants(
    response({k: {"enum": [True], "type": "boolean"} if k == "duplicate" else v
              for k, v in CAPTURE_FIELDS.items() if k in CAPTURE_BASE}, CAPTURE_BASE),
    response({**CAPTURE_FIELDS, "duplicate": enum(False)},
             (*CAPTURE_BASE, "older_items_ignored", "coverage", "note")),
)
IMPORT_FIELDS = {**CAPTURE_FIELDS, "file_sha256": SHA256, "imported_occurrences": COUNT,
                 "warnings": arr(STR), "note": STR}
IMPORT = variants(
    response({**IMPORT_FIELDS, "duplicate": enum(True)},
             (*CAPTURE_BASE, "file_sha256", "imported_occurrences", "warnings", "note")),
    response({**IMPORT_FIELDS, "duplicate": enum(False)},
             (*CAPTURE_BASE, "older_items_ignored", "coverage", "file_sha256", "imported_occurrences", "warnings", "note")),
)

OBSERVATION_ITEM = {**ITEM, "required": [*ITEM["required"], "excerpt"]}
OBSERVATION = obj({
    "source": SOURCE, "source_url": STR,
    "title": {"type": "string", "minLength": 1, "maxLength": 500},
    "observed_at": TIMESTAMP, "scope": {"type": "string", "minLength": 1, "maxLength": 500},
    "coverage": enum("partial", "complete_visible_scope"), "authentication": AUTHENTICATION,
    "text": {"type": "string", "maxLength": 30_000},
    "items": arr(OBSERVATION_ITEM, 500), "item_count": COUNT,
}, ("source", "source_url", "title", "observed_at", "scope", "coverage", "authentication", "text"))
OBSERVATION["anyOf"] = [{"required": ["items"]}, {"required": ["item_count"]}]

STUDENT_GUIDANCE = obj({"workflow": arr(STR), "login": STR, "coverage": STR},
                       ("workflow", "login", "coverage"))
HOST_GUIDANCE = obj({
    "core": STR, "setup": STR,
    "clients": obj({name: STR for name in
                    ("chatgpt_work", "claude_desktop", "claude_code", "workbuddy", "deepseek_harness")},
                   ("chatgpt_work", "claude_desktop", "claude_code", "workbuddy", "deepseek_harness")),
    "acceptance": STR,
}, ("core", "setup", "clients", "acceptance"))
LANGUAGES = {"type": "object", "maxProperties": 100,
             "propertyNames": {"type": "string", "maxLength": 63},
             "additionalProperties": {"type": "string", "maxLength": 100}}
LANGUAGE_GUIDANCE = obj({
    "catalog_languages": LANGUAGES, "instructions": STR, "source_integrity": STR,
    "fallback": STR, "timezone": STR,
}, ("catalog_languages", "instructions", "source_integrity", "fallback", "timezone"))
HELP = variants(*(response({"topic": enum(topic), "guidance": guidance, "note": STR},
                          ("topic", "guidance", "presentation", "note"))
                  for topic, guidance in (("student", STUDENT_GUIDANCE), ("hosts", HOST_GUIDANCE),
                                          ("languages", LANGUAGE_GUIDANCE), ("capabilities", CAPABILITIES),
                                          ("schemas", JSON_OBJECT))))

OUTPUTS = {
    "study_status": response({
        "version": STR, "name": enum("UoE Companion"), "transport": enum("stdio"),
        "browser": enum("plugin_owned_persistent_campus_session"), "data_directory": STR,
        "counts": obj({kind: COUNT for kind in KIND["enum"]}), "tasks": COUNT,
        "last_observations": obj({source: LAST_OBSERVATION for source in SOURCE["enum"]}),
        "live_connection_checked": enum(False), "capabilities": arr(STR), "unsupported": arr(STR),
        "privacy": STR, "audience": enum("students"), "tool_profile": enum("daily", "student", "full"),
        "basic_workflows": obj({
            "schedules": STR, "course_files": STR, "learn_updates_and_unread": STR,
            "public_dates_events": STR, "older_chat_work_catalog": STR, "advanced_operations": STR,
        }, ("schedules", "course_files", "learn_updates_and_unread", "public_dates_events")),
        "preferences": PREFERENCES, "feature_status": CAPABILITIES,
    }, ("version", "name", "transport", "browser", "counts", "tasks", "last_observations",
        "live_connection_checked", "capabilities", "unsupported", "privacy", "audience", "tool_profile",
        "basic_workflows", "preferences")),
    "study_route": variants(
        response({"target": STR, "url": STR, "steps": arr(STR),
                  "host_browser_required": enum(False), "next_tool": STR},
                 ("target", "url", "steps", "host_browser_required", "next_tool")),
        response({"url": STR, "title": STR, "source": SOURCE, "observed_at": TIMESTAMP,
                  "host_browser_required": enum(False), "next_tool": STR},
                 ("url", "title", "source", "observed_at", "host_browser_required", "next_tool")),
    ),
    "study_capture": CAPTURE,
    "study_search": response({
        "items": arr(RECORD_ITEM, 500), "total_matches": COUNT, "truncated": BOOL,
        "offset": COUNT, "next_offset": nullable(COUNT), "live": enum(False),
        "coverage": enum("cached_observations_only"), "note": STR,
    }, ("items", "total_matches", "truncated", "offset", "live", "coverage", "note")),
    "study_evidence": response({
        "observation": OBSERVATION, "content_is_untrusted": enum(True),
        "offset": COUNT, "total_chars": COUNT, "has_more": BOOL, "next_offset": nullable(COUNT),
    }, ("observation", "content_is_untrusted", "offset", "total_chars", "has_more", "next_offset")),
    "study_deadlines": response({
        "deadlines": arr(RECORD_ITEM), "unknown_deadlines": arr(RECORD_ITEM),
        "timezone": enum("Europe/London"), "live": enum(False),
        "coverage": enum("cached_observations_only"),
        "range": obj({"start": DATE, "end_inclusive": DATE}, ("start", "end_inclusive")), "warning": STR,
    }, ("deadlines", "unknown_deadlines", "timezone", "live", "coverage", "range", "warning")),
    "study_task_create": response(TASK_PROPERTIES, TASK_REQUIRED),
    "study_task_update": response({"task": TASK, "university_submission_changed": enum(False)},
                                  ("task", "university_submission_changed")),
    "study_tasks": response({"tasks": arr(TASK), "local_only": enum(True)}, ("tasks", "local_only")),
    "study_plan": response({
        "blocks": arr(obj({"task_id": IDENTIFIER, "title": STR, "starts_at": TIMESTAMP, "ends_at": TIMESTAMP,
                           "minutes": {"type": "integer", "minimum": 5, "maximum": 120},
                           "item_id": nullable(IDENTIFIER)},
                          ("task_id", "title", "starts_at", "ends_at", "minutes"))),
        "unallocated": arr(obj({"task_id": IDENTIFIER, "title": STR,
                                "remaining_minutes": {"type": "integer", "minimum": 1, "maximum": 6000},
                                "reason": enum("deadline_passed", "insufficient_time_before_deadline")},
                               ("task_id", "title", "remaining_minutes", "reason"))),
        "timezone": enum("Europe/London"), "draft": enum(True), "calendar_changed": enum(False),
        "assignments_without_active_tasks": arr(RECORD_ITEM, 500), "assumptions": arr(STR),
        "coverage": enum("cached_observations_only"), "warning": STR,
    }, ("blocks", "unallocated", "timezone", "draft", "calendar_changed", "assignments_without_active_tasks",
        "assumptions", "coverage", "warning")),
    "study_import_calendar": IMPORT,
    "study_export_calendar": response({"path": STR, "events": COUNT, "sha256": SHA256,
                                       "calendar_changed": enum(False), "note": STR},
                                      ("path", "events", "sha256", "calendar_changed", "note")),
    "study_download_resource": response(ARTIFACT["properties"],
        (*ARTIFACT["required"], "reused", "verified", "signed_urls_stored", "save_dialog_required")),
    "study_downloads": response({"files": arr({**ARTIFACT, "required": [*ARTIFACT["required"], "file_exists"]}),
                                 "signed_urls_stored": enum(False)}, ("files", "signed_urls_stored")),
    "study_services": response({"services": arr(SERVICE), "live": enum(False),
                                "directory_is_not_connection_proof": enum(True), "scope": STR, "next_tool": STR},
                               ("services", "presentation", "live", "directory_is_not_connection_proof", "scope", "next_tool")),
    "study_collect": response({"collection_entry": COLLECTION_ENTRY, "item": RECORD_ITEM,
                               "university_record_changed": enum(False)},
                              ("collection_entry", "item", "university_record_changed")),
    "study_collections": response({
        "entries": arr(COLLECTION_WITH_ITEM, 200), "total_matches": COUNT, "truncated": BOOL,
        "offset": COUNT, "next_offset": nullable(COUNT), "local_only": enum(True),
    }, ("entries", "total_matches", "truncated", "offset", "local_only")),
    "study_home": response({
        "name": enum("UoE Companion"), "services": arr(HOME_SERVICE),
        "indexed_items": arr(obj({"source": SOURCE, "kind": KIND, "count": COUNT}, ("source", "kind", "count"))),
        "download_count": COUNT, "tasks": arr(TASK, 10), "task_count": COUNT, "tasks_truncated": BOOL,
        "collections": arr(COLLECTION_WITH_ITEM, 10), "collection_count": COUNT, "collections_truncated": BOOL,
        "live": enum(False),
        "next_tools": obj({"tasks": STR, "collections": STR, "source": STR}, ("tasks", "collections", "source")),
        "note": STR,
    }, ("name", "services", "indexed_items", "download_count", "tasks", "task_count", "tasks_truncated",
        "collections", "collection_count", "collections_truncated", "live", "next_tools", "note")),
    "study_read_file": response(FILE_TEXT["properties"], FILE_TEXT["required"]),
    "study_preferences": response({"preferences": PREFERENCES, "changed": BOOL, "local_only": enum(True),
                                   "translation_scope": STR, "catalog_languages": LANGUAGES, "other_languages": STR},
                                  ("preferences", "changed", "local_only", "presentation", "translation_scope")),
    "study_agenda": response({
        "items": arr(variants(AGENDA_ITEM, TASK_AGENDA), 500), "total_matches": COUNT,
        "unknown_dates": COUNT, "offset": COUNT, "next_offset": nullable(COUNT), "truncated": BOOL,
        "live": enum(False), "coverage": enum("cached_observations_only"), "start": DATE, "end": DATE,
        "source_dates_unchanged": enum(True), "range_timezone": enum("Europe/London"),
        "note": STR, "refresh_tools": arr(STR),
    }, ("items", "total_matches", "unknown_dates", "offset", "truncated", "live", "coverage", "start", "end",
        "presentation", "source_dates_unchanged", "range_timezone", "note", "refresh_tools")),
    "study_help": HELP,
}
