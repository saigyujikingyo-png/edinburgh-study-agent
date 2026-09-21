"""Shared JSON Schema definitions for version 1 structured tool results.

The bounded JSON extension is deliberately non-recursive in its schema form.
The output validator also walks every value to enforce the same limits at all
nesting levels. Named record fields below are validated more narrowly.
"""
from __future__ import annotations

from copy import deepcopy

STR = {"type": "string", "maxLength": 2_100_000}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}
NUM = {"type": "number"}
JSON_VALUE = {
    "type": ["null", "boolean", "integer", "number", "string", "array", "object"],
    "maxLength": 2_100_000, "maxItems": 100_000, "maxProperties": 512,
    "description": "Bounded JSON extension; the server also limits depth and total size recursively.",
}
JSON_OBJECT = {
    "type": "object", "maxProperties": 512,
    "propertyNames": {"type": "string", "maxLength": 256},
    "additionalProperties": JSON_VALUE,
}


def obj(props, required=(), *, extra=False):
    """Create a closed object unless a bounded extension is explicitly requested."""
    value = {"type": "object", "properties": dict(props),
             "additionalProperties": deepcopy(JSON_VALUE) if extra else False,
             "maxProperties": max(512 if extra else len(props), len(props))}
    if required:
        value["required"] = list(required)
    return value


def arr(schema, limit=100_000):
    return {"type": "array", "items": schema, "maxItems": limit}


def nullable(schema):
    """Null means unavailable/not supplied; compact output may omit that key."""
    return {"anyOf": [schema, {"type": "null"}]}


def enum(*values):
    value = {"enum": list(values)}
    if values and all(isinstance(v, bool) for v in values):
        value["type"] = "boolean"
    elif values and all(isinstance(v, str) for v in values):
        value["type"] = "string"
    elif values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        value["type"] = "integer"
    return value


IDENTIFIER = {"type": "string", "minLength": 1, "maxLength": 512}
DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$", "maxLength": 10}
TIMESTAMP = {"type": "string", "maxLength": 80,
             "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)$",
             "description": "ISO 8601 timestamp with an explicit UTC offset; source instants are retained."}
SHA256 = {"type": "string", "pattern": "^[a-f0-9]{64}$", "minLength": 64, "maxLength": 64}
COUNT = {"type": "integer", "minimum": 0}
SOURCE = enum("learn", "myed", "timetable", "library", "university")
KIND = enum("course", "resource", "assignment", "event", "announcement", "service")
AUTHENTICATION = enum("authenticated", "login_required", "unknown")

PRESENTATION = obj({
    "response_language": {"type": "string", "maxLength": 63},
    "catalog_language": {"type": "string", "maxLength": 63},
    "catalog_fallback": BOOL,
    "display_timezone": {"type": "string", "maxLength": 100},
    "source_timezone": enum("Europe/London"),
    "bilingual_titles": BOOL,
    "direction": enum("rtl", "ltr"),
}, ("response_language", "catalog_language", "catalog_fallback", "display_timezone",
    "source_timezone", "bilingual_titles", "direction"))

ITEM = obj({
    "native_id": {"type": "string", "minLength": 1, "maxLength": 300},
    "kind": KIND,
    "title": {"type": "string", "minLength": 1, "maxLength": 500},
    "url": nullable(STR),
    "course_id": nullable({"type": "string", "maxLength": 300}),
    "course_title": nullable({"type": "string", "maxLength": 500}),
    "service_id": nullable({"type": "string", "maxLength": 100}),
    "excerpt": {"type": "string", "minLength": 1, "maxLength": 3000},
    "due_at": nullable(TIMESTAMP), "due_date": nullable(DATE),
    "starts_at": nullable(TIMESTAMP), "ends_at": nullable(TIMESTAMP),
    "status": enum("unknown", "available", "unavailable", "submitted", "graded", "cancelled"),
    "id": IDENTIFIER, "item_id": IDENTIFIER,
    "source": SOURCE, "source_url": STR,
    "observed_at": TIMESTAMP, "observation_id": IDENTIFIER,
    "age_hours": {"type": "number", "minimum": 0, "description": "Age of the observation in hours."},
    "needs_refresh": BOOL,
    "timing": enum("date_only", "exact", "unknown"),
    "display_due_at": TIMESTAMP, "display_starts_at": TIMESTAMP, "display_ends_at": TIMESTAMP,
    "excerpt_truncated": BOOL, "excerpt_length": COUNT,
}, ("native_id", "kind", "title", "status"))
RECORD_ITEM = {**ITEM, "required": [*ITEM["required"], "id", "source", "observed_at", "observation_id", "needs_refresh"]}

ARTIFACT = obj({
    "item_id": IDENTIFIER, "title": {"type": "string", "minLength": 1, "maxLength": 500},
    "filename": {"type": "string", "minLength": 1, "maxLength": 201},
    "path": {"type": "string", "minLength": 1, "maxLength": 32_768},
    "size_bytes": {"type": "integer", "minimum": 1, "description": "Saved byte count, not an estimate."},
    "sha256": SHA256, "source_page_url": STR, "downloaded_at": TIMESTAMP,
    "title_source": enum("filename"),
    "attachment_binding": obj({
        "method": enum("unique_visible_preview"), "content_id": IDENTIFIER,
        "content_path": {"type": "string", "pattern": r"^/ultra/courses/_\d+_\d+/file/_\d+_\d+$", "maxLength": 300},
        "preview_filename": {"type": "string", "minLength": 1, "maxLength": 201},
        "requested_filename": {"type": "string", "minLength": 1, "maxLength": 201},
    }, ("method", "content_id", "content_path")),
    "file_exists": BOOL, "reused": BOOL, "verified": BOOL,
    "remote_freshness_checked": BOOL, "signed_urls_stored": enum(False),
    "save_dialog_required": enum(False),
}, ("item_id", "title", "filename", "path", "size_bytes", "sha256", "source_page_url", "downloaded_at"))

FILE_TEXT = obj({
    "item_id": IDENTIFIER, "filename": {"type": "string", "minLength": 1, "maxLength": 201},
    "sha256": SHA256, "source_page_url": STR,
    "text": {"type": "string", "maxLength": 30_000},
    "offset": {"type": "integer", "minimum": 0, "maximum": 2_000_000},
    "next_offset": nullable({"type": "integer", "minimum": 0, "maximum": 2_000_000}),
    "has_more": BOOL, "extraction_limit_reached": BOOL,
    "source_content_is_untrusted": enum(True), "verified": enum(True), "text_cache_hit": BOOL,
    "note": STR, "table_reading": STR, "text_truncated": BOOL, "text_length": COUNT,
}, ("item_id", "filename", "sha256", "source_page_url", "text", "offset", "has_more",
    "extraction_limit_reached", "source_content_is_untrusted", "verified", "text_cache_hit", "note"))
