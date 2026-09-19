# Learn connection recovery and file updates (0.8.4 preview)

This release addresses a workflow in which checking for new course files repeatedly waited for a page that could not finish campus sign-in. The MCP connection and a saved login observation were available, but neither established a current authenticated Learn session.

## Observable behavior

- Learn navigation reports a bounded failure code, stage, optional allowlisted hostname/HTTP status and recovery action. Raw exception text, redirects, query strings, cookies and credentials are not returned or saved by these diagnostics.
- A network failure preserves saved login information. Only a recognized login requirement requests campus sign-in. Navigation waits at most 12 seconds per navigation; content recognition retains its separate 20-second budget. A recent network failure suppresses repeated Learn browser jobs for 60 seconds. Cached reads and other services remain available. A forbidden/missing individual course does not trigger service-wide suppression.
- Workflow modules and the `-m` worker share the same exception classes, so a login requirement remains `needs_login` rather than falling into generic failure handling.
- A list refresh without a course returns course choices before opening a browser. It does not relabel cached files as fresh. Pagination and batch limits are server-validated and included in the advertised portable parameter descriptions.

The failure diagnostic distinguishes `NETWORK_TIMEOUT`, `NETWORK_DNS`, `NETWORK_CONNECTION`, `TLS_ERROR`, `HTTP_ERROR`, `LOGIN_REQUIRED` and `PAGE_NOT_READY`. A network failure identifies the observed failing path; it does not establish a university-wide outage or diagnose the user's VPN configuration.

## Check files in one operation

Ask the agent to check for new or changed course files. It should call `study_materials(operation="updates")`, optionally narrowing `course` by name/id. An empty course or `all` checks the dated Learn course index in batches of up to three courses, with the newest dated titles first. This ordering is not an enrolment claim. When the index is empty, one bounded course discovery is attempted. Known closed courses are excluded from the broad default; an explicitly selected course can be rechecked.

Each batch reuses one private browser context and a bounded folder traversal. Continue remaining courses with `course_offset=next_course_offset`. Read more rows from the completed `job_id` through `study_school_job`; paging the receipt does not scan the school again. The operation does not create collections, recurring tasks, downloads or school changes.

| Result | Meaning |
| --- | --- |
| `baseline` | First observed file list; it does not establish a new upload. |
| `newly_observed` | Not present in the available prior course index; it may be an older file that was not previously seen. |
| `metadata_changed` | Observed title, source link, status or indexed description differs. |
| `unchanged_metadata` | Compared metadata agrees; returned as a count to keep output small. |
| `comparison_unknown` | Prior bounded index was truncated, so absence is not established. |

The tool does **not** claim remote file-byte equality or an upload date. Hidden, restricted and unvisited content remains outside the observed scope. Files absent from a partial scan are retained and counted as not seen, never deleted. A connection/login failure stops the batch, retains completed course results and returns the failed course offset for a later resume.

## Evidence boundaries

Synthetic tests cover redirected SSO network failure, HTTP login/service failures, unrelated iframe failures, shared worker exception identity, cached-read preservation, cooldown expiry, metadata differences, partial baselines, interrupted batches and paging without rescanning. Public MCP checks cover full/student/daily profiles and structured error/text compatibility.

Record the exact release's test, package, installed and host evidence separately. A successful source or package test does not prove a restored campus network path, a current SSO session or every host/model workflow. Retain the existing account connections and private browser profile during an authorized upgrade. The earlier 0.8.3 Windows command-encoding repair remains included.

Local source verification on 19 September 2026: **653 passed, 5 skipped** in the full suite; the real stdio smoke passed with structured output, output schemas, text parity and invalid-argument rejection. Isolated catalogs exposed 38/35/15 tools for full/student/daily. Daily catalog size was 97,609 serialized UTF-8 bytes and warm cached-status median was 25.82 ms across three measured calls. These are local protocol measurements, not model tokens, user task latency or billing.

A separate authenticated-source attempt using an existing local profile ended after 25.9 seconds with `NETWORK_TIMEOUT` at the campus sign-in stage. No course was freshly checked. This verifies the new failure path, not restored campus access; stored credentials were retained. Package, installed-account and host/model acceptance require their own subsequent receipts.
