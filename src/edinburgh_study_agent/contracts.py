"""Versioned output contracts shared by direct MCP calls and the daily dispatcher."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import math
import re

from jsonschema import Draft202012Validator

CONTRACT_VERSION = "1"
ERROR_CODES = ("UNKNOWN_TOOL", "INVALID_ARGUMENT", "TOOL_ERROR", "OUTPUT_VALIDATION_ERROR")


class OutputValidationError(ValueError):
    """An invalid server result; never includes private result values."""


def _field(path):
    return ".".join(re.sub(r"[^a-zA-Z0-9_-]", "_", str(part))[:48] for part in path)[:240] or "result"


def _bounded_json(value, depth=0, budget=None, *, max_depth=48):
    # This also bounds deliberately extensible source metadata and schema documents.
    if budget is None:
        budget = [250000]
    budget[0] -= 1
    if depth > max_depth or budget[0] < 0:
        raise OutputValidationError("Result exceeds the supported JSON depth or node budget.")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise OutputValidationError("Result contains a non-finite number.")
        return
    if isinstance(value, str):
        if len(value) > 2000000:
            raise OutputValidationError("Result text exceeds the supported bound.")
        return
    if isinstance(value, list):
        if len(value) > 100000:
            raise OutputValidationError("Result list exceeds the supported bound.")
        for entry in value:
            _bounded_json(entry, depth + 1, budget, max_depth=max_depth)
        return
    if isinstance(value, dict):
        if len(value) > 2000 or any(not isinstance(key, str) or len(key) > 1000 for key in value):
            raise OutputValidationError("Result object keys exceed the supported bounds.")
        for entry in value.values():
            _bounded_json(entry, depth + 1, budget, max_depth=max_depth)
        return
    raise OutputValidationError("Result contains a value that is not JSON data.")


@lru_cache(maxsize=1)
def _outputs():
    from .contracts_records import OUTPUTS as records
    from .contracts_school import OUTPUTS as school
    from .contracts_nmr import OUTPUTS as nmr
    if records.keys() & school.keys() or (records.keys() | school.keys()) & nmr.keys():
        raise RuntimeError("Duplicate output contract definitions.")
    return {**records, **school, **nmr}


def _metadata(operation=None):
    from .contracts_common import obj, STR
    return obj({"version": {"type": "string", "const": CONTRACT_VERSION},
                "operation": ({"type": "string", "const": operation} if operation else STR)},
               ("version", "operation"))


def _stamp(schema, operation):
    """Add metadata at the result root, including its root union alternatives."""
    schema = deepcopy(schema)
    if schema.get("type") == "object" or "properties" in schema:
        if "_contract" not in schema.get("properties", {}) and isinstance(schema.get("maxProperties"), int):
            schema["maxProperties"] += 1
        schema.setdefault("properties", {})["_contract"] = _metadata(operation)
        schema["required"] = list(dict.fromkeys([*schema.get("required", []), "_contract"]))
    for union in ("oneOf", "anyOf", "allOf"):
        if union in schema:
            schema[union] = [_stamp(branch, operation) for branch in schema[union]]
    return schema


@lru_cache(maxsize=1)
def error_schema():
    from .contracts_common import obj, STR, enum
    return obj({
        "contract_version": {"type": "string", "const": CONTRACT_VERSION},
        "error": obj({"code": enum(*ERROR_CODES), "operation": STR,
                      "message": {"type": "string", "maxLength": 1000},
                      "recovery": {"type": "string", "maxLength": 1000}},
                     ("code", "operation", "message", "recovery")),
        "identifiers": obj({key: {"type": "string", "maxLength": 128}
                            for key in ("job_id", "task_id", "item_id", "observation_id", "id")}),
    }, ("contract_version", "error"))


@lru_cache(maxsize=1)
def _error_validator():
    return Draft202012Validator(error_schema())


def validate_error(value):
    _bounded_json(value)
    _check(_error_validator(), value)


@lru_cache(maxsize=64)
def success_schema(name):
    from .contracts_common import obj
    if name == "study_more":
        # The operation-shaped payload is validated separately against its own
        # complete contract. This envelope avoids a default union of all tools.
        return obj({"_contract": _metadata()}, ("_contract",), extra=True)
    try:
        return _stamp(_outputs()[name], name)
    except KeyError:
        raise ValueError("Unknown output contract.") from None


@lru_cache(maxsize=64)
def output_schema(name):
    return {"type": "object", "oneOf": [success_schema(name), error_schema()],
            "description": "UoE output contract v1. Compact optional nulls may be omitted; source coverage and freshness remain explicit."}


@lru_cache(maxsize=64)
def _validator(name):
    schema = success_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=32)
def _job_validator(action):
    from .contracts_school import JOB_RESULTS
    if action not in JOB_RESULTS:
        raise OutputValidationError("School job action has no result contract.")
    schema = JOB_RESULTS[action]
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _check(validator, value, prefix=()):
    error = next(validator.iter_errors(value), None)
    if error is not None:
        raise OutputValidationError(f"Output field {_field((*prefix, *error.absolute_path))} violates {error.validator}.")


@lru_cache(maxsize=2)
def _more_validator(mode):
    from .contracts_common import obj, arr, STR, INT, BOOL, JSON_OBJECT
    if mode == "list":
        schema = obj({"tools": arr(obj({"tool": STR, "description": STR}, ("tool", "description")), 6),
                      "matched": INT, "refine_query": BOOL, "next_step": STR},
                     ("tools", "matched", "refine_query", "next_step"), extra=True)
    else:
        schema = obj({"tool": STR, "description": STR, "inputSchema": JSON_OBJECT,
                      "outputSchema": JSON_OBJECT, "annotations": JSON_OBJECT,
                      "contract_version": {"type": "string", "const": CONTRACT_VERSION}, "next_step": STR},
                     ("tool", "description", "inputSchema", "outputSchema", "contract_version", "annotations", "next_step"), extra=True)
    return Draft202012Validator(_stamp(schema, "study_more"))


def validate_result(name, value):
    """Validate actual JSON output, including the selected dispatcher/job payload."""
    if not isinstance(value, dict):
        raise OutputValidationError("Structured output must be a JSON object.")
    _bounded_json(value)
    _check(_validator(name), value)
    if name == "study_more":
        operation = value["_contract"]["operation"]
        if operation != "study_more":
            from .daily_tools import DAILY
            if operation in DAILY or operation in {"study_capture", "study_download_resource", "study_route"}:
                raise OutputValidationError("Dispatcher result names an unavailable operation.")
            validate_result(operation, value)
        else:
            _check(_more_validator("list" if "tools" in value else "describe"), value)
    if "job_id" in value:
        if "action" not in value and not value.get("unchanged"):
            raise OutputValidationError("A school job must retain its action unless the poll is unchanged.")
        body = value.get("result")
        if value.get("state") in {"complete", "partial"} and not isinstance(body, dict):
            raise OutputValidationError("A completed school job must retain its result object.")
        if isinstance(body, dict):
            if "action" not in value:
                raise OutputValidationError("A school job result must retain its action.")
            _check(_job_validator(value["action"]), body, ("result",))


def describe_contract(name=""):
    """Return complete operation-specific contracts only when requested."""
    from .contracts_school import JOB_RESULTS
    names = sorted([*_outputs(), "study_more"])
    if not name:
        return {"contract_version": CONTRACT_VERSION, "tools": names,
                "next_step": "Choose one tool with study_help(topic='schemas', tool=...).",
                "semantics": "Successful fields retain their existing meanings. Unknown optional nulls can be omitted in compact results; errors use isError=true and a stable structured error code."}
    if name not in names:
        raise ValueError("Choose a tool from the output contract registry.")
    value = {"contract_version": CONTRACT_VERSION, "tool": name, "outputSchema": output_schema(name),
             "server_validates": True, "text_fallback": "The JSON text block matches structuredContent."}
    action_tools = {"study_connect_school": "login", "study_live_courses": "courses",
                    "study_live_resources": "resources", "study_download_files": "download",
                    "study_live_myed": "myed", "study_results": "results", "study_read_service": "service",
                    "study_read_resource": "read_resource", "study_timetable": "timetable",
                    "study_materials": "materials", "study_messages": "messages"}
    if name in action_tools:
        value["jobResultSchema"] = JOB_RESULTS[action_tools[name]]
    if name == "study_school_job":
        value["job_actions"] = sorted(JOB_RESULTS)
        value["next_step"] = "Describe the direct school workflow to read its complete job-result schema."
    return deepcopy(value)
