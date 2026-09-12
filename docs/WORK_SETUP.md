# ChatGPT Chat and cloud Work setup

Codex develops the plugin. ChatGPT Work is the usage and acceptance environment.

## Architecture

Work → private Secure MCP Tunnel → local MCP runtime → plugin-owned persistent Chrome profile and verified file store.

The Work cloud browser does not need access to personal Chrome. Complete campus sign-in and MFA in the plugin's dedicated local window when `study_connect_school` is requested. The browser retains its own profile; no cookies, passwords, browser storage or tokens are exported to the model. Later jobs run without a visible window.

A session may expire under university policy. MyEd, Learn, EUCLID, MyCareerHub and Timetabler have reused the same campus login. The core query/download/read/collection/task flows passed actual Work tests; this does not establish access to all external providers.

## Normal usage

Install **and connect** the personal UoE Companion in ChatGPT Plugins. The same connected tools can then be used in Chat and cloud Work. Select that connected UoE Companion. Ask for the desired school task. For live information use the automatic tools and poll their jobs. A local personal Codex marketplace reference is not the Work connection.

- Courses/files: `study_live_courses`, `study_live_resources`, `study_download_files`.
- Reading: `study_read_resource`, `study_read_file`, `study_evidence`.
- School-wide: `study_services`, `study_read_service`, `study_search`.
- Organisation: `study_home`, `study_collect`, `study_collections`, task and study-plan tools.

The full tool catalog contains 31 operations; the student profile contains 28. Refresh the catalog in Work's plugin settings after upgrading the runtime. Previous chat messages about a missing local plugin or requiring cloud-browser login describe the old architecture.

## Deploy on another machine

1. Install Chrome, the source/plugin package and its private Python runtime with `scripts/install_runtime.py`.
2. Create an authorised private Secure MCP Tunnel associated only with the intended organisation/workspace.
3. Provide a tunnel Read + Use key locally; retain it in process environment or Windows DPAPI, never source files or chat.
4. Configure `scripts/Connect-Work.ps1` with the actual tunnel ID, official tunnel client and private runtime.
5. Verify with `Run-Work-Connection.ps1 -ConnectOnce`. Use `Enable-Work-Connection.ps1` for the current user's authorised logon connection.
6. Register/connect the plugin in Work using that tunnel, refresh tools and complete one local campus login.
7. Test the actual Work workflow, not just the transport.

The logon task runs with the current user's ordinary permissions. It maintains the private connection, not periodic school crawling. No inbound public listener is opened. `Stop-Work-Connection.ps1` stops this plugin's connection and preserves private data.

## Boundaries

Files remain on the local computer. Work can request bounded text from verified supported documents; local paths do not constitute cloud attachments. Session policies, unavailable courses, external/LTI resources, scanned PDFs and unsupported interactive pages must be reported per result.

A website entry or login page is not proof of authenticated student data. The plugin reads supported pages and manages local records; it does not submit coursework, apply for internships, book events or alter enrolment.

Connection IDs and private acceptance details are kept under `~/.edinburgh-study-agent/acceptance`, outside the distribution.

## Official references

- [Work MCP extensions](https://learn.chatgpt.com/docs/extend/mcp)
- [Connect and test ChatGPT plugins](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Playwright persistent browser context](https://playwright.dev/python/docs/api/class-browsertype)

## Installation and connection are separate

If the model says no course-reading interface was provided, check the ChatGPT connection before asking for a new school login. An installed local personal-marketplace package can supply the icon and skills while its stdio server is unavailable to the cloud. A healthy tunnel also does not prove the ChatGPT app is installed or connected.

1. In ChatGPT, open the **personal registered UoE Companion connection**, install it, and complete **Connect**. Seeing the tool catalog alone is insufficient.
2. Bind the existing local plugin package to **your own** registered app. Run the following in the private installed runtime, replacing the two arguments with your actual connection ID and separate installed plugin copy:

```text
python -m edinburgh_study_agent.chatgpt bind --plugin-path <private-installed-plugin> --app-id <your-registered-app-id>
```

The command writes `.app.json` and the `apps` manifest reference only into that private copy. It stores the association outside the package, backs up changed files, preserves local MCP configuration and other app dependencies, and refuses Git checkouts or an already bound different identity. It does **not** claim to install/authenticate the cloud app. Reinstall that private marketplace plugin using the host's normal update flow so new conversations pick up its dependency.

`python -m edinburgh_study_agent.chatgpt check` checks the saved association. Its cloud connection and model acceptance fields deliberately remain `not_checked`; actual model calls are required. When upgrading with `scripts/install_runtime.py --plugin-path <private-installed-plugin>`, the installer reapplies the saved association. Initial binding can also be supplied via `--chatgpt-app-id`.

3. In both a Chat conversation and a cloud Work task, call `study_status` and a bounded `study_search`. For current course access, run `study_live_courses` and wait for its job. Record fresh results separately from cached results. If ChatGPT returns an authentication-completed/retry response, retry once after connection succeeds; do not start another campus login for that host-side response.

Keep the private plugin copy and its app binding on your own machine. Share the audited public release, not the locally bound package. Every other person registers and binds their own connection. This is not a public hosted multi-user service or an official-directory one-click distribution.

The campus computer must remain on and the tunnel online for Chat or cloud Work to read that person's local session/files. A cloud conversation does not move the campus runtime into the cloud.

Official source: [MCP in ChatGPT](https://learn.chatgpt.com/docs/extend/mcp) and [connect and test plugins](https://developers.openai.com/plugins/deploy/connect-chatgpt).
