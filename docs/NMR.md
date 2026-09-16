# NMR raw-data acquisition

UoE Companion adds a single `study_nmr` entrypoint for finding and downloading your NMR data. It uses HTTP/API requests, preserves original received ZIP bytes, and reuses `study_export_files` for host delivery. It does not operate instruments, book time, submit experiments, create accounts or process spectra.

## Two independent sources

The legacy [School of Chemistry page](http://nmr-server.chem.ed.ac.uk/index.html) links to the [teaching archive](http://nmr-server.chem.ed.ac.uk/cgi-bin/nmrstation.pl). Its maintenance notice points to the facility's SharePoint information site. That notice does **not** establish that historical files were migrated to [NOMAD](https://nmr-nomad.chem.ed.ac.uk/).

The user-supplied 2024 laboratory handout describes four-digit sample references, teaching groups **3OR** and **2OR**, raw ZIP downloads and subsequent processing in MestReNova. This first legacy adapter supports those two groups only. Credentials and the handout are not distributed in the plugin. Other groups need separate verified requirements.

NOMAD is a separate account and API, not the saved MyEd/Learn login. The university's public [deployed API documentation](https://nmr-nomad.chem.ed.ac.uk/api/api-docs/) and [NOMAD developer guide](https://www.nomad-nmr.uk/docs/getting-started/for-developers/) were checked on **16 September 2026**. The independently written client uses:

- `POST /api/auth/login` for protected username/password sign-in and a bounded session token.
- The deployed frontend's `/api/search/experiments` for escaped literal sample searches, pagination and one date-range filter. This unversioned adapter is isolated and validates its response shape.
- `GET /api/v2/auto-experiments` for an observed exact dataset and the authenticated user's ID.
- `POST /api/v2/auto-experiments/download?id=...` for **one explicit experiment ID**. Empty IDs, multi-ID downloads, redirects and arbitrary hosts are rejected.

The frontend dataset ID and v2 experiment ID have different meanings. The adapter checks ownership and exact experiment identity before a download. It avoids the v2 start/end-date combination whose upstream implementation can overwrite one date constraint. Search results are not assumed to be a complete archive.

Upstream protocol review used [nomad-server at aba97242af9273c614cb52fd882afb609bf3223f](https://github.com/nomad-nmr/nomad-server/tree/aba97242af9273c614cb52fd882afb609bf3223f). Its root licence is AGPL-3.0; no upstream implementation was copied into this MIT-licensed client.

## Ask, connect and resume

Natural-language examples:

- “Find my NMR sample 0042 from the old teaching archive.”
- “Download the experiment from 12 March, keeping the raw data.”
- “Find my NOMAD sample and attach the original ZIP.”

`sample` is text; leading zeros are significant. `find` returns a saved `request_id`. If information is missing, the agent asks for only the listed non-secret fields and calls `resume` with the same ID. Changing source, sample, group, archive or date invalidates the previous selection and scoped HTTP consent. The last 100 request contexts are retained privately.

| State | Agent action |
| --- | --- |
| `needs_input` | Ask for the listed sample/source/group/consent information; preserve the request. |
| `needs_auth` | Offer the protected plugin connection panel using `connect`; never ask for a password in chat. |
| `authentication_pending` | Complete protected input, then resume the same request. Opening the panel alone is not authentication. |
| `needs_selection` | Ask which returned date/dataset/experiment is intended. Do not download all ambiguous matches. |
| `ready` | Use a returned selection ID, or download the unique saved selection. |
| `no_matches` | State the selected search coverage; ask about date/group/backup. Do not claim data never existed or was migrated. |
| `downloaded` | Original received bytes passed container/member validation. Use file export for host delivery. |
| `unavailable` | Report the stable code and retained request. Do not loop or silently switch to browser automation. |

`download` can combine search and acquisition when a new query has exactly one result. A repeated download of a saved selection checks and reuses its intact cache without repeating the network search or transfer. `forget` removes the selected NMR connection, preserving downloaded data.

Legacy requests default to the explicitly reported archive range **2015-01-01 through today** unless a narrower date is supplied. The default is deliberately wider than the old page's one-year form window. Backup is a separate, user-selected scope; the adapter does not scan all groups or follow username/history links. There is no guarantee that every historic file is still retained.

## Protected credential adapter

Passwords are **not MCP parameters**, elicitation form fields, model text, source files or log content. `connect` opens a temporary plugin-owned loopback panel; the user enters the NMR credential there, without navigating the school's form. A capable host receives a standard **URL-mode elicitation** request; other hosts receive the same protected link and resumable request. The MCP specification [forbids collecting passwords through ordinary form elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation).

The panel has a ten-minute lifetime, exact Host/Origin checks, a separate CSRF nonce, bounded requests, no external assets, no access logs and no public listener. Successful submission or disconnection invalidates it. Windows saves the session using current-user DPAPI; NOMAD passwords are discarded after login. Other operating systems keep sessions only in the running process. Expired or rejected sessions require protected reconnection; automatic renewal/account provisioning is not implemented.

**Reachability matters:** the panel must be opened by a browser on the computer running UoE Companion. A cloud model can continue using that connected backend, but a phone or another computer cannot open its loopback panel. Real URL-elicitation UX in each host remains a separate acceptance gate. The plugin does not claim a universal inline credential widget or remote secure-setup service.

The old archive serves HTTP. Its HTTPS certificate failed ordinary validation during this check. The plugin never disables certificate verification: it asks explicit consent before sending the teaching-group credential over HTTP for the saved query. ZIP CRC/SHA-256 checks establish byte integrity, **not encrypted transport or source authenticity**. No old credential is reused against NOMAD.

## Data and delivery contracts

Each acquisition binds source, account/group, observed sample selection, observation time, dataset and experiment. Only recorded selections can be downloaded; generic cached page capture cannot manufacture an NMR download authorization. Received ZIPs remain unchanged and are not automatically extracted.

Validation checks safe member paths, exact expected dataset/experiment containment, CRCs, per-member hashes and nonempty Bruker `fid` or `ser` plus root `acqus`. The old archive's verified group/user parent directories are also bound. Limits: 2,000 members, 256 MiB uncompressed total, 200:1 per-member compression ratio, 8 MiB metadata, stored/deflate only. Full ZIP64 central directories, multipart and unsupported layouts fail explicitly. No scientific interpretation is inferred from these checks.

Network transfers use bounded timeouts and streaming, with a 32 MiB default download budget, adjustable up to 128 MiB. Partial/invalid transfers are not registered as downloads. The original ZIP and an integrity manifest are retained in the private cache. NOMAD may construct a ZIP on demand; “original” means the exact received container and raw member bytes, not an asserted bit-identical historical server container.

`study_export_files` exports Learn or NMR originals through the same delivery contract, up to its existing **32 MiB aggregate** budget. The result is `awaiting_host_receipt`, not a cloud upload claim. A local path, `uoe://` URI or MCP blob is not a Google Drive file reference. Host materialization and destination readback remain necessary. Large NMR downloads can be valid local acquisitions while exceeding the current host export budget.

## Acceptance boundaries

Source/protocol discovery, synthetic checks, actual archive retrieval, host credential UX, scientific processing and final attachment/storage delivery are distinct results. Current live NOMAD authentication and acquisition are **unverified** because the testing user does not yet have a NOMAD account. The old archive can be tested independently. See the version's verification record for actual test and acquisition evidence; neither a listed tool nor a configured host proves an end-to-end run.
