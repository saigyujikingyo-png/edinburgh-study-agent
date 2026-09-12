# Work acceptance scope — UoE Companion 0.4.0

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
