# Student workflows in 0.6.0

The WorkBuddy trial spent minutes locating local files, setting up PDF libraries, writing parsing scripts and building a timetable UI. The plugin previously exposed the low-level pieces but did not provide a complete ordinary schedule query. This release adds four shared MCP workflows that return usable data directly.

## Implemented and bounded

| Request | Tool | Actual coverage |
| --- | --- | --- |
| Personal classes this semester | `study_timetable` | Published personal Timetabler activities, by academic year, semester and dates. Weekly counts/date spans are computed before detail pagination. The summary is not a continuous attendance span or a complete exam/deadline calendar. |
| A course PDF timetable | `study_timetable(item_id=..., semester=1)` | Automatically download an observed file if needed, verify its checksum, then read labelled week/day cells with the existing pypdf dependency. Cross-page continuation and mid-page semester changes are supported. Course grids do not prove personal group allocations; week labels are not converted into invented calendar dates. |
| Find/read/download materials | `study_materials` | Name/id resolution, dated cached search, bounded live folder search and verified file reading/download. Ambiguous matches return choices. A known parsed PDF timetable can be found even when its filename does not say “timetable”. |
| Messages and updates | `study_messages` | Loaded Learn activity rows and loaded course inbox unread counters. Full conversation bodies, email and exhaustive message history are not implemented. Zero unread does not mean no history. |
| Events and academic dates | `study_events` | Official standard academic calendar and Physics & Astronomy public event feed, each with separate freshness/failure. This is not university-wide activity coverage. |

Sources: [Timetabler](https://timetabler.is.ed.ac.uk/), [Learn](https://www.learn.ed.ac.uk/), [academic dates](https://semester-dates.ed.ac.uk/), [Physics & Astronomy events](https://www.ph.ed.ac.uk/events/calendar). The university also links a [student Events App](https://www.ed.ac.uk/new-students/get-started/top-tasks/download-our-events-app); its full aggregation remains unimplemented. Standard academic dates have programme-specific exceptions.

PDF table support is limited to upright, labelled weekly grids with detectable ruled columns. Unsupported layouts return partial coverage or an explicit failure. No OCR or universal PDF-layout accuracy is claimed.

## Runtime changes

The personal timetable uses the school's observed export endpoint with the browser-owned authenticated request context. It reads the returned HTML directly and never launches the site's generated blob download. No cookies, authentication headers or account credentials leave the plugin profile. This is an observed web integration, not a registered or officially supported university API partnership.

The native Chrome download path initially failed during development with Windows process exit code 3221225477 after the school returned a successful export. Direct response reading removed that dependency. Failed development probes are retained privately and are not included in the successful-path timings below.

Other fixes:
- Learn activity/message navigation is recognised as an authenticated shell.
- A school response saying a course is unavailable returns that state promptly; it does not ask for a new campus login.
- Unrecognised loading timeouts are distinct from observed login gates.
- New jobs reuse matching active work and wait internally for up to 20 seconds.
- Personal data caches last five minutes; updates/counters last two minutes. PDF extraction caches are keyed by verified content hash and parser version.
- Resource traversal prioritises matching folders, retains observed folder context and has a bounded search budget.
- Latest complete personal export snapshots supersede old agenda entries without falsely marking missing records cancelled.
- Unknown academic-calendar dates remain unknown; cross-month/year ranges retain both endpoints.
- Results carry short response guidance. A basic query should return a table/list, not trigger a host filesystem search, package install, new parser or unsolicited website.

## Cross-host compatibility

One execution core and plugin identity serve all supported hosts. Student profile exposes 33 tools; full profile exposes 36. Existing tool names remain available.

Some Chat/Work conversations retain a pre-upgrade 31-tool catalog. These calls use the same new implementation immediately:

- `study_read_service(service_id="timetable", query="semester 1")`
- The same call with `item_id` for a course PDF.
- `study_read_service(service_id="learn", query="activity")` or `query="inboxes"`.
- `study_read_service(service_id="events")`.

For those compatibility calls, `query` can contain a small JSON object with the relevant workflow options, including academic year, refresh and offset. The response supplies an exact continuation call when needed. No second plugin installation is required.

WorkBuddy/Claude/other stdio hosts should refresh their MCP catalog once after upgrading to discover the four named tools. Existing campus login, private data and host configuration are reused.

## Verification on 2026-09-13

The installed 0.6.0 wheel was exercised using the existing WorkBuddy MCP command, arguments and environment. These are real installed-tool and school-data measurements, **not a new WorkBuddy model conversation**.

| Workflow | Time | Tool calls | Result text UTF-8 bytes |
| --- | ---: | ---: | ---: |
| Personal semester timetable, live | 23.62 s | 2 | 2207 |
| Personal timetable, cached | 0.02 s | 1 | 2068 |
| Course PDF semester week grid, first parse | 1.321 s | 1 | 25011 |
| Course PDF week grid, cached | 0.019 s | 1 | 25010 |
| Indexed timetable material lookup | 0.251 s | 1 | 1129 |
| Verified file text reading | 1.279 s | 1 | 11734 |
| Learn activity, live | 6.299 s | 1 | 3702 |
| Course unread overview, live | 5.66 s | 1 | 1963 |
| Supported public events/dates, live | 0.27 s | 1 | 2625 |

The personal query returned the requested academic year/semester with no unparsed export rows. The PDF query returned all eleven labelled semester weeks. The update/counter queries returned loaded source rows, and both public sources returned records. Empty/partial scopes remain explicit. Cached updates and public events were also checked.

MCP startup and tool discovery: 0.891 seconds. Student catalog: 21741 UTF-8 bytes. Result bytes measure one serialized MCP text block, not billing tokens; some clients also consume structured content. The final weekly-overview field adds a small deterministic summary after these initial payload measurements, so byte counts above are not a final payload-size claim.

Validation covers 172 regression tests, a real stdio protocol check, the installed source/module comparison and unchanged hashes for three host configuration files. The final summary and compatibility routes were also exercised through the existing connected UoE app tools: personal timetable 7.1 s, inbox counters 10.9 s, public dates/events 4.9 s, one call each. The complete weekly overview count matched all filtered occurrences despite detail pagination. These are connected-tool checks, not separate model-conversation acceptance for every Chat/Work mode. No private course titles, grades, account identifiers, PDF contents or connection secrets are included here.

The previous WorkBuddy grade conversation used Hy4 preview with high reasoning and remains a separate historical result. The user deferred its follow-up model acceptance. This run has no model, reasoning-effort or token-billing measurement and is **not GPT-5.6 Terra max acceptance**. It does not certify all newly added workflows in Chat, local Work, cloud Work, Claude or DeepSeek. The previously reported OpenAI project-sync issue is outside this plugin change.
