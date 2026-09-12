# One UoE Companion for Chat, local Work and cloud Work

Codex develops the plugin. ChatGPT Chat, desktop local Work and cloud Work use one installed, connected UoE Companion. Each person has their own connection, campus session and data.

## Architecture

Chat / local Work / cloud Work → one registered UoE Companion → private Secure MCP Tunnel → campus computer's MCP runtime → plugin-owned campus profile and file store.

The computer must remain on, signed in and online in all three modes. A cloud conversation does not move the campus runtime into the cloud. The local backend is a component of the plugin; it does not need a second visible marketplace entry.

Complete campus sign-in and MFA in the dedicated local window when a live job reports `needs_login`. The profile remains on the campus computer; no cookies, passwords, browser storage or tokens are exported to the model. Later jobs use structured DOM and direct HTTP without screenshots, coordinate clicks or Save As dialogs. University policy may require reauthentication.

## Normal usage

1. Install **and connect** your registered UoE Companion in ChatGPT Plugins.
2. Use that same entry in ordinary Chat, or choose Work and select **Work locally** or **Cloud** in the desktop composer when available. Web Work runs in the cloud. Mode availability depends on the host/account.
3. Ask for the school task. No duplicate local Codex marketplace entry is needed for these modes.

- Courses/files: `study_live_courses`, `study_live_resources`, `study_download_files`.
- Reading: `study_read_resource`, `study_read_file`, `study_evidence`.
- School resources: `study_services`, `study_read_service`, `study_search`.
- Organisation: `study_home`, collections, tasks, agenda and study-plan tools.

The full catalog has 31 operations; the student profile has 28. Refresh the registered plugin's tool catalog after runtime upgrades. Server instructions and `study_help` supply workflows to hosts without the optional Codex skill.

## Deploy on another machine

1. Install Chrome and Python 3.11+, obtain the public release, then run `python scripts/install_runtime.py` to install the private backend. Do not register a second local marketplace plugin for normal ChatGPT use.
2. Create an authorised private Secure MCP Tunnel associated with your intended organisation/workspace.
3. Provide a tunnel Read + Use key locally; retain it in process environment or Windows DPAPI, never source files or chat.
4. Configure `scripts/Connect-Work.ps1` with the actual tunnel ID, official client and private runtime.
5. Verify with `Run-Work-Connection.ps1 -ConnectOnce`. Use `Enable-Work-Connection.ps1` for the current user's authorised logon connection.
6. Register one UoE Companion using that tunnel, install/connect it in ChatGPT, refresh its tools and complete the campus login when required.
7. Test status and a bounded course query separately in Chat, local Work and cloud Work. See [acceptance](WORK_ACCEPTANCE.md) for current evidence.

The logon task runs with ordinary user permissions and maintains the connection; it does not periodically crawl school pages. No inbound public listener is opened. `Stop-Work-Connection.ps1` stops the connection and preserves private data. Upgrade the backend while jobs are idle, keep the private data directory and reconnect the existing registered app.

This remains a self-hosted deployment. Public-directory one-click installation, a hosted multi-user service and per-user campus onboarding within such a service are not implemented. Sharing the source or release does not share the author's private connection.

## If tools are missing

Check whether the intended registered app is installed **and connected**, then refresh its catalog. A local icon, a visible list of tool names, or a healthy tunnel alone is not proof that a particular conversation can call the tools. Retry once if ChatGPT explicitly reports authentication completed and asks for a retry. Request a new campus login only after a live school job reports `needs_login`.

For acceptance, actually call `study_status` and `study_search(kind="course", limit=1)` in each mode. For current course access, run `study_live_courses` and wait for its job. Keep cached and live evidence separate. A local MCP protocol check or a Codex development task does not replace a local Work model turn.

If a previous installation shows two UoE entries, retain the registered ChatGPT connection. With the user's removal authorisation, uninstall only the duplicate local marketplace package and remove only its available catalog entry. Preserve the backend, campus profile, files and registered connection. Reload the catalog and repeat the mode checks.

## Optional Codex developer package

Developers who deliberately use a separate local marketplace package can associate it with their own registered app:

```text
python -m edinburgh_study_agent.chatgpt bind --plugin-path <private-installed-plugin> --app-id <your-registered-app-id>
```

This writes `.app.json` and its manifest reference only into the separate private copy, preserves MCP configuration, makes backups and refuses Git checkouts or conflicting identities. It does not install or authenticate the cloud app. Only developers using this optional package should reinstall that private marketplace entry to load the dependency; this can display an additional local entry.

`python -m edinburgh_study_agent.chatgpt check` reports association configuration, with cloud/model verification deliberately `not_checked`. Upgrades with `--plugin-path` preserve the saved association. Keep bound private copies out of public releases. No binding command is required for the normal single-entry ChatGPT route.

## Scope and files

Files remain on the campus computer. All three modes can request bounded text from verified supported files; local paths are not cloud attachments. Source times, unavailable courses, external/LTI pages and incomplete coverage remain explicit. MyEd, Learn, EUCLID, MyCareerHub and Timetabler have reused the same campus login; that does not establish access to every provider.

The plugin reads supported pages and manages local records. It does not submit coursework, apply for internships, book events or alter enrolment. Private connection and acceptance details stay outside the release.

## Official references

- [Plugins across ChatGPT surfaces](https://learn.chatgpt.com/docs/plugins)
- [Choose local or cloud Work](https://learn.chatgpt.com/docs/get-started-with-work)
- [MCP in ChatGPT](https://learn.chatgpt.com/docs/extend/mcp)
- [Connect and test plugins](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
