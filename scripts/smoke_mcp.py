"""Exercise the real stdio MCP protocol in an isolated data directory."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from jsonschema import Draft202012Validator

async def run():
    with tempfile.TemporaryDirectory(prefix="edinburgh-mcp-test-") as data:
        env = dict(os.environ, EDINBURGH_STUDY_HOME=data, PYTHONUTF8="1")
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name("run_server.py"))], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized=await session.initialize()
                assert initialized.serverInfo.name=="UoE Companion"
                assert initialized.serverInfo.icons[0].mimeType=="image/png"
                tools = await session.list_tools()
                assert len(tools.tools) == 36
                schemas = {tool.name: tool.outputSchema for tool in tools.tools}
                for schema in schemas.values():
                    assert schema and schema.get("type") == "object"
                    Draft202012Validator.check_schema(schema)
                state = await session.call_tool("study_status", {})
                assert not state.isError and state.structuredContent["live_connection_checked"] is False
                created = await session.call_tool("study_task_create",
                    {"title": "Synthetic MCP acceptance task", "estimate_minutes": 30})
                assert not created.isError
                task_id = created.structuredContent["id"]
                finished = await session.call_tool("study_task_update", {"task_id": task_id, "status": "done"})
                assert finished.structuredContent["university_submission_changed"] is False
                bad = await session.call_tool("study_route", {"target": "not-a-route"})
                assert bad.isError and bad.structuredContent["error"]["code"] == "INVALID_ARGUMENT"
                for name, reply in (("study_status", state), ("study_task_create", created),
                                    ("study_task_update", finished), ("study_route", bad)):
                    Draft202012Validator(schemas[name]).validate(reply.structuredContent)
                    assert json.loads(reply.content[0].text) == reply.structuredContent
                assert state.structuredContent["_contract"] == {"version": "1", "operation": "study_status"}
                print(json.dumps({"passed": True, "transport": "stdio", "tool_count": len(tools.tools),
                    "structured_results": True, "output_schemas": True, "text_parity": True, "local_task_round_trip": True,
                    "invalid_tool_request_rejected": True, "data": "isolated synthetic fixture"}))
asyncio.run(run())
