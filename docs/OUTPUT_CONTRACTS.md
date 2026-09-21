# Output contracts and acceptance coverage

Shared rule: **2026-09-14.1**, section 12. Product implementation: **0.8.0 student preview**. Public output contract: **version 1**. These are separate version numbers. Implementation in the checkout does not establish that a release package or an account installation has been accepted.

The shared registry now declares output schemas for all **39 public tool names**: **38** in the full catalog, **35** in the student catalog and **15** in the daily catalog. The daily entrypoint exposes **21 advanced operations** through on-demand discovery. All advertised tools have `outputSchema`; each advanced operation has the same complete output contract as its direct tool.

The `study_nmr` contract validates status, connected/reused setup, missing input/authentication, pending protected connection, explicit selection, ready data, no matches, unavailable/cancelled acquisition, verified download and disconnection. Closed metadata schemas keep secrets and binary data out of tool text; required download fields prevent a bare success claim. The same original-file export contract applies to verified NMR records. See [NMR design and acceptance boundaries](NMR.md). Version 0.8.1 adds bounded remembered/persistence metadata and connected-state requirements without changing existing file-result fields. Real browser submission, DPAPI restart, sample-form fallback and download-intent recovery are covered by focused checks; see [connection verification](NMR_CONNECTION_ACCEPTANCE.md). True host credential UX and live NOMAD acceptance are separate from synthetic state/ZIP/DPAPI/MCP checks.

## Implemented boundary

- Successful results retain their operation-shaped fields and gain `_contract: {version: "1", operation: "study_..."}`. `structuredContent` and the serialized JSON text fallback contain the same data. A dispatched result identifies the original operation, not `study_more`.
- The server validates results before delivery. Validators are cached, and deliberately extensible JSON is limited by type, string/list/object size, nesting depth and node budget. Non-JSON and non-finite values are rejected.
- Errors use `isError=true`, `contract_version: "1"` and a bounded `error` object with `code`, `operation`, `message` and `recovery`. Codes are `UNKNOWN_TOOL`, `INVALID_ARGUMENT`, `TOOL_ERROR` and `OUTPUT_VALIDATION_ERROR`. Error text does not echo private result values. Known safe identifiers can be retained after a write; output validation never retries that write.
- Direct calls and daily dispatch use the same validation boundary. `study_more(mode='describe', tool=...)` includes that operation's output schema. `study_help(topic='schemas', tool=...)` provides detailed contracts, including the relevant school-job payload. Ordinary help and the default dispatcher do not repeat every advanced schema.
- School jobs use a compact public envelope and independently validated payloads for all **11 worker actions**: login, courses, resources, download, MyEd, service, resource reading, results, timetable, materials and messages. Payload schemas are discovered on demand. Passing only the envelope is insufficient.
- The existing compact/full distinction remains: compact results can omit optional null fields and shorten source excerpts; full results retain source nulls. Missing marks remain blank strings, unknown dates and counts remain unknown, and suppressed means are omitted rather than replaced by zero.
- File contracts describe the available identity, source, path, byte count, hash, verification and pagination metadata. Media/resource blocks are preserved alongside JSON text; binary content is not duplicated into structured data. File metadata validation is not proof of host receipt.

The implementation is in [the registry](../src/edinburgh_study_agent/contracts.py), [shared definitions](../src/edinburgh_study_agent/contracts_common.py), [record contracts](../src/edinburgh_study_agent/contracts_records.py), [school contracts](../src/edinburgh_study_agent/contracts_school.py) and [the protocol boundary](../src/edinburgh_study_agent/protocol.py).

## Evidence and limits

The final local 0.7.1 source run passed **235 tests in 21.14 seconds** on Windows / Python 3.12.14, including the additional error-boundary cases. Real stdio checks passed for output schemas, structured errors, text parity and all three profiles; see [protocol measurements](CONTRACT_PERFORMANCE.md). The exact release commit's CI and installation receipts remain separate evidence.

[Output-contract tests](../tests/test_output_contracts.py) cover catalog validity, all advanced schema descriptions, direct/dispatched task and collection parity, structured redacted errors, invalid-output rejection without repeating writes, lifecycle states, pagination, unknown/zero distinctions, verified file text and deterministic student workflows. [Student-core tests](../tests/test_student_core.py), [result tests](../tests/test_results.py), [daily tests](../tests/test_daily.py) and [document-layout tests](../tests/test_document_layout.py) retain their backend/data checks. They do not execute every live service branch through a host.

