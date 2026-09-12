# Verification

## Campus and Work

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

Release tests additionally cover staged-data auditing, release allowlists and isolated runtime installation configuration. The real stdio smoke test verifies 28 tools, structured results, input rejection and an isolated local-task round trip.

CI runs these checks using synthetic data on Windows and Linux, Python 3.11 and 3.12. The Actions result for a commit is the current CI record. It neither accesses a school account nor requires campus or Work secrets.

0.4.0 regression coverage includes database migration, Unicode and query-value isolation, cache integrity, assignment-file reuse, compact evidence provenance, pagination, bounded waiting and public icon validation.
