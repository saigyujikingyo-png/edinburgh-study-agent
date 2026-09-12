# ChatGPT Work setup

Codex develops the plugin. ChatGPT Work is the usage and acceptance environment.

## Architecture

Work → private Secure MCP Tunnel → local MCP runtime → plugin-owned persistent Chrome profile and verified file store.

The Work cloud browser does not need access to personal Chrome. Complete campus sign-in and MFA in the plugin's dedicated local window when `study_connect_school` is requested. The browser retains its own profile; no cookies, passwords, browser storage or tokens are exported to the model. Later jobs run without a visible window.

A session may expire under university policy. MyEd, Learn, EUCLID, MyCareerHub and Timetabler have reused the same campus login. The core query/download/read/collection/task flows passed actual Work tests; this does not establish access to all external providers.

## Normal usage

Select the connected UoE Companion in Work. Ask for the desired school task. For live information use the automatic tools and poll their jobs. A local personal Codex marketplace reference is not the Work connection.

- Courses/files: `study_live_courses`, `study_live_resources`, `study_download_files`.
- Reading: `study_read_resource`, `study_read_file`, `study_evidence`.
- School-wide: `study_services`, `study_read_service`, `study_search`.
- Organisation: `study_home`, `study_collect`, `study_collections`, task and study-plan tools.

The tool catalog contains 28 operations. Refresh the catalog in Work's plugin settings after upgrading the runtime. Previous chat messages about a missing local plugin or requiring cloud-browser login describe the old architecture.

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