Evidence codes below distinguish the checks instead of calling every tool fully accepted:

- **C**: catalog schema and registry coverage checked; all advanced operations also have describe coverage.
- **D**: a synthetic successful public call is asserted against its contract and JSON text fallback in the output-contract tests.
- **X**: a synthetic advanced call is checked; selected reads are compared with their direct result.
- **J**: the shared school-job lifecycle and action-payload validation boundary is checked. This does not mean that tool started a real campus job.
- **B**: existing backend fixtures/regressions support the fields; a dedicated successful public contract call is not claimed by this ledger.
- **F**: a deliberately malformed public result is rejected; it is not a successful school read.

All rows below have a declared **v1 schema and server validation**. Evidence codes concern exercised paths only. Live adapters, every source branch, all host/model combinations and final artifact delivery remain separate gates.

## Per-tool coverage

Availability: F = full; S = student; D = direct daily tool; A = daily advanced operation.

| Tool | Availability | Evidence | Implemented contract and remaining acceptance scope |
| --- | --- | --- | --- |
| `study_agenda` | F / S / D | C, D | Dated/unknown agenda records, display timezone, counts and pagination; live calendar coverage remains separate. |
| `study_capture` | F | C, B | Observation identity, captured counts and provenance; private source capture is not tested. |
| `study_collect` | F / S / A | C, X | Collection identity, tags, archival state and school-write boundary; host workflow remains separate. |
| `study_collections` | F / S / A | C, D, X | Collection rows, evidence and pagination; direct/dispatched synthetic reads agree. |
| `study_connect_school` | F / S / D | C, J | Login job identity and lifecycle; interactive login/MFA is not performed by contract tests. |
| `study_deadlines` | F / S / A | C, B | Due dates, unknown dates, cached records and counts; no claim that absent cached assignments are absent at school. |
| `study_download_files` | F / S / A | C, J | Per-file outcome, partial failure, remaining ids and verified metadata; real transfer and receipt remain separate. |
| `study_download_resource` | F | C, B | Download identity, bytes, hash, source and freshness; current host download acceptance remains separate. |
| `study_downloads` | F / S / A | C, D, X | Mixed Learn/NMR records, filename-sourced legacy titles without database rewrites, and daily dispatcher parity; host receipt remains separate. |
| `study_events` | F / S / D | C, D | Date/null semantics and independent source failures; supported public sources do not mean all University events. |
| `study_evidence` | F / S / A | C, B | Observation, optional item detail, bounded text and continuation; no private-source read in contract tests. |
| `study_export_files` | F / S / D | C, D, F | Originals/ZIP as MCP binary resources, metadata-only mode, size/SHA-256, bounded batch and state-specific contracts. All three profiles and modes tested; see [delivery acceptance](FILE_DELIVERY.md). |
| `study_export_calendar` | F / S / A | C, B | ICS identity/path, counts, export coverage and available media metadata; receiving/opening it is a separate gate. |
| `study_help` | F / S / D | C, D | Topic, locale, guidance and on-demand schema discovery; host interpretation is not guaranteed. |
| `study_home` | F / S / A | C, B | Cached counts, service checks, collections and local tasks; counts are not a live connection claim. |
| `study_import_calendar` | F / S / A | C, B | Import counts, scope, recurrence limits and evidence; source calendar completeness remains separate. |
| `study_live_courses` | F / S / D | C, J, F | Course job and typed observations; malformed payload rejection preserves job identity without retry. |
| `study_live_myed` | F / S / A | C, J | Portal lifecycle and page/link coverage; no fresh MyEd account access is claimed. |
| `study_live_resources` | F / S / A | C, J | Course-resource rows and bounded traversal metadata; external/LTI and hidden resources remain gaps. |
| `study_materials` | F / S / D | C, D, J | List/read/download/updates, scope choices, verified text, metadata deltas and resumable partial batches; live discovery/host delivery remain separate. |
| `study_messages` | F / S / D | C, D, J | Activity/counter shapes, unknown versus zero and pagination; Learn conversation bodies remain unimplemented. |
| `study_more` | D | C, D, X | List/describe/call contracts, operation identity and shared validation; not every advanced operation is invoked in the synthetic suite. |
| `study_plan` | F / S / A | C, B | Draft allocations, minutes, conflicts and remaining effort; a plan is not a school booking or official requirement. |
| `study_preferences` | F / S / A | C, B | Saved preferences, optional language list and presentation fields; host/model language quality remains separate. |
| `study_read_file` | F / S / A | C, D | Verified identity/hash, text offsets, truncation and null continuation; no OCR or host delivery claim. |
| `study_read_resource` | F / S / A | C, J, B | Inline page versus downloaded file and source freshness; actual authenticated page access remains separate. |
| `study_read_service` | F / S / A | C, J, B | Service page/result/entry/login/external-provider branches and legacy workflows; not every real service branch is exercised. |
| `study_results` | F / S / D | C, D, J | Published strings, blank/zero marks, year summaries and coverage; not an official transcript or award calculation. |
| `study_route` | F | C, B | Named route/observed link and structured invalid arguments; no browser navigation acceptance is claimed. |
| `study_school_job` | F / S / D | C, D, J | Pending/terminal/unchanged states, retained identity and payload validation; terminal completion is not proof of freshness. |
| `study_school_status` | F / S / A | C, B | Previous local check and active jobs; cached authentication is not a current live connection check. |
| `study_search` | F / S / D | C, D | Typed cached items, provenance, empty matches and pagination; no remote completeness inference. |
| `study_services` | F / S / A | C, B | Directory, locale and dated service checks; directory presence is not access evidence. |
| `study_status` | F / S / D | C, D, F | Version/counts, freshness and optional capabilities; nonconforming backend data becomes a structured error. |
| `study_task_create` | F / S / A | C, X, F | Identity, estimate in minutes and local scope; format failure retains identity and does not duplicate creation. |
| `study_task_update` | F / S / A | C, X | Local task state and university-submission boundary; no school form or submission changes. |
| `study_tasks` | F / S / A | C, D, X | Typed tasks and filtering; direct/dispatched synthetic reads agree. |
| `study_timetable` | F / S / D | C, D, J | Personal patterns/occurrences, DST, empty-year scope and PDF week cells; PDF grids do not establish personal groups/calendar dates. |

