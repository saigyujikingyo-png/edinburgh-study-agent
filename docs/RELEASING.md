# Releasing

1. Keep all campus profiles, downloads, private receipts and tunnel credentials outside this checkout.
2. Review the intended changes, update version metadata when behavior changes, and run the regression tests and stdio smoke test.
3. Run the publication checker on the source. Stage only reviewed source files and run it again with --git-index. This reads staged blobs rather than trusting a cleaned working tree.
4. Inspect the staged diff and filenames, commit, and push without rewriting existing history.
5. Wait for the GitHub Actions checks for that exact commit.
6. Build the source/plugin archive with scripts/package_plugin.py. The builder validates the complete input allowlist, checks common private-data patterns and tests ZIP integrity. It writes a SHA-256 sidecar.
7. Inspect and publish that archive and checksum against the passing commit. Do not upload old dist archives, installed runtimes or local acceptance files.

The archive includes the MIT license, notices and a portable MCP template. A fresh installer writes its machine-specific configuration outside the checkout. The checked-in configuration must never contain an absolute personal runtime path.

The publication check is a targeted safeguard. Human review is still required for free-form text and copyright content.
