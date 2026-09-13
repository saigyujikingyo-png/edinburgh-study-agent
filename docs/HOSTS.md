# Connect your agent

UoE Companion is a student-focused MCP server. ChatGPT Chat/Work, Codex, Claude, WorkBuddy, DeepSeek Harness and other MCP clients use the same local core. Each person uses their own school account, data directory and connection. Switching clients on the same computer can reuse that person's campus session. Different people must not share it.

## Install once

Windows x64 students should use the [bundled setup ZIP](EASY_INSTALL.md): extract it, double-click Install.cmd and select their local agent. It includes Python and dependencies, merges WorkBuddy/Claude Desktop configuration with backups and enables the 13-tool daily profile. Other host documents are generated in the private connections folder. Chrome or Edge is required.

The following commands remain an optional developer/manual route. Install Python 3.11+ and Chrome, obtain the source release, then run `python scripts/install_runtime.py`. On Windows:

```powershell
$uoePython = Join-Path $env:USERPROFILE '.edinburgh-study-agent\runtime\Scripts\python.exe'
& $uoePython -m edinburgh_study_agent.hosts generate
& $uoePython -m edinburgh_study_agent.hosts doctor
```

On macOS/Linux the installed executable is `~/.edinburgh-study-agent/runtime/bin/python`; the same module arguments apply. Windows has live campus acceptance; Linux/Windows CI tests do not establish live macOS/Linux campus support.

`generate` writes six host documents into a new private directory and prints their paths. It does not change any client configuration. `doctor` starts the actual server and verifies MCP initialization, discovery and tool calls; it does not ask a model to use the tools or verify school login.

Use `--home` to select a separate private data directory, `--python` for an explicit installed Python executable, and `--locale fr-FR` for the initial language. Paths are passed as arguments, not shell expressions. Language and timezone preferences can later be managed in the agent.

## One ChatGPT plugin: Chat, local Work and cloud Work

Follow [Work setup](WORK_SETUP.md) to create your own private Secure MCP Tunnel and install/connect one UoE Companion in ChatGPT. Chat, desktop local Work and cloud Work use that same registered connection. The backend runs on your campus computer, which must remain on, signed in and online in all three modes. The cloud cannot reach arbitrary local stdio processes or loopback URLs. A second local marketplace package is optional for Codex development and is not required for the three ChatGPT modes. Existing users keep the connection and refresh its tool catalog after upgrading. No host browser is required for campus operations.

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

The 0.7.0 Windows wizard enables `UOE_TOOL_PROFILE=daily` for selected local agents: 13 direct tools, with advanced task/collection/calendar/service operations discovered and called through `study_more`. Original validation and private storage are retained. Existing student/full profiles remain valid; adding a daily menu does not remove their tools. The wizard does not silently change an existing ChatGPT connection's catalog.

New generated local-host entries use `UOE_TOOL_PROFILE=student`: 33 tools for students. It hides the three legacy developer tools `study_capture`, `study_download_resource` and `study_route`. `full` exposes 36 tools. Version 0.6.0 adds four basic workflow tools to both profiles, retaining existing tool names. Existing Work connections default to `full` for compatibility. Server descriptions and on-demand help apply without installing the Codex skill.

Ask in your preferred language, for example “Show my study agenda” or “显示本周学习日程”. Use `study_preferences(locale="auto")` to follow each request's language. See [language scope](LANGUAGES.md).

## Acceptance levels

| Client | Evidence | Remaining boundary |
| --- | --- | --- |
| ChatGPT Chat | 0.5.1: actual status and cached course lookup, repeated after removing the duplicate local entry | Cached lookup is not live school access |
| ChatGPT local Work | 0.5.1: user-created local Work called status and cached course lookup through the same registered connection; originator verified as codex_work_desktop | This local Work test did not repeat live refresh or download |
| ChatGPT cloud Work | 0.5.1: live Learn refresh, then status/cached lookup again after consolidation | Only tested account/service scope is established |
| Claude Desktop | Existing user configuration merged and backed up; same installed stdio runtime passes protocol checks | Application reload and a Claude model turn have not been verified |
| Claude Code | Portable entry and official-CLI installer implemented | CLI installation and model roundtrip not tested on the acceptance host |
| WorkBuddy | 0.5.2: a fresh Hy4 preview (high) conversation used one results call and returned all loaded years; source rows and year means were checked. See [measurements](WORKBUDDY_RESULTS.md). | The turn took 89.4 seconds and added unsupported interpretation; final summary/presentation guidance needs a new model test. This is not Terra max acceptance |
| DeepSeek Harness | Official bridge successfully discovered 28 tools, accepted schemas, executed multilingual catalog/preferences and task/agenda calls, rendered text and propagated errors | Registration/lifecycle fixture, not a full Harness agent/model turn |
| Generic MCP | Real stdio initialization/list/call checks for both tool profiles | Individual clients and model behavior require their own acceptance |

Configuration acceptance, protocol acceptance, official-bridge acceptance and a real model turn are separate claims. No other user's account is validated by the developer's result.

Version 0.6.0 student workflow backend/protocol measurements are recorded in [STUDENT_WORKFLOWS.md](STUDENT_WORKFLOWS.md). They do not certify a new WorkBuddy model turn or the new tools in every Chat/Work mode. Refresh the host MCP catalog once after upgrading; reuse the same entry, private data and campus login.

The 0.7.0 installer and daily-menu checks are recorded in [INSTALL_PERFORMANCE.md](INSTALL_PERFORMANCE.md). They are not a new Claude, DeepSeek, Codex or WorkBuddy model conversation. The installer generates a generic MCP document for Codex but does not rewrite Codex's global configuration. Normal runtime use does not require a coding checkout.

The installed Codex CLI's `codex mcp add --help` confirms the supported local registration route: `codex mcp add uoe-companion --env UOE_TOOL_PROFILE=daily --env EDINBURGH_STUDY_HOME=<private-directory> -- <installed-python> -m edinburgh_study_agent.server`. Pass each path as a properly quoted argument. Use this optional native CLI route only when you want a local stdio connection; keep an already-working registered ChatGPT/UoE connection instead of adding duplicates. This command's availability was checked locally; a new Codex model turn was not run.
