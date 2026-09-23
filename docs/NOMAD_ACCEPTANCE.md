# NOMAD 0.8.6 acceptance

Checked on 23 September 2026, Windows, one user's own NOMAD account. Private sample names, account identities, tokens, connection URLs, request IDs and file hashes remain outside the publication.

## Behavior

The existing direct-HTTP adapter now lists a bounded page of the authenticated user's datasets without requiring a sample number. Dataset and experiment selection remain distinct; acquisition uses one observed experiment. Date range and pagination survive authentication/resume. The old teaching archive remains separate.

Real network/transfer failures return explicit FortiClient guidance with a retained request. A disconnected adapter, active adapter with an unreachable service and unknown adapter state are distinct observations. Detection is read-only, hidden, bounded to four seconds and used only after failure. It never toggles VPN settings, reads VPN credentials, replaces login, retries a download or adds a resident process. Successful queries use no adapter subprocess.

## Evidence

| Gate | Observed result and limit |
| --- | --- |
| Source regression | 700 passed, 5 explicit skips on Windows in 66.28 seconds. Focused cases include personal ownership, observed selection, retained pagination, original ZIP safety, secure input and VPN failure recovery. |
| Protocol | Real stdio smoke passed. Full/student/daily catalogs retain 38/35/15 tools, each with a validated output schema and matching JSON text fallback. Serialized catalogs measured 232,880 / 219,278 / 104,614 UTF-8 bytes; these are not billed token counts. |
| Deployed API | The university API documentation responded over ordinary HTTPS. A personal, bounded archive query returned ownership metadata and the deployed frontend shape expected by the adapter. Upstream protocol ordering is newest lastArchivedAt, with stable dataset tie-breaking. |
| Secure sign-in | The user entered NOMAD credentials in the protected plugin panel. A current-user DPAPI session was saved and reused. No password or token entered model arguments, public output or source. This is not shared MyEd authentication. |
| Real daily MCP | The source candidate exposed 15 tools. A date query found one dataset; selection returned one experiment. Listing, selection, fresh acquisition and cached readback validated against their output schema and matched their JSON text fallback. |
| Fresh raw ZIP | 1,321,140 received bytes; 41 members / 32 files; 1,314,308 uncompressed bytes. Exact dataset/experiment containment, nonempty fid, acqus, CRCs and member hashes passed. No extraction, spectral processing or source mutation occurred. |
| Cache reuse | The same selected original returned cache_hit=true with no repeated download. |
| VPN | The runtime device reported an active Fortinet VPN adapter during the successful live query. Synthetic tests cover inactive/active/unknown detection, bounded hidden queries, no retry, credential retention and protected-panel network messages. The real VPN was not disconnected for testing. |
| Limits | Installed runtime, each remote account, model-host conversations, other accounts/instruments, token renewal and final attachment/cloud-storage delivery require separate evidence. These source results do not imply those passes. |

## One observed source run

| Operation | Tool time |
| --- | ---: |
| Personal dataset list | 284.95 ms |
| Select and inspect experiment | 162.09 ms |
| Fresh transfer and raw-data validation | 446.74 ms |
| Verified cache reuse | 58.56 ms |

These are local stdio tool round trips using an already saved account session, not a full agent-turn benchmark or token/billing measurements. There are no new MCP tools or runtime dependencies. Password-based automatic token renewal remains unimplemented; NOMAD can require secure reauthentication after expiry/rejection.

Public protocol references: [deployed API](https://nmr-nomad.chem.ed.ac.uk/api/api-docs/), [NOMAD developer guide](https://www.nomad-nmr.uk/docs/getting-started/for-developers/), and the previously reviewed [upstream revision](https://github.com/nomad-nmr/nomad-server/tree/aba97242af9273c614cb52fd882afb609bf3223f). No upstream implementation was copied.