## Advanced operation ledger

Every operation below is implemented using its direct v1 contract, with cached server-side validation. **Describe** means automated output-schema discovery; **call** means an actual synthetic dispatcher invocation. The matching tool row describes payload coverage and remaining gaps.

| Advanced operation | Describe | Synthetic dispatcher call coverage |
| --- | --- | --- |
| `study_collect` | Checked | Save a resource with tags |
| `study_collections` | Checked | Read and compare with direct call |
| `study_deadlines` | Checked | Dedicated call not claimed |
| `study_download_files` | Checked | Dedicated call not claimed |
| `study_downloads` | Checked | Mixed Learn/NMR legacy receipt normalization and direct-result contract parity |
| `study_evidence` | Checked | Dedicated call not claimed |
| `study_export_files` | F / S / D | C, D, F | Originals/ZIP as MCP binary resources, metadata-only mode, size/SHA-256, bounded batch and state-specific contracts. All three profiles and modes tested; see [delivery acceptance](FILE_DELIVERY.md). |
| `study_export_calendar` | Checked | Dedicated call not claimed |
| `study_home` | Checked | Dedicated call not claimed |
| `study_import_calendar` | Checked | Dedicated call not claimed |
| `study_live_myed` | Checked | Dedicated call not claimed |
| `study_live_resources` | Checked | Dedicated call not claimed |
| `study_plan` | Checked | Dedicated call not claimed |
| `study_preferences` | Checked | Dedicated call not claimed |
| `study_read_file` | Checked | Dedicated call not claimed |
| `study_read_resource` | Checked | Dedicated call not claimed |
| `study_read_service` | Checked | Dedicated call not claimed |
| `study_school_status` | Checked | Dedicated call not claimed |
| `study_services` | Checked | Dedicated call not claimed |
| `study_task_create` | Checked | Create, reject invalid input and reject malformed output without repeating the write |
| `study_task_update` | Checked | Complete a local task and preserve the school-submission boundary |
| `study_tasks` | Checked | Read and compare with direct call |

The dispatcher itself has bounded six-result discovery, including refine-query metadata, and one-operation descriptions. Its compact public schema is supplemented by full operation validation; it is not a substitute for that validation.

## Job lifecycle and compatibility

`queued`, `running` and `waiting_for_login` are pending. `complete`, `partial`, `needs_login`, `failed` and `cancelled` are terminal. A successfully retrieved failed job is a successful status call reporting a failed operation; an MCP call error is represented separately by `isError` and the structured error code.

