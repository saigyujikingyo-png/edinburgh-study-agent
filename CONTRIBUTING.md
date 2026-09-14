# Contributing

Use Python 3.11+ and install the development extras from the current checkout. Run the tests, the real stdio smoke test and the publication check described in README.md.

Keep the MCP core independent of the host. Work is the user environment; success in a local development shell is not evidence of Work acceptance.

School adapters must use structured page content and observed links. Do not add screenshot or coordinate-click fallbacks. Use only the user's own authorised session and accessible content. A login page is not a successful data read.

Every service result needs its source, observation time and actual coverage. Do not infer formal enrolment from Learn membership or submission from a local task.

Use synthetic HTML and documents in tests. Do not commit campus page captures, user identifiers, signed URLs, cookies, personal schedules, course files or local verification receipts. Preserve session errors as failures, never as empty successful results.

Keep profile ownership exclusive, bound traversal and downloads, redact credentials from errors, and use incremental or conditional downloads only when freshness evidence is available.

For upstream code reuse, record the exact source revision and retain its license and required notices. The reference list is not permission to relicense upstream code. Propose substantial dependency or school-write changes separately.

Pull requests should describe the concrete behavior, relevant tests and remaining limits. Do not post private evidence to issues; see SECURITY.md.

## Output contracts

Follow shared rule **2026-09-14.1** section 12 and the [output-contract coverage ledger](docs/OUTPUT_CONTRACTS.md). Version 0.7.1 implements v1 output contracts in the shared registry; new or changed public tools and advanced operations must extend that implementation before their interfaces are considered complete.

Preserve operation-shaped successful results and their field meanings. Add definitions in the shared record/school contract modules, declare an output schema, return matching `structuredContent` and JSON text, and validate at the server boundary. The `_contract` operation names the underlying tool even through `study_more`. Keep detailed advanced and school-job schemas discoverable on demand instead of expanding the default catalog into every payload variant.

Cover success, structured errors, lifecycle, optional/null fields, units, provenance, pagination and available artifact metadata with synthetic fixtures. A completed job must retain its action and object payload; validate that payload against its action contract. Invalid output after a write must preserve known safe identifiers, reject success and avoid retrying the write. Preserve media/resource content blocks without copying binary data into JSON.

Run the focused contract tests, the appropriate regressions and the real stdio smoke test. Check direct/dispatcher behavior, compact/full output and profile/dialect compatibility where affected. Update each changed tool/operation's ledger row with actual exercised branches and gaps. Contract checks supplement native, numerical, document, host/model and final-delivery acceptance; do not replace those gates or relabel historical passes. Publication and installation require evidence for the exact packaged version.
