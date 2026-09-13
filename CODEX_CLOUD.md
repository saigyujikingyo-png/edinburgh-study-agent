# UoE Companion: Codex cloud development

Part of the [Chembridge cloud workspace](https://github.com/saigyujikingyo-png/chembridge). Read [shared principles](DEVELOPMENT_PRINCIPLES.md) and [contributor instructions](AGENTS.md) first.

This environment checks the portable core, synthetic browser fixtures and stdio MCP transport. Browser installation, when needed on a non-root runner, is limited to the test environment; root containers skip that download. It does not log into a university account or import a private browser profile.

## Environment configuration

Select this repository in Codex Web and name the environment **Chembridge / UoE Companion**. Use the universal image with Python 3.12 and caching. Use the same setup and maintenance command:

```bash
bash scripts/setup_codex_cloud.sh
```

The setup uses a repository-local `.venv`; it does not combine this product's dependencies with another plugin. No OpenAI API key, campus session, tunnel secret or vendor licence is required for these checks.

## Verification commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_mcp.py
.venv/bin/python scripts/public_release.py --git-index
```

The Codex universal container currently runs as root. The four synthetic DOM tests require sandboxed Chrome under a non-root user, so they report explicit skips in that container; the browser sandbox is not disabled. Run those tests in the existing non-root Ubuntu/Windows CI matrix and record its result separately. Remaining portable tests and the real stdio smoke test run inside the cloud virtual environment.

Record the tested commit, runtime, command output and failures/skips. A setup or protocol pass is not native-software, account, host/model or final-artifact acceptance. Keep those results in this product's own records. Environment configuration does not change source ownership or authorise edits to another task's branch.

See the [Chembridge catalog and cloud guide](https://github.com/saigyujikingyo-png/chembridge) for the shared entrypoint and future-plugin process. Environment creation and real test results are recorded separately; this setup document does not claim a completed native release.