Pending, unchanged, failed or login-required jobs can omit a result. Null can represent unavailable payload in compatible non-success records; a completed or partial job must retain an object result and its action. An unchanged poll may omit action and payload. When a payload is present, the server validates its action-specific schema even through `study_school_job` or a legacy service entrypoint. A malformed payload cannot hide behind an otherwise valid job envelope.

Schemas supplement source facts. Course membership does not prove formal enrolment; an empty cached search does not establish an empty course; a zero unread counter is not empty message history; an empty timetable cell does not prove no class. PDF week cells retain source page numbers, sparse day labels and explicit truncation, without inventing calendar dates.

## Historical 0.7.0 baseline

The isolated 14 September 2026 stdio probe at `af6d552` recorded the following **before** implementation:

| Profile | Advertised tools | Declared output schemas | Serialized catalog bytes |
| --- | ---: | ---: | ---: |
| full | 36 | 0 | 25,786 |
| student | 33 | 0 | 21,807 |
| daily | 13 | 0 | 7,535 |

That probe found matching successful JSON text and structured data, but no output-schema discovery, no server result validation and no structured error body for invalid routes. It is a baseline, not the current implementation or 0.7.1 acceptance.

Catalog bytes mean UTF-8 bytes of `ListToolsResult.model_dump_json(by_alias=True, exclude_none=True)`. They are not network traffic, actual model tokens or billing. Adding output schemas may increase catalog size; measure the current catalog and latency before making an efficiency claim. Validator caching and delayed discovery do not by themselves establish lower model charges.

## Release and installation gates

| Gate | Development state | Release evidence required |
| --- | --- | --- |
| Shared rule and coverage inventory | Adopted; 38 tools / 21 advanced operations registered | This ledger and matching shared principles |
| Declared contracts and server validation | Implemented | Final checkout contract/regression pass and exact CI run |
| Error/lifecycle/null/artifact branches | Focused synthetic coverage; not exhaustive live coverage | Current boundary tests, malformed-result checks and applicable artifact checks |
| Direct/dispatcher/profile/text compatibility | Synthetic public calls and real stdio checked | Final packaged stdio/profile validation; host dialect acceptance recorded separately |
| Current campus data/document correctness | Not established by this change | Authorized live reads and independent document checks where applicable |
| Host artifact receipt | Not established by schemas or local paths | User-receivable, openable artifact through the intended host |
| Host/model conversations | Not established by this change | Separate Chat, local Work, cloud Work, Codex and other advertised host runs |
| Terra max efficiency | Separate benchmark gate | Exact model/effort, fixed inputs, success, calls/retries, latency and actual usage when available |
| Release package, upgrades and rollback | Packaging/publication/account rollout in progress | [Release procedure](RELEASING.md), exact release/CI evidence, repeat-install and recovery checks |

Keep private account identities, app/tunnel ids, campus data and installation receipts outside the public repository. Account installs are accepted separately even when they reuse the same core. The known OpenAI local Work project-synchronisation issue, Outlook mail, GUI repairs and unrelated features remain outside this change.

## Development changelog

- 2026-09-14: adopted shared rule 2026-09-14.1 and recorded the 0.7.0 schema/error/dispatcher baseline.
- 2026-09-14: implemented v1 output contracts for the 0.7.1 student preview, shared direct/dispatch validation, structured errors, bounded data, cached validators and on-demand job schemas. Added focused synthetic/protocol coverage. Packaging, publication and account rollout require their own completion evidence.

References: [shared rules](../DEVELOPMENT_PRINCIPLES.md#12-structured-tool-outputs-and-output-schemas), [verification](../VERIFICATION.md), [release gates](RELEASING.md), [host evidence](HOSTS.md).

## 0.8.4 Learn recovery additions

School job envelopes declare bounded `failure` diagnostics, outage retry timing and the originating failed job when a repeated live read is suppressed. Raw redirect/error details are excluded. The materials action adds an operation-shaped updates payload with dated per-course checks, metadata comparison counts, unknown comparison coverage and separate course/row pagination. Tests cover shared worker exceptions, full/student/daily recovery results, malformed diagnostic rejection, partial batch preservation and completed-job paging without another scan. Parameter bounds remain runtime-enforced and are described in the portable catalog. Live SSO and host/model acceptance remain separate.

Version 0.8.5 adds optional filename-title provenance, observed Learn preview binding, and typed per-file/worker failures. Focused regressions are documented in [download integrity](DOWNLOAD_INTEGRITY.md). Existing public result shapes and contract version 1 are retained; required-field diagnostics name schema fields without including private values.
