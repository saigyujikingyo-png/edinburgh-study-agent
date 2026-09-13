"""Measure real MCP startup/catalog/status with isolated empty data, never model billing."""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(python, profile, runs):
    samples = []
    with tempfile.TemporaryDirectory(prefix="uoe-benchmark-") as temporary:
        for attempt in range(runs):
            params = StdioServerParameters(command=str(python), args=["-m", "edinburgh_study_agent.server"],
                env={"PYTHONUTF8":"1", "UOE_TOOL_PROFILE":profile,
                     "EDINBURGH_STUDY_HOME":str(Path(temporary)/str(attempt))})
            begin = time.perf_counter()
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    init = await session.initialize()
                    catalog = await session.list_tools()
                    startup = (time.perf_counter()-begin)*1000
                    begin = time.perf_counter()
                    status = await session.call_tool("study_status", {})
                    elapsed = (time.perf_counter()-begin)*1000
                    assert not status.isError
                    encoded = json.dumps([t.model_dump(exclude_none=True) for t in catalog.tools], ensure_ascii=False, separators=(",",":")).encode()
                    samples.append({"startup_ms":round(startup,2),"status_ms":round(elapsed,2),
                        "tools":len(catalog.tools),"catalog_utf8_bytes":len(encoded),
                        "instructions_utf8_bytes":len((init.instructions or "").encode()),
                        "status_text_utf8_bytes":sum(len(c.text.encode()) for c in status.content if c.type=="text"),
                        "version":status.structuredContent["version"]})
    return {"profile":profile,"samples":samples,
            "median_startup_ms":statistics.median(s["startup_ms"] for s in samples),
            "median_status_ms":statistics.median(s["status_ms"] for s in samples),
            "model_turn":"not_run","billing_tokens":"unavailable",
            "scope":"MCP initialize/list/status with isolated empty data. UTF-8 bytes are not billable tokens."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python",type=Path,default=Path(sys.executable))
    parser.add_argument("--profile",choices=["daily","student","full"],default="daily")
    parser.add_argument("--runs",type=int,default=3)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not 1<=args.runs<=10:parser.error("runs must be 1..10")
    value=asyncio.run(run(args.python,args.profile,args.runs))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(value))


if __name__=="__main__":main()
