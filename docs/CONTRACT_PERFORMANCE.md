# 0.7.1 contract protocol measurements

Measured on 14 September 2026 with Windows, Python 3.12.14 and the current 0.7.1 source, using `python scripts/benchmark_contracts.py`. Each profile launches a fresh real stdio server with an isolated empty data directory, initializes and lists tools, then performs one cold and ten warm `study_status` calls. No campus session, account, documents or model is used. The daily probe also describes and invokes `study_tasks` through the dispatcher and verifies structured/text parity.

| Profile | Tools / output schemas | Catalog UTF-8 bytes | Discovery ms | First status ms | Warm status median / max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| full | 36 / 36 | 194,954 | 60.14 | 76.52 | 26.79 / 29.11 |
| student | 33 / 33 | 181,700 | 61.74 | 75.13 | 32.49 / 37.33 |
| daily | 13 / 13 | 76,319 | 29.76 | 78.31 | 35.43 / 40.13 |

Initialization, including process startup, was 864–939 ms. Warm status response sizes were 2,572–2,870 bytes. These are elapsed local protocol times and serialized `model_dump_json(by_alias=True, exclude_none=True)` byte counts, not packet traffic, model latency, tokens, billing or quota. OS load and concurrent tests affect timings; no comparative latency improvement is established by this single run.

The daily catalog is about 61% smaller than the current full catalog. Output schemas increase catalog size compared with the historical 0.7.0 catalogs, which declared no output schemas (25,786 / 21,807 / 7,535 bytes respectively). Do not describe that increase as token savings. The daily dispatcher exposes detailed advanced schemas on demand, and school job payload schemas are also available on demand; neither expands the default menu into every possible operation payload. Validators and advertised schemas are cached in each server process.

## Reproduce

```text
python scripts/benchmark_contracts.py --iterations 10
python scripts/smoke_mcp.py
python -m pytest -q
```

The JSON report records its exact product/Python versions, timestamp, profile counts, bytes, timings and synthetic-data scope. Actual model tokens and billing remain explicitly null. The smoke test verifies advertised output schemas, structured success/errors, matching JSON text, and an isolated local task create/update round trip. The contract tests separately reject malformed values without retrying writes and preserve known saved identifiers.

## Acceptance boundary

A GPT-5.6 Terra / max workflow benchmark requires a real model conversation with fixed requests, per-call timing, retries and actual usage when available. It is separate from this protocol probe. WorkBuddy, Claude and DeepSeek model behavior and additional students' installations are not established here. Release CI, installed-account checks and artifact delivery must be reported separately; see [contract coverage](OUTPUT_CONTRACTS.md) and [host evidence](HOSTS.md).
