# Releasing

## 0.7.2 student prerelease

This compatible update adds verified batch original-file delivery using standard MCP resources and fixes obsolete connection processes during upgrades. All 38 public tool identities and 21 advanced operations retain version 1 output contracts. See [0.7.2 acceptance](FILE_DELIVERY_ACCEPTANCE.md), [file delivery](FILE_DELIVERY.md) and the [contract ledger](OUTPUT_CONTRACTS.md) for tested branches and remaining host/campus gates.

The shared rule version (2026-09-14.1), output contract version (1) and product version (0.7.2) are separate. Publish as a prerelease while additional-user and full host/model acceptance remain open.

## Release procedure

1. Keep all campus profiles, downloads, private receipts and tunnel credentials outside this checkout.
2. Review the intended changes, update version metadata when behavior changes, and run the regression tests, stdio smoke test and `scripts/benchmark_contracts.py`. Check output schemas, structured errors and text parity; catalog byte counts are not token or billing measurements.
3. Run the publication checker on the source. Stage only reviewed source files and run it again with --git-index. This reads staged blobs rather than trusting a cleaned working tree.
4. Inspect the staged diff and filenames, commit, and push without rewriting existing history.
5. Wait for the GitHub Actions checks for that exact commit.
6. Build the source/plugin archive with scripts/package_plugin.py. The builder validates the complete input allowlist, checks common private-data patterns and tests ZIP integrity. It writes a SHA-256 sidecar.
7. Inspect and publish that archive and checksum against the passing commit. Do not upload old dist archives, installed runtimes or local acceptance files.

The archive includes the MIT license, notices and a portable MCP template. A fresh installer writes its machine-specific configuration outside the checkout. The checked-in configuration must never contain an absolute personal runtime path.

The publication check is a targeted safeguard. Human review is still required for free-form text and copyright content.

## Windows student installer

Version 0.7.2 additionally ships `UoE-Companion-0.7.2-Windows-x64.zip` and its checksum. Build on Windows from the reviewed checkout:

```text
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/build_windows.py --wheel dist/edinburgh_study_agent-0.7.2-py3-none-any.whl
```

The builder verifies the current wheel against source, downloads the pinned official CPython embeddable archive, verifies its published SHA-256, resolves dependency wheels against `requirements.lock`, and installs them into a fresh build directory. It retains licences and a public binary provenance inventory. It removes generated console launchers/build-path provenance because the product uses module entrypoints. No personal runtime is a build input.

Validate actual installation and repeat installation in isolated directories (including spaces/non-ASCII paths), configuration preservation, failure rollback, the local wizard and the bundled stdio runtime. The Windows/Python 3.13 CI job builds and executes this installer in addition to the normal regression suite. Review both source and runtime archive inventories before upload; publish only artifacts built from the passing commit.

Label 0.7.2 as a student **prerelease** until additional-user installation and the outstanding real host/model workflows are accepted. Include the installation guide, current compatibility limits, measured scope and checksums. Do not promote protocol timing or synthetic tests to model/token-billing evidence.
