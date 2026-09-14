"""Advertise a conservative schema subset while retaining Pydantic call validation."""
from copy import deepcopy
import json
import re
from functools import lru_cache
from pydantic import ValidationError
from mcp.types import CallToolResult, TextContent
from mcp.server.fastmcp import FastMCP

CONSTRAINTS={"minimum","maximum","exclusiveMinimum","exclusiveMaximum","multipleOf",
             "minLength","maxLength","minItems","maxItems","pattern","format"}
KEYWORDS={"type","oneOf","properties","required","additionalProperties","items","enum","const",
          "description","default","examples"}

def portable_schema(schema, *, output=False):
    definitions=schema.get("$defs",{})
    def convert(node, stack=()):
        if isinstance(node, bool):
            return node
        node=deepcopy(node)
        if "$ref" in node:
            ref=node.pop("$ref")
            if not ref.startswith("#/$defs/") or ref in stack:
                raise ValueError("Only acyclic local schema references can be advertised.")
            key=ref.removeprefix("#/$defs/")
            node={**convert(definitions[key],(*stack,ref)),**node}
        node.pop("$defs",None)
        if output:
            # Property-name constraints remain enforced by the full server schema.
            node.pop("propertyNames",None)
        # Generated field titles repeat the parameter name and cost prompt tokens.
        node.pop("title",None)
        if "anyOf" in node and not output:
            alternatives=node.pop("anyOf")
            kinds=[part.get("type") for part in alternatives]
            # Nullable optional fields have disjoint alternatives: oneOf preserves meaning.
            if len(alternatives)!=2 or kinds.count("null")!=1 or None in kinds:
                raise ValueError("Only disjoint nullable unions can be converted to portable oneOf.")
            node["oneOf"]=alternatives
        constraint_keys = CONSTRAINTS | ({"minProperties", "maxProperties"} if output else set())
        constraints=[f"{key}={node.pop(key)}" for key in sorted(constraint_keys & node.keys())]
        if constraints and not output:
            # These constraints remain enforced by the server even when a host's
            # schema interpreter cannot enforce their keywords during generation.
            node["description"]=(node.get("description","")+" Server validates: "+", ".join(constraints)+".").strip()
        unknown=node.keys()-(KEYWORDS | ({"anyOf", "allOf", "not"} if output else set()))
        if unknown:
            raise ValueError("Unsupported schema keywords: "+", ".join(sorted(unknown)))
        if "properties" in node:
            node["properties"]={key:convert(value,stack) for key,value in node["properties"].items()}
        if "items" in node:
            node["items"]=convert(node["items"],stack)
        for keyword in ("oneOf", "anyOf", "allOf"):
            if keyword in node:
                node[keyword]=[convert(part,stack) for part in node[keyword]]
        if isinstance(node.get("additionalProperties"),dict):
            node["additionalProperties"]=convert(node["additionalProperties"],stack)
        if isinstance(node.get("not"),dict):
            node["not"]=convert(node["not"],stack)
        return node
    return convert(schema)


@lru_cache(maxsize=64)
def advertised_output_schema(name):
    from .contracts import output_schema
    return portable_schema(output_schema(name), output=True)


def _identifiers(*values):
    found = {}
    for value in values:
        if isinstance(value, dict):
            for key in ("job_id", "task_id", "item_id", "observation_id", "id"):
                item = value.get(key)
                if isinstance(item, str) and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}", item) and not item.startswith("sk-"):
                    found.setdefault(key, item)
    return found


def _safe_message(exc):
    if isinstance(exc, ValidationError):
        fields = sorted({".".join(str(x) for x in item["loc"])[:100]
                         for item in exc.errors(include_input=False, include_url=False)})[:6]
        return "Invalid arguments: " + ", ".join(fields) + ". Use the declared parameter types and bounds."
    if isinstance(exc, ValueError):
        value = str(exc)
        value = re.sub(r"https?://\S+", "[URL omitted]", value)
        value = re.sub(r"(?i)(?:sk-|bearer\s+|(?:token|password|cookie|api[_-]?key)\s*[=:]\s*)\S+", "[secret omitted]", value)
        return value[:900] or "Invalid arguments or unmet operation preconditions."
    return "The operation could not be completed. Check its status before trying again."


