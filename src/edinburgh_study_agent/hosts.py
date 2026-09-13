"""Generate private MCP configurations or merge one managed entry into an installed host."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .localization import normalize_locale

SERVER_NAME = "uoe-companion"
MODULE = "edinburgh_study_agent.server"
HOSTS = ("generic", "claude-desktop", "claude-code", "workbuddy", "deepseek-harness", "chatgpt-work")

def server_config(python, home, locale="auto", profile="student"):
    # Resolving a venv executable symlink selects the base interpreter instead.
    python, home = Path(os.path.abspath(python)), Path(home).resolve()
    if not python.is_file():
        raise ValueError("Install the private Python runtime first.")
    if profile not in ("daily", "student", "full"):
        raise ValueError("Choose daily, student or full tools.")
    return {"command":str(python),"args":["-m",MODULE],"env":{
        "PYTHONUTF8":"1","EDINBURGH_STUDY_HOME":str(home),
        "UOE_LOCALE":normalize_locale(locale),"UOE_TOOL_PROFILE":profile}}

def host_document(host, config):
    if host not in HOSTS:
        raise ValueError("Unknown host.")
    if host == "deepseek-harness":
        # JSON is valid YAML, and avoids YAML quoting/Windows path ambiguities.
        return [{"insert":[{"id":"mcp-uoe-companion","name":"@deepseek-ai/dsh-mcp-client",
            "config":{"serverName":SERVER_NAME,"transport":"stdio",**config,"toolCallTimeoutMs":60000}}]}]
    if host == "chatgpt-work":
        return {"setup_guide":"https://github.com/saigyujikingyo-png/edinburgh-study-agent/blob/main/docs/WORK_SETUP.md",
                "transport":"private Secure MCP Tunnel","uses_same_local_data":True,
                "surfaces":["ChatGPT Chat","ChatGPT local Work","ChatGPT cloud Work"],
                "binding_check":"python -m edinburgh_study_agent.chatgpt check",
                "note":"Install AND connect one private ChatGPT app. Existing connections are reused; a second local plugin is not required. Each Chat/Work mode needs its own model acceptance."}
    return {"mcpServers":{SERVER_NAME:config}}

def atomic_json(path, document):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor, temporary=tempfile.mkstemp(prefix=".uoe-",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8",newline="\n") as stream:
            json.dump(document,stream,ensure_ascii=False,indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def generate(directory, config, host="all"):
    directory=Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Choose a new or empty private output directory.")
    names=HOSTS if host=="all" else (host,)
    paths=[]
    for name in names:
        document=host_document(name,config)
        path=directory/(name+(".yaml" if name=="deepseek-harness" else ".json"))
        atomic_json(path,document)
        paths.append(str(path))
    return {"generated":paths,"host_configuration_changed":False,"contains_campus_credentials":False,
            "next_step":"Install/merge the host entry. DeepSeek: add this profile overlay to an existing Harness installation containing @deepseek-ai/dsh-mcp-client. Work: use the private connection guide."}

def configuration_path(host):
    if host=="workbuddy":
        return Path.home()/".workbuddy/mcp.json"
    if host=="claude-desktop":
        if sys.platform=="win32":
            if not os.environ.get("APPDATA"):
                raise ValueError("APPDATA is unavailable; specify --config-path.")
            return Path(os.environ["APPDATA"])/"Claude/claude_desktop_config.json"
        if sys.platform=="darwin":
            return Path.home()/"Library/Application Support/Claude/claude_desktop_config.json"
        raise ValueError("Claude Desktop path is not defined for this platform; use an explicit config path for a supported client.")
    raise ValueError("Only Claude Desktop and WorkBuddy have direct JSON merge installers. Claude Code uses its CLI; DeepSeek uses a profile overlay.")

def merge_config(path, config):
    path=Path(path)
    before=path.read_bytes() if path.exists() else None
    try:
        document=json.loads(before.decode("utf-8-sig")) if before is not None else {}
    except (ValueError,UnicodeError) as exc:
        raise ValueError("Existing host config is invalid JSON; it was not changed.") from exc
    if not isinstance(document,dict) or not isinstance(document.get("mcpServers",{}),dict):
        raise ValueError("Host config must contain an object named mcpServers; it was not changed.")
    servers=document.setdefault("mcpServers",{})
    managed=[key for key,value in servers.items() if isinstance(value,dict) and value.get("args")==["-m",MODULE]]
    if len(managed)>1:
        raise ValueError("Multiple UoE entries exist. Consolidate them before installing to avoid duplicate tools.")
    name=managed[0] if len(managed)==1 else SERVER_NAME
    if name in servers and name not in managed:
        raise ValueError("This host already has an unrelated uoe-companion entry. Resolve the name conflict before installing.")
    existing=servers.get(name,{})
    merged={**existing,**config,"env":{**existing.get("env",{}),**config["env"]}}
    if existing==merged:
        return {"path":str(path),"server_name":name,"changed":False,"backup":None,"acceptance":"configuration_only"}
    # Preserve existing custom fields (including client enable/disable flags).
    servers[name]=merged
    if (path.read_bytes() if path.exists() else None)!=before:
        raise ValueError("Host config changed concurrently. Retry the merge.")
    backup=None
    if before is not None:
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup=path.with_name(path.name+".uoe-"+stamp+".bak")
        with backup.open("xb") as stream:
            stream.write(before)
        if sys.platform!="win32":
            backup.chmod(0o600)
    atomic_json(path,document)
    return {"path":str(path),"server_name":name,"changed":True,"backup":str(backup) if backup else None,
            "acceptance":"configuration_only","next_step":"Restart or reload the host, then call study_status and study_help. Existing unrelated servers/settings were preserved."}

def doctor(config):
    """A protocol check, never a claim that a model used the tools."""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def check():
        params=StdioServerParameters(command=config["command"],args=config["args"],env=config["env"])
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                init=await session.initialize()
                catalog=await session.list_tools()
                status=await session.call_tool("study_status",{})
                help_result=await session.call_tool("study_help",{"topic":"languages","locale":"fr"})
                assert not status.isError and not help_result.isError
                names={tool.name for tool in catalog.tools}
                expected={"study_agenda","study_help","study_status","study_materials"}
                expected |= {"study_more"} if config["env"].get("UOE_TOOL_PROFILE")=="daily" else {"study_preferences","study_download_files"}
                assert expected <= names
                return {"server":init.serverInfo.name,"version":status.structuredContent["version"],
                        "tools":len(names),"tool_profile":config["env"].get("UOE_TOOL_PROFILE","full"),
                        "stdio_initialize_list_call":"passed","host_model_roundtrip":"not_tested",
                        "campus_login_checked":False}
    return asyncio.run(asyncio.wait_for(check(),timeout=45))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["generate","install","doctor"])
    parser.add_argument("--host",choices=[*HOSTS,"all"],default="all")
    parser.add_argument("--python",type=Path,default=Path(sys.executable))
    parser.add_argument("--home",type=Path,default=Path(os.environ.get("EDINBURGH_STUDY_HOME",Path.home()/".edinburgh-study-agent")))
    parser.add_argument("--locale",default="auto")
    parser.add_argument("--profile",choices=["daily","student","full"],default="student")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--config-path",type=Path)
    args=parser.parse_args()
    try:
        config=server_config(args.python,args.home,args.locale,args.profile)
        if args.action=="generate":
            stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            value=generate(args.output or args.home/"connections"/stamp,config,args.host)
        elif args.action=="doctor":
            value=doctor(config)
        elif args.host=="claude-code":
            executable=shutil.which("claude")
            if not executable:
                raise ValueError("Claude Code CLI is not installed. Generate its JSON configuration and merge it into the desired project's .mcp.json.")
            if Path(executable).suffix.lower() in (".cmd",".bat"):
                raise ValueError("Use the native Claude executable or merge the generated project JSON. Windows batch launchers require a shell and are not executed by this installer.")
            # Reviewed CLI-only boundary: trusted local executable, argument vector,
            # no shell, and no webpage/MCP tool parameters. Quoting the JSON again
            # would corrupt the actual argument; batch launchers are rejected above.
            subprocess.run([executable,"mcp","add-json","--scope","user",SERVER_NAME,json.dumps(config)],check=True,shell=False)  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit, python.lang.security.audit.dangerous-subprocess-use-tainted-env-args
            value={"host":"claude-code","acceptance":"configuration_only","next_step":"Run claude mcp get uoe-companion, then use the tools in Claude Code."}
        else:
            if args.host not in ("claude-desktop","workbuddy"):
                raise ValueError("Choose claude-desktop, claude-code or workbuddy for install. Other hosts use generate.")
            path=args.config_path or configuration_path(args.host)
            if not path.parent.exists() and args.config_path is None:
                raise ValueError("Host installation was not found. Install that client first or use generate.")
            value=merge_config(path,config)
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(value,ensure_ascii=False))

if __name__=="__main__":
    main()
