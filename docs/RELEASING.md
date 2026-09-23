# Releasing

## 0.8.7 Learn inline originals

The shared core indexes visible document attachments and reuses the existing original-file downloader. Preserve the 15/35/38 catalogs, campus sessions, account identities and runtime lifecycle. Verify source binding, actual byte counts and hashes; keep package/installed and host-model evidence separate. See [Learn attachments](LEARN_ATTACHMENTS.md).

## 0.8.6 NOMAD browsing and VPN guidance

Publish one shared core with the existing 15/35/38 daily/student/full catalogs. Recent NOMAD browsing, retained pagination and VPN diagnostics add no runtime dependency or lifecycle changes. Keep the source live-account result separate from packaged/installed and model-host acceptance. Preserve existing DPAPI sessions and both account connector identities during upgrade. See [NOMAD evidence](NOMAD_ACCEPTANCE.md).

## 0.8.4 Learn recovery and file updates

The current preview distinguishes campus network/login failures, preserves saved sessions during outages, shares worker exception identity and adds bounded metadata-change checks through `study_materials(operation="updates")`. See [behavior and verification boundaries](LEARN_RECOVERY.md). It includes the earlier 0.8.3 connection repair. Preserve any installed base-plus-overlay receipt during a full upgrade; never replay the old maintenance transaction.


## 0.8.3 command-encoding repair

This preview fixes the nested MCP command encoding used to start the Windows
remote connector. It restores forward-slash paths and explicit quoting while
preserving credentials, account identity, retries and ownership rules. See
[repair evidence and overlay limits](WORK_COMMAND_REPAIR.md). The 0.8.2 lifecycle
implementation record is historical and is not current installed acceptance.

Publish source, wheel and Windows bundle from the same reviewed source. Record
source tests, actual official-client parser/child-start checks, package integrity,
installed identity and each remote account call separately. An exceptional one-file
overlay on 0.8.2 must retain explicit base-plus-overlay provenance; it is not a full
0.8.3 installation. Private maintenance receipts and helpers are never released.

## Candidate and release procedure

1. Keep campus profiles, downloads, private receipts and credentials outside this checkout.
2. Review scope and version metadata. Run regression tests, the stdio smoke test and
   `scripts/benchmark_contracts.py`. Schema sizes are not token or billing measurements.
3. Run the publication checker, stage only reviewed source, then run
   `scripts/public_release.py --git-index` against exact staged blobs.
4. Inspect and commit the staged changes. Push the branch without rewriting history,
   create a draft PR and wait for GitHub Actions on that exact commit.
5. Build and inventory local source, wheel and Windows review packages from the same
   source. Verify ZIP integrity, source/module parity and SHA-256 sidecars. Do not
   upload old archives, installed runtimes or private acceptance receipts.
6. Record source/CI/package evidence and a reversible account migration plan for the
   installation gate. Preserve existing task preferences, credentials and jobs.
   Product Max owns technical verification under the current user authorization;
   the shared-principles task is not an external technical sign-off gate.
7. Merge, tag and publish within the user's authorized release scope. Rebuild if
   reviewed source changes; release only packages tied to the passing source.

The source archive includes the MIT license, notices and portable MCP template.
Fresh installation writes machine-specific configuration outside the checkout.
The targeted publication checker supplements review of free-form text and content.

## Windows review package

Build on Windows from the reviewed checkout:

```text
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/build_windows.py --wheel dist/edinburgh_study_agent-0.8.4-py3-none-any.whl
python scripts/package_plugin.py
```

Expected review artifacts are `UoE-Companion-0.8.4-Windows-x64.zip`,
`edinburgh-study-agent-0.8.4.zip`, their checksum sidecars, and the source wheel.
Candidate package names do not mean a public release exists. The bundled guide's
versioned release link becomes available only after publication.

The builder compares the complete wheel module inventory to current source,
verifies the pinned official CPython archive and resolves dependency wheels against
`requirements.lock`. It builds a fresh directory, retains licenses and a public
binary provenance inventory, and removes local build-path provenance and unused
console launchers. No personal runtime is an input.

The Windows/Python 3.13 CI job builds and executes the installer in disposable
directories. Focused fixtures cover multi-account migration, repeated installation,
configuration preservation, locking and failure rollback. The opt-in real Task
Scheduler fixture is separate; it uses only synthetic processes and removes its
own registration. Neither CI nor that fixture authorizes existing-account changes.

For an approved two-account upgrade, use the staged new controller to quiesce old
launchers, not the old task tree-stop script. Record original startup preferences,
identities and file hashes; reject unknown/active ownership. Verify and retain both
runtime and launcher backups. Restore the original task preferences after success
or rollback. Fresh status calls in each account follow local installed readback;
campus authentication and OS-event testing remain separate gates.

Keep student releases labelled **prerelease** until additional-user installation
and outstanding host/model workflows are accepted. Include installation guidance,
known limits, rollback instructions and checksums without promoting synthetic
timing into end-user efficiency or token-billing claims.