def error_result(name, code, message, *values):
    from .contracts import CONTRACT_VERSION, validate_error
    body = {"contract_version": CONTRACT_VERSION,
            "error": {"code": code, "operation": name, "message": message[:1000],
                      "recovery": "Correct invalid arguments using the tool schema. If an identifier is present, inspect that task/job or saved file before retrying; do not repeat a write to repair output formatting."}}
    ids = _identifiers(*values)
    if ids:
        body["identifiers"] = ids
    validate_error(body)
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(body, ensure_ascii=False, separators=(",", ":")))],
                          structuredContent=body, isError=True)


class PortableFastMCP(FastMCP):
    visible_tools = None
    descriptions = None

    async def list_tools(self):
        tools=await super().list_tools()
        if self.visible_tools is not None:
            tools=[tool for tool in tools if tool.name in self.visible_tools]
        for tool in tools:
            tool.inputSchema=portable_schema(tool.inputSchema)
            tool.outputSchema=advertised_output_schema(tool.name)
            if self.descriptions and tool.name in self.descriptions:
                tool.description=self.descriptions[tool.name]
        # A stable catalog helps host prompt caching across repeated connections.
        return sorted(tools,key=lambda tool:tool.name)


    async def call_tool(self, name, arguments):
        from .contracts import CONTRACT_VERSION, OutputValidationError, validate_result, validate_error
        if self._tool_manager.get_tool(name) is None:
            return error_result(name, "UNKNOWN_TOOL", "Choose an available tool from this connection.")
        raw = None
        try:
            # FastMCP/lowlevel bypass output validation for CallToolResult. Enforce
            # it here for both direct calls and study_more's nested call path.
            raw = await self._tool_manager.call_tool(name, arguments, context=self.get_context(), convert_result=False)
            if isinstance(raw, dict):
                raw = CallToolResult(content=[], structuredContent=raw)
            if not isinstance(raw, CallToolResult) or not isinstance(raw.structuredContent, dict):
                raise OutputValidationError("The tool returned no structured result object.")
            if raw.isError:
                validate_error(raw.structuredContent)
                # Error text must not disagree with its structured recovery receipt.
                content = [TextContent(type="text", text=json.dumps(raw.structuredContent, ensure_ascii=False, separators=(",", ":"), allow_nan=False))]
                content.extend(block for block in raw.content if block.type != "text")
                return raw.model_copy(update={"content": content})
            original = raw.structuredContent
            operation = arguments.get("tool") if name == "study_more" and arguments.get("mode") == "call" else name
            metadata = {"version": CONTRACT_VERSION, "operation": operation}
            if "_contract" in original and original["_contract"] != metadata:
                raise OutputValidationError("Output contract metadata does not match the called operation.")
            value = {**original, "_contract": metadata}
            validate_result(name, value)
            # One exact JSON text fallback, preserving separate media/resource
            # blocks and any non-JSON explanatory text.
            content = [TextContent(type="text", text=json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))]
            for block in raw.content:
                if block.type == "text":
                    try:
                        if json.loads(block.text) == original:
                            continue
                    except (ValueError, TypeError):
                        pass
                content.append(block)
            return raw.model_copy(update={"structuredContent": value, "content": content})
        except OutputValidationError as exc:
            value = raw.structuredContent if isinstance(raw, CallToolResult) else raw
            return error_result(name, "OUTPUT_VALIDATION_ERROR", str(exc), value, arguments)
        except Exception as exc:
            cause = exc
            for _ in range(8):
                if cause.__cause__ is None:
                    break
                cause = cause.__cause__
            code = "INVALID_ARGUMENT" if isinstance(cause, (ValidationError, ValueError)) else "TOOL_ERROR"
            return error_result(name, code, _safe_message(cause), arguments)
