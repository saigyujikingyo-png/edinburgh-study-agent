# Releasing

## 0.8.2 lifecycle repair candidate

This candidate scopes private Work supervision to one account/profile owner,
reconciles uncertain starts before retrying, preserves detached jobs during an
explicit stop, and migrates launcher files together with the runtime. Public tool
identities and version 1 output contracts remain unchanged. See
[lifecycle evidence and open gates](RUNTIME_LIFECYCLE.md).

Governance has allowed versioning, local review packages and a draft PR with CI.
This is not approval to merge, publish a release or install over existing accounts.
The released student preview remains 0.8.1. Product version 0.8.2, shared rules
2026-09-19.1 and output contract version 1 are separate.

Historical workflow evidence remains in [NMR 0.8.1](NMR_CONNECTION_ACCEPTANCE.md),
[file delivery 0.7.2](FILE_DELIVERY_ACCEPTANCE.md) and the
[contract ledger](OUTPUT_CONTRACTS.md); it is not new installed acceptance.

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
6. Return source/CI/package evidence and a reversible account migration plan for the
   installation gate. Preserve existing task preferences, credentials and jobs.
7. Merge, tag and publish only after the applicable separate approval. Rebuild if
   reviewed source changes; release only packages tied to the passing source.

The source archive includes the MIT license, notices and portable MCP template.
Fresh installation writes machine-specific configuration outside the checkout.
The targeted publication checker supplements review of free-form text and content.

## Windows review package

Build on Windows from the reviewed checkout:

```text
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/build_windows.py --wheel dist/edinburgh_study_agent-0.8.2-py3-none-any.whl
python scripts/package_plugin.py
```

Expected review artifacts are `UoE-Companion-0.8.2-Windows-x64.zip`,
`edinburgh-study-agent-0.8.2.zip`, their checksum sidecars, and the source wheel.
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
