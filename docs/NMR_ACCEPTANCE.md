# NMR 0.8.0 verification record

Checked on **16 September 2026**, Windows, Python 3.12.14. This is an independent student preview. Private sample numbers, names, passwords, file names, hashes, request IDs and full receipts are intentionally omitted.

| Gate | Evidence and limit |
| --- | --- |
| University source | The supplied 2024 NMR handout, current old archive/search form, current NOMAD login/API documentation and public upstream protocol were inspected. No historical migration was inferred. |
| Legacy real acquisition | One user-authorized, uniquely matching teaching-archive record was retrieved through the actual `study_nmr` MCP boundary. The 1,224,471-byte ZIP contained 42 members / 33 files and 1,693,110 uncompressed bytes. Raw `fid`, `acqus`, CRCs, containment and member hashes passed. |
| Original byte export | `study_export_files` materialized the cached bytes into an MCP resource; decoded size and SHA-256 matched the acquisition. A ChatGPT attachment or cloud-storage upload was **not** tested for this NMR record. |
| NOMAD live authentication | **Unverified**: the testing user has no NOMAD account. Public protocol discovery and synthetic request tests do not establish authenticated live acceptance. |
| Protected input | Real local HTTP tests and current-user Windows DPAPI passed. Disconnect invalidates pending forms, including an in-flight login/save race. Passwords were not exposed as MCP inputs or results. Real host URL-elicitation UX is **unverified**. |
| Host boundary | One shared stdio implementation; 38 full / 35 student / 15 daily tools. Per-host model conversations and credential-panel reachability are not implied by those catalogs. Mobile/remote panel setup is unsupported. |
| Scientific use | Raw acquisition and integrity only. No processing, peak assignment, instrument actions or scientific interpretation was performed. |

The temporary teaching credential used for live verification was removed afterwards. The saved raw-data cache remains available through its recorded selection and export contract. HTTP consent was specific to that acquisition; no TLS-verification bypass was used. Hash validation does not make HTTP confidential or authenticate its source.

## Measured execution

The actual backend call that searched and downloaded the unique record took **0.823 seconds**. Repeating its saved selection used the verified cache in **0.030 seconds**, without another source query or transfer. These are one observed run, not a latency guarantee or full agent-turn timing.

The isolated stdio benchmark used three warm status calls per profile:

| Profile | Tools | Serialized catalog bytes | Initialization | Warm status median |
| --- | ---: | ---: | ---: | ---: |
| Full | 38 | 209,962 | 960.65 ms | 25.85 ms |
| Student | 35 | 196,708 | 920.72 ms | 25.45 ms |
| Daily | 15 | 90,698 | 966.80 ms | 25.95 ms |

The daily catalog retains on-demand advanced discovery. These are UTF-8 sizes and local protocol timings, **not actual tokens, billing, quota or model-efficiency measurements**. No Terra-max/model benchmark was performed in this verification. No second model/provider or permanent service was added.

## Reproducible checks

Run `python -m pytest -q`, `python scripts/smoke_mcp.py` and `python scripts/benchmark_contracts.py --iterations 3` from an installed development environment. Synthetic NMR checks cover protocol identity/ownership, escaped leading-zero references, missing fields, resume/selection, credential expiry, cancellation, unsafe ZIPs, source-layout changes, cache corruption and unchanged original delivery. Full regression, public-source audit, exact-commit CI and packaged-runtime checks are separate release gates; release/installation receipts record their final results.

No private campus fixture, downloaded NMR file or credential is included in public tests, GitHub source or release assets. The [NMR guide](NMR.md) describes supported methods and remaining limits.
