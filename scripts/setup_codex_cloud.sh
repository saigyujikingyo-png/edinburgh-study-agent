#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [ ! -x .venv/bin/python ]; then uv venv --python 3.12 .venv; fi
uv pip sync --python .venv/bin/python requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
if [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' 'Sandboxed DOM checks require a non-root runner; Chrome installation is skipped here.'
elif ! command -v google-chrome >/dev/null 2>&1; then
    .venv/bin/python -m playwright install --with-deps chrome
fi
printf '%s\n' 'UoE portable-test environment ready; no campus account or private browser profile is configured.'
