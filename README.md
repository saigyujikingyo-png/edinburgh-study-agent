# Edinburgh Study Agent

[English](#what-it-does) · [中文](#中文说明) · [Work setup](docs/WORK_SETUP.md) · [GitHub references](docs/GITHUB_REFERENCES.md)

Manage University of Edinburgh coursework and web resources through natural language in **ChatGPT Work** or a local MCP host. **Codex is the development environment.** This is an independent student project, not a University or Anthology product.

## 中文说明

登录一次学校后，在 Work 内集中查课程、课件、EUCLID、课表、活动和实习就业信息，整理收藏、标签、待办和学习计划。

- 后续操作复用插件专属校园会话；无需截图、视觉点击或逐文件“另存为”。
- 课件直接保存到本机，校验完整性后可读取 PDF、Word、PowerPoint 和 Excel 文本。
- 收录 17 项学校服务，逐项说明访问时间和覆盖范围。目录入口不等于所有功能都已接入。
- 校园会话可能过期；届时只在本机学校页面重新登录和完成 MFA。

示例：“刷新今年课程并下载课程手册”“查近期学校活动和实习信息，把感兴趣的加入收藏”“核对 EUCLID 正式课程”“读取课件，帮我安排本周学习”。

## What it does

Version 0.3.0 exposes **28 MCP tools**:

| Area | Available behavior |
| --- | --- |
| Learn | Read paginated courses and supported nested content; search, download and verify original attachments |
| MyEd / EUCLID | Reuse campus SSO and read supported student-record sections |
| Timetabler | Read the displayed timetable page; a complete structured timetable import is not implemented |
| Careers and events | Read supported official pages and authenticated MyCareerHub links; bounded observed-link discovery |
| Central workspace | Search dated evidence, organise collections and tags, manage local tasks and study plans |
| Documents | Read bounded text from verified PDF, DOCX, PPTX, XLSX and supported text downloads |
| Calendars | Import an existing local ICS export and create a local ICS file; no automatic feed subscription |

The directory contains MyEd, Learn, EUCLID, enrolments, Timetabler, DRPS, library, reading lists, past papers, Media Hopper, careers, internships, MyCareerHub, career events, university events, EUSA and registry support.

Live campus acceptance covered the core supported Work flows on 2026-09-11. Other providers, hidden/LTI content and features not exercised remain explicitly unverified. See [acceptance scope](docs/WORK_ACCEPTANCE.md).

## Install from source

The validated campus host is Windows with Python 3.12 and Google Chrome. Python 3.11+ is required. The portable core can be used from another MCP host; the supplied private Work connection scripts use Windows DPAPI and Task Scheduler.

~~~powershell
git clone https://github.com/saigyujikingyo-png/edinburgh-study-agent.git
cd edinburgh-study-agent
python scripts/install_runtime.py
~~~

The installer creates a private runtime under ~/.edinburgh-study-agent/runtime and writes ~/.edinburgh-study-agent/mcp.json. It prints the path to that host-local configuration. Merge its one server entry into your local MCP host, or follow [Work setup](docs/WORK_SETUP.md). It does not change a host's whole configuration or the checkout's portable .mcp.json.

For a separate extracted Codex plugin, the installer accepts --plugin-path pointing to that plugin directory. The runtime is installed from the current source, so an old wheel in dist cannot silently replace newer code. Use --locked to reproduce the recorded development dependency snapshot.

## How Work reaches your resources

Work → authorised private Secure MCP Tunnel → local MCP runtime → dedicated school browser and verified file store.

Your computer must be on, signed in and online. Complete campus sign-in and MFA only in the plugin's dedicated local window. Later jobs use structural DOM access without screenshots or coordinate clicks. The browser profile stays local; credentials, cookies and signed URLs are not returned to the agent.

Downloaded files, evidence, collections and tasks stay under ~/.edinburgh-study-agent. Work can request supported document text through tools; a local path is not a cloud attachment. No telemetry is sent by this project.

The tools do not submit coursework, change enrolment, send messages, apply for jobs or book events. A local task marked done is not an official submission.

## Development and release

~~~powershell
python -m pip install -e ".[dev]"
python -m playwright install chrome
python -m pytest -q
python scripts/smoke_mcp.py
python scripts/public_release.py
python scripts/package_plugin.py
~~~

Tests use synthetic pages and isolated data; they do not require campus credentials. CI checks Windows and Linux, Python 3.11 and 3.12. The publication check also audits the Git index, so staged private data is rejected even if the working file was subsequently cleaned.

See [contributing](CONTRIBUTING.md), [security and privacy](SECURITY.md), [verification](VERIFICATION.md), and [release checklist](docs/RELEASING.md).

## License and references

Original project code is available under the [MIT License](LICENSE). Dependencies retain their respective licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).

The GitHub review considered [BlackboardSync](https://github.com/sanjacob/BlackboardSync), [bblearn](https://github.com/sanjacob/bblearn), the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), and [Playwright for Python](https://github.com/microsoft/playwright-python). The [reference record](docs/GITHUB_REFERENCES.md) distinguishes existing dependencies, design references and future work. No BlackboardSync or bblearn code is included.
