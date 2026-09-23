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

## Recent NOMAD data and campus VPN

Use `study_nmr(action="list")` when you do not know the sample number. The default is your own NOMAD account, with ten datasets per page (maximum twenty), newest archived first. Optional `start_date` / `end_date` use the deployed archive's inclusive day-range filter. Results retain submission timestamps, observation time, page, limit, total datasets and explicit partial coverage. Do not present the first page as the full archive.

Listing does not download even a single matching dataset automatically. Pass an observed `dataset_name` as `selection_id` with the same `request_id` to `resume` for experiment choices, or `download` for a unique experiment. Multiple experiments still require an explicit choice. Resuming after login retains the date range, page and page size. Historical teaching data is not silently searched or assumed migrated.

Off campus, the runtime computer needs the University of Edinburgh network through **FortiClient VPN**. A browser login on another device does not provide that network route. Real NMR network/transfer failures trigger one bounded, read-only local adapter check. The reply distinguishes an inactive Fortinet adapter, an active adapter with an unreachable service, and an unknown VPN state. An active adapter alone does not prove the correct campus route. Saved login, request and selections are retained; connect/check the campus VPN, then resume the same request. No automatic VPN connection, credential reading, setting changes or blind retry occurs.

Successful queries and cached reads do not launch the adapter check. On Windows it uses built-in PowerShell hidden with a four-second deadline and exposes only boolean adapter state. Other platforms or unavailable adapter information return an honest unknown with campus-access guidance. Protected login panels also distinguish a network failure from rejected credentials, in English and Chinese. Actual VPN on/off transitions are a separate acceptance gate; see [NOMAD verification](NOMAD_ACCEPTANCE.md).

## Ask, connect and resume

Natural-language examples:

- “Find my NMR sample 0042 from the old teaching archive.”
- “Download the experiment from 12 March, keeping the raw data.”
- “Find my NOMAD sample and attach the original ZIP.”
- “Show my NMR data from yesterday; I do not know the sample number.”

`sample` is text; leading zeros are significant. `find` returns a saved `request_id`. If information is missing, the agent asks for only the listed non-secret fields and calls `resume` with the same ID. Hosts advertising MCP form elicitation may show these fields in their own small input form. No password or token can enter that form. A resumed download remains a download, including after dataset selection. Changing source, sample, group, archive or date invalidates the previous selection and query-only HTTP consent. A remembered connection reuses only its own group-scoped HTTP permission. If exactly one compatible connection is saved, its source/group is selected automatically; ambiguous connections are not tried in turn. The last 100 request contexts are retained privately.

| State | Agent action |
| --- | --- |
| `needs_input` | Ask for the listed sample/source/group/consent information; preserve the request. |
| `needs_auth` | The school rejected a connection. Use `connect` to replace it through protected input; do not retry the rejected credential. |
| `connected` | The existing connection is available. Continue the sample request; do not open a new credential form. |
| `authentication_pending` | Complete protected input, then resume the same request. Opening the panel alone is not authentication. |
| `needs_selection` | Ask which returned date/dataset/experiment is intended. Do not download all ambiguous matches. |
| `ready` | Use a returned selection ID, or download the unique saved selection. |
| `no_matches` | State the selected search coverage; ask about date/group/backup. Do not claim data never existed or was migrated. |
| `downloaded` | Original received bytes passed container/member validation. Use file export for host delivery. |
| `unavailable` | Report the stable code and retained request. Do not loop or silently switch to browser automation. |

`download` can combine search and acquisition when a new query has exactly one result. A repeated download of a saved selection checks and reuses its intact cache without repeating the network search or transfer. `connect` reuses saved credentials; `reconnect` creates a fresh replacement panel and invalidates the previous panel for that request. A form rejected by its browser-origin check is renewed on the next `connect`, instead of recycling the same failed link. `forget` removes the selected NMR connection, preserving downloaded data.

Legacy requests default to the explicitly reported archive range **2015-01-01 through today** unless a narrower date is supplied. The default is deliberately wider than the old page's one-year form window. Backup is a separate, user-selected scope; the adapter does not scan all groups or follow username/history links. There is no guarantee that every historic file is still retained.

## Protected credential adapter

Passwords are **not MCP parameters**, elicitation form fields, model text, source files or log content. When credentials are missing, `find`/`download` offers a temporary plugin-owned loopback panel directly; `connect` can also offer it; the user enters the NMR credential there, without navigating the school's form. A capable host receives a standard **URL-mode elicitation** request; other hosts receive the same protected link and resumable request. The MCP specification [forbids collecting passwords through ordinary form elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation).

