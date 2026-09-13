# WorkBuddy historical course results

Version: 0.5.2. The reported 0.5.1 trial used WorkBuddy Hy4 preview with high reasoning. It is not a GPT-5.6 Terra benchmark.

## Observed problem

The client connected successfully. Historical marks failed because the generic EUCLID reader captured only the visible academic-year tab. Other year panels were already present in the authenticated Courses document. A query string filtered links; it did not select a year. The supplied trial log contained eight school reads and sixteen result polls, including repeated Assessment, Courses and Documents reads. Service discovery also treated a list of keywords as one exact phrase.

Repeatedly loading the MyEd portal added substantial latency. Direct DOM inspection found a parameter-free EUCLID SSO entry in the actual MyEd student-record link. Reusing that entry avoids booting the full portal each time; one MyEd fallback remains if it fails.

## Changed behavior

- Call `study_results(academic_year="all")` directly for the student's own published course marks, grades, credits, result and sit fields. Use `current` or `YYYY/YY` for a narrower year.
- Read the labelled loaded year panels together. No screenshots, coordinate clicks, year-tab clicks, form submissions, grade changes or per-course expansion.
- Return structured rows and dated evidence. Empty or placeholder marks retain their original strings. Missing fields or years report partial coverage; they never prove that results do not exist.
- Wait up to 20 seconds inside the initial call. Poll only when its state remains running or queued; a terminal response already includes the result. Larger outputs expose pagination.
- Reuse a five-minute cache within the individual's private installation. `refresh=True` requests a new school read. Starting an interactive campus login invalidates this cache. Matching active result jobs are reused.
- Existing `study_read_service` clients can select an academic year in EUCLID Courses. An exact year in the old query parameter is also recognised. Assessment component navigation remains a separate, incomplete adapter.
- Multi-keyword service discovery finds relevant catalog entries. Connection guidance calls for one brief status check, without host configuration reads or unrelated onboarding.

Own published marks are read-only student information. This is not an official transcript, a complete assessment-component export or staff grade administration. The University's [student assessment guidance](https://registryservices.ed.ac.uk/student-systems/support-guidance/students/in-course-assessments) distinguishes provisional in-course marks and final ratified course marks.

## Verification scope

Synthetic tests cover hidden year panels, mobile duplicate avoidance, empty and zero marks, unknown-year coverage, evidence, caching, expiry, separate installations, login invalidation, duplicate jobs, pagination, SSO fallback and portable tool registration. Optional DOM tests run real headless Chrome with synthetic offline pages.

Live acceptance uses the existing private student session and reports only timing/count summaries outside that private store. It does not publish the student's marks, course identities, SITS session links or account details.

Backend/stdio latency is not WorkBuddy's total model-turn latency. Response byte counts or tokenizer estimates are not provider-billed tokens. A new WorkBuddy model turn must be recorded separately; a passing MCP protocol probe does not certify all clients or models.

## Recorded measurements (2026-09-13)

The installed 0.5.2 package was started through the existing WorkBuddy MCP command/environment. It exposed 29 student tools, including `study_results`. Configuration file hashes were unchanged and the existing campus profile was reused.

| Measurement | Observed value |
| --- | --- |
| MCP initialization, catalog and status | 0.984 seconds |
| Installed fresh results call | 10.485 seconds; one tool call |
| Immediate cached results call | 0.015 seconds; one tool call; no browser |
| Final fresh result text | 4,705 UTF-8 bytes |
| Original failing UoE path in WorkBuddy log | 31 plugin calls; 48,180 UTF-8 result-text bytes |
| Tests | 131 passed, including real offline DOM tests |

Development fresh-read samples included a 31.062-second, two-call result as well as 10.485-second, one-call results. School/SSO latency is variable; the final installed probe is a measurement, not a guaranteed response time. The original model trial and the repaired direct MCP probe are different acceptance scopes. Billed-token usage and a new WorkBuddy model turn remain unmeasured.

## Upgrade

Install the new package into the existing private runtime. Keep the user's campus profile, database, downloads and host configuration. Refresh or reconnect the UoE MCP entry so WorkBuddy loads `study_results` and its new instructions. Other connectors do not need reinstalling.

For read-only acceptance, ask: “Query my historical course results, grouped by academic year.” The intended first operation is `study_results`; do not manually instruct the model to browse different record sections or supply marks.
