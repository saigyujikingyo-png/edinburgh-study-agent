# Verification

## Chat and cloud Work

0.5.1 recovered a fresh cloud task that had no course tools despite a healthy local tunnel. Actual ordinary Chat status/search and cloud Work status/live Learn refresh both passed after installing and connecting the personal ChatGPT app and adding its private package dependency. See [versioned acceptance](docs/WORK_ACCEPTANCE.md) for the observed scope.

## Historical campus and Work

0.5.0 was subsequently accepted in an actual Work turn for French/Arabic catalog queries, unchanged preferences, cached agenda coverage/timezone metadata, fresh Learn course listing and verified local PDF reuse. See the versioned scope below; populated agenda time conversion is synthetic coverage, not an observation from the empty live-account calendar cache.

The live Work acceptance on 2026-09-12 verified UoE Companion 0.4.0 identification, current Learn course refresh with result pagination, verified local PDF reuse without starting the browser, a fresh PDF download and text reading. Historical 0.3.0 acceptance also covered supported school pages, collections and local tasks. It used a Windows/Python 3.12 deployment and the plugin-owned campus profile. See [public scope](docs/WORK_ACCEPTANCE.md); personal receipts stay local.

Live acceptance is historical evidence. The automated tests below are synthetic and must not be reported as a fresh school login or all-site acceptance.

## Reproduce the checks

~~~powershell
python -m pip install -e ".[dev]"
python -m playwright install chrome
python -m pytest -q
python scripts/smoke_mcp.py
python scripts/public_release.py
python scripts/public_release.py --git-index
python scripts/package_plugin.py
~~~

The regression suite covers evidence integrity, dates and recurrence, planning, bounded downloads, file integrity, DOM selectors, deferred course rows, course status, folder selection, deep-link recovery, profile locking, worker errors, source boundaries, collections and document-text reading.

Release tests additionally cover staged-data auditing, release allowlists and isolated runtime installation configuration. The real stdio smoke test verifies 31 full-profile tools, structured results, input rejection and an isolated local-task round trip.

CI runs these checks using synthetic data on Windows and Linux, Python 3.11 and 3.12. The Actions result for a commit is the current CI record. It neither accesses a school account nor requires campus or Work secrets.

0.4.0 regression coverage includes database migration, Unicode and query-value isolation, cache integrity, assignment-file reuse, compact evidence provenance, pagination, bounded waiting and public icon validation.


0.5.0 adds tests for concurrent per-field preference writes, catalog aliases and fallback, RTL metadata, timezone/DST boundaries, linked deadline updates, unknown/date-only agenda records, filtering before pagination/export/planning, host configuration preservation/backups/idempotency and the 28-tool student stdio profile. The full suite has 107 tests.

An optional real [DeepSeek bridge probe](scripts/verify_deepseek.py) uses the official published package (0.0.1-rc.1 on the acceptance host), its config resolver, MCP transport/discovery/execution, official schema validator and text renderer. The registration/lifecycle fixture and synthetic data do not constitute a full Harness/model turn. It exposed a real nullable-schema incompatibility, now fixed through a portable catalog while server input validation remains enforced.

See [host evidence levels](docs/HOSTS.md) and [language boundaries](docs/LANGUAGES.md). Private runtime backups, host configuration backups and campus receipts are excluded from releases.


0.5.1 adds six regression cases for per-person ChatGPT binding, upgrade reapplication, conflict refusal, rollback, unknown-versus-verified connection state and public-package isolation. The full local suite has 113 tests. CI status must be checked for the exact release commit; it does not validate a real ChatGPT or campus account.
