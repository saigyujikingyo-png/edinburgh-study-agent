# Chat, local Work and cloud Work acceptance — UoE Companion

## 0.5.1 single-entry acceptance — 2026-09-12

At the user's request, the duplicate local Codex package was uninstalled and only its personal-marketplace catalog entry removed. The campus runtime, profile, files and registered ChatGPT connection were preserved. The retained entry is named **UoE Companion**, without a separate connection suffix.

After removal, actual model turns used the same registered connection:

| Mode | Result | Scope |
| --- | --- | --- |
| Ordinary Chat | Status returned 0.5.1; a one-course cached query succeeded | No live refresh or download in this consolidation check |
| Desktop local Work | The user created a local Work task; status and one-course lookup succeeded | Session metadata identified `codex_work_desktop`; both remote plugin tool calls completed. This was separate from the development task |
| Cloud Work | The previous failing Work task again called status and returned one cached course | Separate live Learn refresh evidence appears below |

All three reported the same version and cached course count. This verifies the single-entry connection for this person's deployment. It does not repeat every workflow in every mode. Private receipts retain the task/turn identities and local Work tool calls; they are not distributed.

## 0.5.1 connection recovery — 2026-09-12

A fresh cloud Work task failed to receive course tools. Its prompt referenced the local personal-marketplace package; the separate ChatGPT app was not installed/connected, even though the local runtime and tunnel were healthy. The installed public package declared stdio but no app dependency. Local runtime health did not detect this host-side failure.

The personal ChatGPT app was installed and connected, its tool catalog refreshed, and a private app dependency was added to the locally installed package. The public package contains only the binding implementation and instructions, never the participant's connection.

Fresh acceptance after installing 0.5.1:
- **Cloud Work:** the original failed task reported actual version 0.5.1 and completed a new Learn course job with two-page coverage. The campus session was reused. Academic-year labels were separated from the All terms listing and were not presented as formal enrolment.
- **Chat:** with the user's permission, a separate ordinary Chat conversation (the Chat radio was selected, not Work) called status and searched one cached course. It reported actual version 0.5.1 and cached-only coverage. The UI exposed the actual search request and response.
- No screenshot, coordinate click, new campus login, file download, task write or school submission was used in this recovery acceptance. Downloads and other services retain their separate historical evidence below.

Private receipts retain the actual task/turn identities and source time. Public source tests cover binding preservation, rollback, identity conflicts, missing configuration and preventing a private dependency from entering the published package. The binding check reports cloud/model status as not_checked: it is a configuration check, not a substitute for these real conversations.

The result establishes this person's connected Windows deployment. Other people still need their own registered app and campus session. A universal hosted service and public-directory one-click installation are not implemented; the campus computer must remain online.

## Historical Work acceptance — 0.4.0

Live acceptance: 2026-09-12, through the participant's existing ChatGPT Work task and private connection. Codex developed and deployed the update. The existing local campus session was reused without another login.

- Work reported `UoE Companion 0.4.0` and read the explicit implemented, unverified and missing capability groups.
- A fresh Learn course job reached `complete` with one default waiting call. Work retrieved the default first page and the remainder using `next_offset`, and checked the final non-truncated result. Source coverage was the current visible course-list scope, not formal enrolment evidence.
- Reading an existing PDF with `refresh=false` returned a verified local copy and `browser_started=false`, with remote freshness explicitly unchecked.
- A fresh transfer of that PDF with `refresh=true` succeeded with `reused=false`, a verified checksum and no failed entries. Work then read verified text from the new copy.
- No screenshot, coordinate click, Work-browser login or per-file Save As was used.

The four unchanged school-wide providers below retain their historical 0.3.0 evidence; this 0.4.0 run did not repeat every provider or test staff-only pages. The local upgraded runtime separately passed all 28-tool catalog, evidence pagination and restart-persistence checks. Public records omit the participant's courses, document identities, account details and private connection/task links.

The new original icon is included in the public and installed plugin assets and advertised through standard MCP server icon metadata. Work's developer-connection management UI allowed name and description edits, but did not expose a separate icon upload control in this acceptance. Rendering server-provided icons depends on the host; a displayed custom Work connection icon is not part of the verified result.

## Historical acceptance — 0.3.0

Historical live acceptance: 2026-09-11. Work was the user and acceptance host; Codex was the development host. This public record intentionally omits the participant's enrolment, course names, document identifiers, account identifiers, task URLs and private connection details.

The participant's existing Work task used the authorised private connection and the 28-tool catalog. The local installed runtime passed protocol, evidence lookup and restart-persistence checks.

The following workflows were exercised through Work:

- Refresh Learn courses with deferred rows and pagination.
- Traverse supported course folders, locate a PDF and spreadsheet, download fresh originals, verify hashes and read their text.
- Reuse campus SSO to read supported MyEd and EUCLID student-record pages.
- Read the authenticated Timetabler displayed week, without claiming a complete event import.
- Read authenticated MyCareerHub and public University Events pages.
- Save and read local collection entries, and create, read, update and archive an explicitly labelled synthetic test task.

No screenshot, coordinate click, Work-browser login or per-file Save As was used. The campus session had already been established in the dedicated local window.

An EUCLID section-label mismatch was initially reported as a failed read. The alias and declared section choices were corrected, and the subsequent Work read passed. The original failure remains in the participant's private evidence.

## Limits

This is a historical result for one authorised deployment. It does not establish current authentication for another user or guarantee continued compatibility after a university website change.

Untested directory entries, third-party/LTI content, hidden course content, complete vacancy/event listings, full structured timetable/exam imports and OCR remain outside the successful scope. No official record or submission was changed.

Downloads remain local; reading their text through MCP does not create a cloud attachment. Reboot/logoff recovery was not part of that acceptance.

The detailed receipts remain under the participant's private acceptance directory and are not part of the public repository or release.


## 0.5.0 student edition acceptance — 2026-09-12

The existing private Work connection was upgraded and its catalog refreshed. A real Work turn identified 0.5.0/student edition; looked up the library in French and Arabic with the same stable service ID; read preferences without changing them; called the agenda with a French language override and Asia/Shanghai display timezone; refreshed Learn courses through the existing campus session; and reused a previously verified PDF with browser_started=false. The final explanation was in French. No screenshots, coordinate clicks, per-file Save As, new campus login, task creation or university submission was used.

The actual agenda cache contained no structured events/deadlines/active tasks. Work correctly reported this as cached absence rather than an empty university schedule. Populated agenda ordering, timezone conversion, date-only/unknown dates and linked deadlines were verified with synthetic data and the official DeepSeek bridge fixture, not inferred from this empty live-account cache. This release does not add full structured Timetabler sync.

The directory lookups were local catalog queries and did not verify library access. Learn refresh was live and completed through two visible pages. PDF reuse did not check remote freshness; fresh downloading remains the separate 0.4.0 acceptance above. Earlier school-service checks remain historical, not repeated all-site verification.

Claude Desktop and WorkBuddy local configs were merged with backups; real model turns in those clients remain unverified. DeepSeek official-bridge tests are narrower than full Harness agent acceptance. See [host setup and evidence](HOSTS.md).