The small form follows the browser's English/Chinese language and light/dark preference. It uses no JavaScript or external assets. Samples are normally answered in chat or a host form, so ordinary use does not require opening a browser.

On Windows, **Remember this connection** saves the old teaching group's credential with current-user DPAPI until replacement, server rejection or `forget`. Its checkbox is shown explicitly and selected by default. HTTP consent is given in the same form and retained only for that group; later samples do not need another setup/consent round. Leaving Remember unchecked keeps the previous one-hour temporary behavior. Existing 0.8.0 temporary credentials are not silently promoted to remembered credentials. Other operating systems still use process memory only, as explained in the form.

NOMAD passwords are still discarded after successful login. Its encrypted token is reused until the server expires or rejects it; automatic password-based renewal/account provisioning remains unimplemented.

The panel has a ten-minute lifetime, exact Host/path checks, a separate CSRF nonce, a per-panel HttpOnly/SameSite cookie, bounded requests, no access logs and no public listener. Foreign origins and cross-site requests are rejected. Missing/null Origin is accepted only with the exact same-panel Referer, matching cookie and nonce. `Referrer-Policy: same-origin` fixes the normal form POSTs rejected by 0.8.0's `no-referrer` policy, while keeping the local URL out of off-site referrers. See [MDN's Origin-header explanation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin). Successful submission or disconnection invalidates the panel. Opening or replacing this **local form** sends no credential to the school and does not require a new HTTP-transmission approval.

**Reachability matters:** the panel must be opened by a browser on the computer running UoE Companion. A cloud model can continue using that connected backend, but a phone or another computer cannot open its loopback panel. Real URL-elicitation UX in each host remains a separate acceptance gate. The plugin does not claim a universal inline credential widget or remote secure-setup service.

The old archive serves HTTP. Its HTTPS certificate failed ordinary validation during this check. The plugin never disables certificate verification: it requires explicit consent before sending the teaching-group credential over HTTP, either for the saved query or through the remembered group connection. ZIP CRC/SHA-256 checks establish byte integrity, **not encrypted transport or source authenticity**. No old credential is reused against NOMAD.

## Data and delivery contracts

Each acquisition binds source, account/group, observed sample selection, observation time, dataset and experiment. Only recorded selections can be downloaded; generic cached page capture cannot manufacture an NMR download authorization. Received ZIPs remain unchanged and are not automatically extracted.

Validation checks safe member paths, exact expected dataset/experiment containment, CRCs, per-member hashes and nonempty Bruker `fid` or `ser` plus root `acqus`. The old archive's verified group/user parent directories are also bound. Limits: 2,000 members, 256 MiB uncompressed total, 200:1 per-member compression ratio, 8 MiB metadata, stored/deflate only. Full ZIP64 central directories, multipart and unsupported layouts fail explicitly. No scientific interpretation is inferred from these checks.

Network transfers use bounded timeouts and streaming, with a 32 MiB default download budget, adjustable up to 128 MiB. Partial/invalid transfers are not registered as downloads. The original ZIP and an integrity manifest are retained in the private cache. NOMAD may construct a ZIP on demand; “original” means the exact received container and raw member bytes, not an asserted bit-identical historical server container.

`study_export_files` exports Learn or NMR originals through the same delivery contract, up to its existing **32 MiB aggregate** budget. The result is `awaiting_host_receipt`, not a cloud upload claim. A local path, `uoe://` URI or MCP blob is not a Google Drive file reference. Host materialization and destination readback remain necessary. Large NMR downloads can be valid local acquisitions while exceeding the current host export budget.

## Acceptance boundaries

Source/protocol discovery, synthetic checks, actual archive retrieval, host credential UX, scientific processing and final attachment/storage delivery are distinct results. On 23 September 2026, one personal NOMAD account completed protected sign-in, bounded date-range discovery, exact experiment selection, a fresh validated ZIP transfer and cache reuse through the source candidate's actual daily stdio MCP boundary. See [0.8.6 NOMAD acceptance](NOMAD_ACCEPTANCE.md). This does not establish every account, instrument, remote host, token-renewal path or final attachment delivery. The old archive can be tested independently. See the version's verification record for actual test and acquisition evidence; neither a listed tool nor a configured host proves an end-to-end run.
