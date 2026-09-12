# Connect your agent

UoE Companion is a student-focused MCP server. Codex develops it; ChatGPT Work, Claude, WorkBuddy, DeepSeek Harness and other MCP clients use the same local core. Each person uses their own school account, data directory and connection. Switching clients on the same computer can reuse that person's campus session. Different people must not share it.

## Install once

Install Python 3.11+ and Google Chrome, download the release, then run `python scripts/install_runtime.py` from the extracted project. On Windows:

```powershell
$uoePython = Join-Path $env:USERPROFILE '.edinburgh-study-agent\runtime\Scripts\python.exe'
& $uoePython -m edinburgh_study_agent.hosts generate
& $uoePython -m edinburgh_study_agent.hosts doctor
```

On macOS/Linux the installed executable is `~/.edinburgh-study-agent/runtime/bin/python`; the same module arguments apply. Windows has live campus acceptance; Linux/Windows CI tests do not establish live macOS/Linux campus support.

`generate` writes six host documents into a new private directory and prints their paths. It does not change any client configuration. `doctor` starts the actual server and verifies MCP initialization, discovery and tool calls; it does not ask a model to use the tools or verify school login.

Use `--home` to select a separate private data directory, `--python` for an explicit installed Python executable, and `--locale fr-FR` for the initial language. Paths are passed as arguments, not shell expressions. Language and timezone preferences can later be managed in the agent.

## ChatGPT Work

Follow [Work setup](WORK_SETUP.md) to create your own private Secure MCP Tunnel. Work cannot reach an arbitrary local stdio process or a loopback URL on your computer. The computer must remain on, signed in and online. Existing Work users keep their connection and refresh its tool catalog after upgrading. No Work browser is required for campus operations.

## Claude Desktop

```powershell
& $uoePython -m edinburgh_study_agent.hosts install --host claude-desktop
```

The installer merges one managed entry into `%APPDATA%/Claude/claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS. It preserves other servers/settings, keeps an exact local backup before changes and is idempotent. It refuses invalid JSON and unrelated entries with a conflicting name. Existing disabled flags are preserved. Restart/reload Claude Desktop after changing its configuration.

Source: [official local-server connection guide](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers).

## Claude Code

If the `claude` command is installed:

```powershell
& $uoePython -m edinburgh_study_agent.hosts install --host claude-code
claude mcp get uoe-companion
```

This uses the official `claude mcp add-json --scope user` command with a native executable. Windows `.cmd`/`.bat` launchers are refused because they require shell interpretation; use the generated JSON option in that case. Alternatively, merge the generated `claude-code.json` entry into the selected project's `.mcp.json`; do not replace unrelated entries or hand-edit Claude Code's internal global storage. The CLI owns conflict handling.

Source: [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

## WorkBuddy

```powershell
& $uoePython -m edinburgh_study_agent.hosts install --host workbuddy
```

This merges the managed entry into `~/.workbuddy/mcp.json`, preserving other servers/settings and making a local backup. Reload its MCP configuration or restart WorkBuddy. A project-specific `.workbuddy/mcp.json` can override the user setting, so check that layer when a client reports an unexpected server.

Source: [WorkBuddy MCP guide](https://www.workbuddy.ai/docs/zh/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide).

## DeepSeek Agent / official Harness

The target is [DeepSeek AI's official Harness](https://github.com/deepseek-ai/deepseek-harness), using `@deepseek-ai/dsh-mcp-client`. This is not an integration with the DeepSeek chat website or an arbitrary wrapper around its API.

The generated `deepseek-harness.yaml` is a Cordis `insert` overlay containing an absolute stdio command and this person's local data directory. JSON syntax is used because it is also valid YAML and preserves Windows paths reliably. In an existing Harness installation that includes the official MCP client:

```powershell
dsh web --no-open --patch '<generated private path>/deepseek-harness.yaml'
```

To persist it, merge that single `insert` entry into the desired user/profile patch layer. Do not replace an existing patch file. The official bridge namespaces tools as `mcp__uoe-companion__study_*`. It consumes tools; UoE's workflows and language instructions are therefore available through `study_help`, without requiring host-specific skills, MCP resources or prompts.

The supported schema subset is narrower than general MCP. UoE advertises disjoint nullable fields with `oneOf`, expands local schema references, removes repetitive field titles, and describes unsupported bound/format keywords in text. Pydantic still enforces the original constraints when tools run. A malformed call returns a real error. Reconnection behavior varies by Harness version; this project does not override its transport supervisor.

References: [official MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md), [official overlay guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/mcp-memory.md). The 2026-09-12 bridge probe used published package `0.0.1-rc.1`; current source and npm tags may differ while Harness is in developer preview.

## Student tools and language

New generated local-host entries use `UOE_TOOL_PROFILE=student`: 28 tools for students. It hides the three legacy developer tools `study_capture`, `study_download_resource` and `study_route`. `full` exposes 31 tools, including all 28 pre-0.5 IDs and three new tools. Existing Work connections default to `full` for compatibility. Server descriptions and on-demand help apply without installing the Codex skill.

Ask in your preferred language, for example “Show my study agenda” or “显示本周学习日程”. Use `study_preferences(locale="auto")` to follow each request's language. See [language scope](LANGUAGES.md).

## Acceptance levels

| Client | Evidence in 0.5.0 | Remaining boundary |
| --- | --- | --- |
| ChatGPT Work | Existing private connection upgraded; new catalog discovered; see the actual acceptance record | Only tested account/service scope is established |
| Claude Desktop | Existing user configuration merged and backed up; same installed stdio runtime passes protocol checks | Application reload and a Claude model turn have not been verified |
| Claude Code | Portable entry and official-CLI installer implemented | CLI installation and model roundtrip not tested on the acceptance host |
| WorkBuddy | Existing user configuration merged and backed up; same installed stdio runtime passes protocol checks | Application reload and a WorkBuddy model turn have not been verified |
| DeepSeek Harness | Official bridge successfully discovered 28 tools, accepted schemas, executed multilingual catalog/preferences and task/agenda calls, rendered text and propagated errors | Registration/lifecycle fixture, not a full Harness agent/model turn |
| Generic MCP | Real stdio initialization/list/call checks for both tool profiles | Individual clients and model behavior require their own acceptance |

Configuration acceptance, protocol acceptance, official-bridge acceptance and a real model turn are separate claims. No other user's account is validated by the developer's result.
