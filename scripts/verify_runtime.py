"""Verify a packaged MCP configuration and optionally import user-approved browser observations."""
import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))["mcpServers"]["edinburgh-study"]
    params = StdioServerParameters(command=config["command"], args=config["args"],
                                   env=dict(os.environ, **config.get("env", {})))
    report = {"at": datetime.now(timezone.utc).isoformat(), "config": str(args.config),
              "server_command": config["command"], "transport": "stdio"}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            catalog = await session.list_tools()
            report["tools"] = [t.name for t in catalog.tools]
            assert len(catalog.tools) == 36
            captures = []
            if args.observations:
                for obs in json.loads(args.observations.read_text(encoding="utf-8")):
                    result = await session.call_tool("study_capture", {"observation": obs})
                    if result.isError:
                        raise RuntimeError("Observation failed validation: " + str(result.content))
                    captures.append(result.structuredContent)
            report["captures"] = captures
            for label, arguments in (("courses", {"kind": "course"}),
                                     ("resources", {"kind": "resource"}),
                                     ("services", {"kind": "service"})):
                result = await session.call_tool("study_search", arguments)
                assert not result.isError and result.structuredContent is not None
                report[label] = result.structuredContent
            if report["resources"]["items"]:
                first = report["resources"]["items"][0]
                route = await session.call_tool("study_route", {"item_id": first["id"]})
                assert route.structuredContent["url"].startswith("https://")
                evidence = await session.call_tool("study_evidence", {"observation_id": first["observation_id"]})
                pages = [evidence.structuredContent["observation"]["text"]]
                while first.get("excerpt",first["title"]) not in "".join(pages) and evidence.structuredContent.get("has_more"):
                    evidence = await session.call_tool("study_evidence", {"observation_id": first["observation_id"],
                        "offset": evidence.structuredContent["next_offset"]})
                    assert not evidence.isError
                    pages.append(evidence.structuredContent["observation"]["text"])
                assert first.get("excerpt",first["title"]) in "".join(pages)
                report["resource_route_and_evidence_verified"] = True
            report["status"] = (await session.call_tool("study_status", {})).structuredContent
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            fresh = (await session.call_tool("study_status", {})).structuredContent
            assert fresh["counts"] == report["status"]["counts"]
            report["persistence_after_restart"] = True
    report["passed"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "tools": len(report["tools"]), "counts": report["status"]["counts"],
                      "persistence_after_restart": True, "report": str(args.report)}))
asyncio.run(main())
