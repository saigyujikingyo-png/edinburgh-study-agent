# NMR 0.8.1 connection verification

Checked on **17 September 2026**, Windows, Python 3.12.14. This update fixes everyday setup and request continuation; it does not add instrument control or spectrum processing. Private course passwords, account/sample identifiers, original data and connection links are excluded from this record.

## Reproduced failure and correction

A real, isolated, sandboxed Chrome form submission against 0.8.0 sent `Origin: null` under its `Referrer-Policy: no-referrer`. The local server returned **403**, before saving the credential. The same normal submission against 0.8.1 sent the exact local origin, returned **200**, and saved the encrypted connection. Neither reproduction contacted a school service. Foreign-origin/cross-site requests remain rejected; cookie, nonce, exact host/path and bounded-form checks are tested separately.

The old one-hour teaching credential is now an explicit **temporary** option. Remembered Windows teaching connections persist with current-user DPAPI until replaced, rejected or forgotten. Old temporary connections are not promoted silently. The saved permission is restricted to the selected old-archive group. NOMAD retains its separate expiring-token model.

## Evidence

| Area | Observed result |
| --- | --- |
| Focused NMR checks | 264 passed: vault limits, cross-process encrypted readback, time advance, group isolation, removal, real browser POSTs, English/Chinese narrow layout, renewal/rejection, input forms, cancellation, selection, raw archives and export contracts. |
| Full local regression | 556 passed, 2 explicit skips in 41.77 seconds. No school fixtures or private credentials are in tests. |
| Request convenience | A saved unique connection selects its provider/group. Only missing sample information is requested. New sample requests reuse the saved group permission. Resuming after input or dataset selection preserves the original download intent. |
| Credential forms | English and Chinese; light/dark CSS; no JavaScript, external asset or school-page navigation. Actual sandboxed Chrome submits in desktop and narrow viewports. Visual owner review and each host's credential-window presentation are separate. |
| MCP | Real stdio initialization/discovery/calls, all output schemas, text parity and malformed-request handling passed. Host-form capability and chat fallback are tested using synthetic host callbacks. |
| Live source network | The first attempt and both public homepages timed out; the credential was retained. After the user confirmed campus VPN connectivity, a real MCP query with only sample/date input automatically selected the saved source/group and found the original record in **0.8891 seconds**, reusing its hash-verified ZIP. A retained-request cache read took **0.0369 seconds**. No credential prompt or browser action occurred. This was a fresh archive search plus existing-file reuse, not a new remote ZIP transfer. |
| NOMAD | No test account is available. Live sign-in, token expiry and acquisition remain unverified. No password-based automatic renewal is claimed. |
| Host/attachment | Existing runtime/account configurations are reused. Individual ChatGPT/Work/Claude/WorkBuddy model runs, URL elicitation and NMR host attachments are separate acceptance gates. |

## Protocol measurements

Three warm status calls per profile, using empty synthetic stores:

| Profile | Tools | Catalog UTF-8 bytes | Initialization | Warm status median |
| --- | ---: | ---: | ---: | ---: |
| Full | 38 | 210,495 | 934.82 ms | 25.64 ms |
| Student | 35 | 197,241 | 890.41 ms | 26.12 ms |
| Daily | 15 | 91,139 | 911.38 ms | 25.41 ms |

These are local protocol timings and serialized bytes, not model tokens, costs or a Terra-max benchmark. No extra model, runtime dependency or permanent service was added. Exact-commit CI, distributable hashes and installation results are recorded with the release. The separate [0.8.0 acquisition record](NMR_ACCEPTANCE.md) remains historical evidence, not a fresh 0.8.1 ZIP transfer.

See [NMR usage and limitations](NMR.md) for the connection states, HTTP scope and remote/mobile reachability boundary.
