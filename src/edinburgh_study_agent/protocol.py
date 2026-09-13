"""Advertise a conservative schema subset while retaining Pydantic call validation."""
from copy import deepcopy
from mcp.server.fastmcp import FastMCP

CONSTRAINTS={"minimum","maximum","exclusiveMinimum","exclusiveMaximum","multipleOf",
             "minLength","maxLength","minItems","maxItems","pattern","format"}
KEYWORDS={"type","oneOf","properties","required","additionalProperties","items","enum","const",
          "description","default","examples"}

def portable_schema(schema):
    definitions=schema.get("$defs",{})
    def convert(node, stack=()):
        node=deepcopy(node)
        if "$ref" in node:
            ref=node.pop("$ref")
            if not ref.startswith("#/$defs/") or ref in stack:
                raise ValueError("Only acyclic local schema references can be advertised.")
            key=ref.removeprefix("#/$defs/")
            node={**convert(definitions[key],(*stack,ref)),**node}
        node.pop("$defs",None)
        # Generated field titles repeat the parameter name and cost prompt tokens.
        node.pop("title",None)
        if "anyOf" in node:
            alternatives=node.pop("anyOf")
            kinds=[part.get("type") for part in alternatives]
            # Nullable optional fields have disjoint alternatives: oneOf preserves meaning.
            if len(alternatives)!=2 or kinds.count("null")!=1 or None in kinds:
                raise ValueError("Only disjoint nullable unions can be converted to portable oneOf.")
            node["oneOf"]=alternatives
        constraints=[f"{key}={node.pop(key)}" for key in sorted(CONSTRAINTS & node.keys())]
        if constraints:
            # These constraints remain enforced by the server even when a host's
            # schema interpreter cannot enforce their keywords during generation.
            node["description"]=(node.get("description","")+" Server validates: "+", ".join(constraints)+".").strip()
        unknown=node.keys()-KEYWORDS
        if unknown:
            raise ValueError("Unsupported schema keywords: "+", ".join(sorted(unknown)))
        if "properties" in node:
            node["properties"]={key:convert(value,stack) for key,value in node["properties"].items()}
        if "items" in node:
            node["items"]=convert(node["items"],stack)
        if "oneOf" in node:
            node["oneOf"]=[convert(part,stack) for part in node["oneOf"]]
        return node
    return convert(schema)

class PortableFastMCP(FastMCP):
    visible_tools = None
    descriptions = None

    async def list_tools(self):
        tools=await super().list_tools()
        if self.visible_tools is not None:
            tools=[tool for tool in tools if tool.name in self.visible_tools]
        for tool in tools:
            tool.inputSchema=portable_schema(tool.inputSchema)
            if self.descriptions and tool.name in self.descriptions:
                tool.description=self.descriptions[tool.name]
        # A stable catalog helps host prompt caching across repeated connections.
        return sorted(tools,key=lambda tool:tool.name)
