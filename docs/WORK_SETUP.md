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

Version 0.7.2 has 37 full-profile tools, 34 student-profile tools and a 14-tool daily menu with advanced discovery. Keep the existing ChatGPT connection and its catalog unless explicitly changing profiles. Server instructions and `study_help` supply workflows to hosts without the optional Codex skill.

## Deploy on another machine

1. On Windows x64, use the [bundled setup ZIP](EASY_INSTALL.md) to install the private backend without a separate Python installation. Chrome or Edge is required. The source installer remains a developer alternative. Do not register a second local marketplace plugin for normal ChatGPT use.
2. Create an authorised private Secure MCP Tunnel associated with your intended organisation/workspace.
3. Provide a tunnel Read + Use key locally; retain it in process environment or Windows DPAPI, never source files or chat.
4. Configure `scripts/Connect-Work.ps1` with the actual tunnel ID, official client and private runtime.
5. Verify with `Run-Work-Connection.ps1 -ConnectOnce`. Use `Enable-Work-Connection.ps1` for the current user's authorised logon connection.
6. Register one UoE Companion using that tunnel. Upload [`assets/icon-chatgpt.png`](../assets/icon-chatgpt.png) in the optional icon field before creating the entry (256 x 256 PNG, under 10 KB). Install/connect it in ChatGPT, refresh its tools and complete the campus login when required.
7. Test status and a bounded course query separately in Chat, local Work and cloud Work. See [acceptance](WORK_ACCEPTANCE.md) for current evidence.

The logon task runs with ordinary user permissions and maintains the connection; it does not periodically crawl school pages. No inbound public listener is opened. `Stop-Work-Connection.ps1` stops the connection and preserves private data. Upgrade the backend while jobs are idle, keep the private data directory and reconnect the existing registered app.

This remains a self-hosted deployment. Public-directory one-click installation, a hosted multi-user service and per-user campus onboarding within such a service are not implemented. Sharing the source or release does not share the author's private connection.

## If the remote icon is missing

Use `assets/icon-chatgpt.png` for the ChatGPT upload field. It is exported from the same original vector artwork as the full-size local icon. The 512-pixel `assets/icon.png` exceeds the creation form's 10 KB limit. A local plugin manifest or the MCP server's `icons` metadata does not establish that the remote listing has saved its own icon.

Use the existing entry's icon editor if available. If it is unavailable, obtain explicit approval before connecting a replacement entry or removing the old one. Reuse the same private tunnel and backend, verify the saved image after a reload, run the read-only host checks, then remove the approved old entry and retain one UoE Companion. Do not delete the campus profile or reinstall the backend to fix listing artwork.

A replacement has a new app identity. Existing conversations can retain the deleted app's tool mapping even after selecting the replacement tag. After retiring the old entry and setting the final name, validate a fresh ordinary Chat and fresh local/cloud Work tasks with the retained entry. Preserve failed legacy-task evidence; a successful call before deleting the old entry is not sufficient proof of the final identity. Update any optional private developer binding with a backup, without registering a second visible package.

## If tools are missing

Check whether the intended registered app is installed **and connected**, then refresh its catalog. A local icon, a visible list of tool names, or a healthy tunnel alone is not proof that a particular conversation can call the tools. Retry once if ChatGPT explicitly reports authentication completed and asks for a retry. Request a new campus login only after a live school job reports `needs_login`.

If the desktop reports **Could not use this project for a local chat** (Chinese: **无法将此项目用于本地聊天**) before starting a task, the host could not synchronise the selected ChatGPT project. First isolate plugin acceptance in a new local Work task from the home screen with no project selected. This does not repair project synchronisation; preserve the project and investigate its files/access separately. Do not erase the campus session or re-create the plugin in response to this host error.

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

Downloads remain on the campus computer. All three modes can request bounded text from verified supported files. Version 0.7.2 can also transfer verified original bytes through `study_export_files`; receiving-host materialisation and destination upload require separate acceptance. See [original-file delivery](FILE_DELIVERY.md). Source times, unavailable courses, external/LTI pages and incomplete coverage remain explicit. MyEd, Learn, EUCLID, MyCareerHub and Timetabler have reused the same campus login; that does not establish access to every provider.

The plugin reads supported pages and manages local records. It does not submit coursework, apply for internships, book events or alter enrolment. Private connection and acceptance details stay outside the release.

## Official references

- [Plugins across ChatGPT surfaces](https://learn.chatgpt.com/docs/plugins)
- [Choose local or cloud Work](https://learn.chatgpt.com/docs/get-started-with-work)
- [MCP in ChatGPT](https://learn.chatgpt.com/docs/extend/mcp)
- [Connect and test plugins](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

## Conversation and file-reference compatibility

If an existing Chat reports `FORBIDDEN: This conversation does not support developer MCPs`,
tool discovery and the campus connection can still be healthy. That conversation cannot
execute the developer tool. Use a host-supported conversation; do not reset school login
or duplicate the registered plugin to address the error. New task creation follows the
user's host workflow and permission rules.

For storage transfers, never send a `BlobResourceContents` object to a destination field
that declares a path string. Materialise the original bytes in the receiving environment,
verify them, then use that environment's declared file upload adapter. Do not invent
connector reference fields. The release acceptance record distinguishes failed inputs,
corrected host paths and actual destination readback.
