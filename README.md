<p align="center"><img src="assets/icon.svg" width="112" alt="UoE Companion icon"></p>

# UoE Companion

Manage University of Edinburgh courses, materials and personal study workflows through your preferred AI agent. Independent open-source student project; not a University product.

**[Download the Windows x64 student preview](https://github.com/saigyujikingyo-png/edinburgh-study-agent/releases/tag/v0.8.1)** · [Easy installation](docs/EASY_INSTALL.md) · [Agent compatibility](docs/HOSTS.md) · [NMR acquisition](docs/NMR.md)

## Install and start

1. Download `UoE-Companion-0.8.1-Windows-x64.zip` and extract the entire ZIP.
2. Double-click **Install.cmd**. In the local setup page, select WorkBuddy or Claude Desktop and choose **Install / update**. Python and plugin dependencies are included; no Git, terminal commands or development checkout are required for this route.
3. Reload the selected agent's MCP connection. Sign in to the University in the dedicated window when needed; password and MFA stay on the school page.
4. Ask, for example, "Show my classes this semester" or "Find this course's lecture notes and read the first file".

Google Chrome or Microsoft Edge must be installed. The wizard reuses existing private data and account connections. It verifies package files, runs an isolated MCP check and backs up changed host configurations. [Update, recovery and removal](docs/EASY_INSTALL.md).

**ChatGPT Chat, local Work and cloud Work** share one personal UoE connection. Existing connections are preserved. New accounts still need the platform's private connection setup and account permissions; the Windows installer cannot grant those. The campus computer must remain online for cloud Work. [ChatGPT setup](docs/WORK_SETUP.md).

**DeepSeek Harness, Claude Code, Codex and other MCP hosts** use the same core. The wizard generates private configuration files; their client-specific setup is described in [HOSTS.md](docs/HOSTS.md). Installing a configuration is not proof of a successful model conversation.

## Student workflows

| Request | Implemented coverage |
| --- | --- |
| Courses and results | Learn membership/content discovery and own EUCLID course marks across loaded academic years; not an official transcript |
| Personal timetable | Published personal Timetabler activities, year/semester/week/date filters and exact occurrence dates; incomplete exam/allocation coverage remains explicit |
| Course timetable PDF | Verified download, labelled week/day extraction and cached summaries; request a particular week for full cells. Course grids do not prove personal group allocations or calendar dates |
| Original file delivery | Export selected cached originals as file attachments or a ZIP with a manifest; validate size/SHA-256 before delivery. A destination upload is complete only after its own receipt and readback |
| Course materials | Name/id resolution, bounded folder search, verified downloads and PDF/Office/text reading; ambiguous results return choices |
| Learn updates | Loaded activity rows and course unread counters; full conversation bodies and exhaustive history are not implemented |
| Events and academic dates | Standard academic dates and Physics & Astronomy public events, plus bounded directory reads; not all University events or vacancies |
| Personal organisation | Dated evidence, collections, tags, local tasks, agenda, study plans and local ICS import/export |
| Languages | Ten-language service catalog and saved/per-call preferences; source names and evidence are preserved. The setup page currently supports English and Chinese |

University email is handled by **Outlook** and is outside this plugin's development scope. Coursework submission, message sending, bookings, applications, enrolment changes, teacher administration, OCR and automatic background calendar sync are not implemented.

Normal campus reading/downloading uses the plugin's own session, structured DOM and HTTP. It does not require screenshots, coordinate clicks, host-side parser scripts or per-file Save As dialogs. Campus policy can require a later sign-in or MFA.

Downloads stay on the campus computer. `study_export_files` transfers their verified original bytes through MCP so a capable host can create usable attachments; a local path or resource URI alone is not a cloud file reference. See [file delivery and cloud workflows](docs/FILE_DELIVERY.md). Each person installs independently and uses their own account; never share your private runtime/data directory or connection credentials.

## Efficiency and acceptance

Version **0.8.1** fixes NMR connection setup: remember an encrypted teaching-group connection once on Windows, then query samples directly. Missing sample details stay in chat or a supported host form. The redesigned English/Chinese credential form fixes normal-browser POST rejection, and rejected forms can be renewed. NOMAD still has a separate, expiring account session; live NOMAD and individual host credential UX remain unverified. See [NMR usage and limits](docs/NMR.md) and [0.8.1 verification](docs/NMR_CONNECTION_ACCEPTANCE.md). Existing campus workflows and original-file export remain available. Daily/student/full catalogs retain 15/35/38 tools.

Installation, tool/protocol checks, real campus reads and real agent/model conversations are separate evidence. This is a **student preview**, with installation and performance results in [INSTALL_PERFORMANCE.md](docs/INSTALL_PERFORMANCE.md). Earlier real Chat/Work and WorkBuddy evidence remains in [WORK_ACCEPTANCE.md](docs/WORK_ACCEPTANCE.md) and [WORKBUDDY_RESULTS.md](docs/WORKBUDDY_RESULTS.md). Those historical checks do not certify every current workflow or another person's account. See [0.7.1 contract coverage](docs/OUTPUT_CONTRACTS.md) and [reproducible protocol measurements](docs/CONTRACT_PERFORMANCE.md).

## Develop and build

Shared rule **2026-09-14.1** is adopted. All 39 public tool identities across profiles declare output schemas, with the same server validation for direct and dispatched calls. Errors return bounded recovery and known saved identifiers; output-format failures never repeat a write. See the [output-contract coverage ledger](docs/OUTPUT_CONTRACTS.md).

The source archive remains available for developers and non-Windows hosts. Windows is the live campus acceptance platform; macOS/Linux live campus operation is unverified.

```text
python -m pip install -c requirements.lock -e ".[dev]"
python -m pytest -q
python scripts/smoke_mcp.py
python scripts/public_release.py
python scripts/package_plugin.py
```

Build the Windows bundle on Windows using a fresh wheel and `scripts/build_windows.py`. The builder verifies the official Python archive checksum, uses pinned dependency constraints, preserves upstream licences and records binary provenance. It never copies a personal installed runtime. See [release instructions](docs/RELEASING.md).

MIT applies to project source and original artwork, not University materials or third-party products. [Third-party notices](THIRD_PARTY_NOTICES.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Reference projects](docs/GITHUB_REFERENCES.md)
