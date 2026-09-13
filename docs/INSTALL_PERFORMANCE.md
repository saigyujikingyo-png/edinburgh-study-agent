# Installation and efficiency — 0.7.0 student preview

This release adds a Windows x64 installation bundle, a temporary local setup page and a compact daily tool profile. It preserves the same product identity, private campus directory and original student/full tool profiles. It does not add hosted multi-user service or new school write operations.

## Installation behaviour

- Bundled official Python 3.13.15 and pinned runtime dependencies; no user-installed Python, Git or development environment for the Windows setup route.
- English/Chinese setup page, selected WorkBuddy/Claude Desktop configuration merge, private documents for other hosts and an explicit ChatGPT account-connection guide.
- Manifest verification, candidate-runtime MCP check with isolated data, runtime backup, exact host-configuration backups, failed-install rollback and repeat-install detection.
- Existing school profile/data and ChatGPT identity are preserved. Busy runtimes are reported rather than killed. The setup helper uses loopback, rejects foreign origins and expires when idle or closed.

Actual Windows tests used isolated installation directories containing spaces and Chinese characters, a bundled executable with system Python removed from PATH, and a host configuration containing an unrelated server. The installed 0.7.0 runtime exposed 13 daily tools and passed MCP initialization/discovery/calls. The unrelated server was retained. Transactional failure, invalid/tampered bundle, host conflict, duplicate installer and local-HTTP boundary tests use synthetic fixtures; they do not represent a second student's campus account.

The setup page was exercised with real Chrome DOM controls, including Chinese labels, the installation-location expander, install, repeat install and Finish. No screenshots or coordinate clicks were used. The verified runs took 27.4 seconds for installation, 18.9 seconds for repeat checks and 9.5 seconds for an isolated upgrade with an existing host config. The previous runtime backup was retained. Two earlier acceptance-script attempts were corrected for a collapsed field and CSP-incompatible test polling; the page security policy was not relaxed. These times exclude downloading/extracting the ZIP and personal account setup.

## Measurements on 2026-09-13

Same Windows x64 development machine. Startup/catalog/status comparison used Python 3.12 for both source versions, three isolated MCP sessions each. No model generated these calls. Timings are local measurements, not guarantees for other devices or providers.

| Measurement | 0.6.0 student | 0.7.0 daily | Interpretation |
| --- | ---: | ---: | --- |
| Advertised tools | 33 | 13 | Advanced operations remain available on demand |
| Serialized tool catalog | 21.8 KB | 7.5 KB | About 66% less UTF-8 data |
| Initialization instructions | 2,414 bytes | 595 bytes | About 75% less UTF-8 data |
| Median initialize + list | 887 ms | 900 ms | No significant startup speedup established |
| Median status call | 22.61 ms | 21.72 ms | Similar local response time |
| Same eleven-week PDF default response | 24,698 bytes | 9,624 bytes | About 61% less data; new default is explicitly marked previews |
| Stored PDF layout cache | 146,313 bytes | 47,576 bytes | Duplicate raw page/table text omitted; original PDF retained |
| Median cached PDF document read | 4.729 ms | 4.769 ms | Similar parsing-cache response time |
| Synthetic cached-job receipt, median | 7.356 ms | 0.193 ms | Reuse avoids repeated receipt-file writes; excludes campus/network/model time |
| Receipt files for nine identical synthetic calls | 9 | 1 | Changed source data still receives a new receipt |

PDF comparison used one already-downloaded private course file and seven cached reads per version. The full-detail week/day cells matched exactly; private filenames, account data and contents are excluded here. The shorter default shows at most 128 characters per day cell and lists `truncated_days`. `view="occurrences"` returns full cells; an optional `week` selects a particular labelled week. Summaries must not be presented as complete individual class allocations.

The receipt test used nine identical synthetic results per version. Its improvement concerns receipt persistence only. It is not a claim that live school queries or WorkBuddy conversations became 38 times faster.

Reproduce isolated MCP measurements with `scripts/benchmark_student.py`. Result sizes measure one serialized text/catalog representation, not actual model billing. MCP text and structured results are both retained for client compatibility; hosts may consume either or both.

## Acceptance boundaries

The regression suite, original full-profile stdio smoke check and new daily-profile calls cover schema validation, advanced dispatch, cache reuse, full PDF detail recovery, configuration preservation and rollback. Windows installation tests exercise the bundled interpreter; the source tests additionally cover supported Python versions in CI.

Local regression result: 181 passed. The full-profile smoke check retained 36 tools; the daily profile validated actual advanced-tool discovery, a synthetic task roundtrip, rejection of invalid estimates and rejection of legacy capture dispatch.

These checks do not establish a new WorkBuddy/Claude/DeepSeek/Codex model conversation, each Chat/local Work/cloud Work workflow, a different student's account, or end-to-end artifact attachment delivery. The previous WorkBuddy model follow-up was deferred by the user. There is no GPT-5.6 Terra max model run or measured input/cached/output/reasoning-token bill for this release. Those remain separate acceptance work.

University email is handled by Outlook and is outside the product scope. Full Learn message bodies, university-wide event coverage and school write operations retain their documented limits.
