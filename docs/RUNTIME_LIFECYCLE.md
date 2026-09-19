# UoE Companion runtime lifecycle

Contract 1.0; shared rules **2026-09-19.1**, pinned to Chembridge
[`922d950`](https://github.com/saigyujikingyo-png/chembridge/blob/922d95041b3b857f6ba11fbfb2817b18712ef605/RUNTIME_LIFECYCLE.md).
Owner: UoE Product Max. Observation date: 19 September 2026.
This is a **source candidate** on `codex/work-runtime-lifecycle`, based on
`a31f052aa8b1484d72b5d66a8456880ff184dbb1` (release 0.8.1). It is not installed
or published. Governance review precedes either action.

Adopting the shared rules does not establish runtime conformance or close
[CB-2026-001](https://github.com/saigyujikingyo-png/chembridge/blob/922d95041b3b857f6ba11fbfb2817b18712ef605/governance/incidents/CB-2026-001.md).

## Components and owners

| Component | Class / owner | Lifetime and cardinality |
| --- | --- | --- |
| Agent stdio frontend | on_demand_local_companion / selected host | Starts on host request. EOF ends that frontend. Independent frontends are allowed; their presence alone is not a leak. |
| Private remote connector | persistent_remote_connector / current user's explicit Run or enabled logon task | One supervisor and one tunnel daemon per alias and canonical profile directory. One logical MCP child chain; an optional declared CPython venv redirector is a packaging shim. |
| School background job | frontend-independent local job / existing school job coordinator | Job records outlive the frontend. Neither connector retry nor this change replays jobs. OS failure survival and old nonterminal records remain separate gaps. |
| Campus browser / NMR credentials | existing school/NMR subsystem | No change to login, DPAPI data, permissions or browser ownership in this candidate. |

The PowerShell files are now thin, identical launch shims. `work_runtime.py`
contains supervision policy; `work_profiles.py` owns generation and migration.
This reuses the bundled interpreter, with no new dependency or system service.
It adds one lightweight Python policy process per remote connection alongside
the scheduled PowerShell shim. Its resident resource cost still needs installed
measurement; smaller tool catalogs or passing tests are not quota evidence.

`connection.json` retains the original tunnel identity, interpreter and client.
The private `lifecycle.json` declares only the alias, task, encrypted-secret
reference, release version and launcher hashes. Primary and named accounts have
separate declarations, directories, locks and tasks. The same generator supports
the previously shipped school-account layout; no private identifiers are in source.

Scope comparison uses canonical paths and rejects symlinks/junctions. A file lock
is shared across launchers, logon sessions and installer transactions. Process
ownership uses exact executable, argument vector, directory, PID, creation time
and observed parent identity. Termination retains a native process handle and
checks its birth time again. Unknown ownership is preserved, not force-cleaned.

## State and recovery

The canonical atomic `lifecycle-status.json` records observation time, state,
scope, owner identities, retry count and error code. Compatibility status/error
files reflect the same observation; successful observations resolve old errors.
Ready observations expire after 50 seconds. A saved ready value is not proof of
current health, campus authentication or host installation.

- External CLI and Windows queries normally have a 10-second hard timeout.
  Startup readiness has one 30-second total deadline. Cleanup has a 45-second
  query/command budget; native handle termination can additionally wait up to
  two seconds. A timed-out CLI is reaped before reconciliation.
- An existing owner is polled; warming does not launch another connector.
  Ongoing health is rechecked every 30 seconds, with a 20-second probe deadline.
  PID existence alone cannot refresh readiness.
- A never-created alias returns a nonzero CLI status. First startup requires a
  successful structured local alias-directory response proving it absent before
  connecting; an arbitrary CLI error is not accepted as absence.
- Registry stop failure does not skip exact-identity cleanup. Producers are
  quiesced before descendants, with new lineage observations at each boundary.
  A child first seen after its parent vanished has unproven ownership: cleanup
  fails and reconnection is blocked. A fresh supervisor with no ownership receipt
  also checks every same-runtime server before connect: missing, inaccessible or
  recycled parent identities block startup. Other-host frontends are excluded only
  through an observed live, older parent chain; their absence from this profile's
  receipt is not proof that they are unrelated.
- More than one daemon, two server branches, changed process identities or
  unknown orphans prevent readiness/retry. A linear redirector/server chain is
  accepted only for the base executable declared in the local venv configuration.
- Recoverable connection failures have at most three retries, after 5, 15 and
  30 seconds. Each possible spawn is reconciled before retry. Five minutes of
  observed healthy operation resets this budget. No school or scientific write
  is resubmitted by this policy.

## Events and installation

| Event | Candidate behavior | Acceptance boundary |
| --- | --- | --- |
| Chat ends / host disconnects | Persistent connector continues; stdio frontend follows its host | Existing architecture; new installed candidate unverified |
| Delayed readiness / child failure / crash | Fresh probes, bounded recovery, no competing same-scope owner | Synthetic policy and Windows adapter tests |
| Boot / logon / reboot | Explicitly enabled current-user, limited-privilege logon task; no machine-wide boot service | Real OS-event tests pending |
| Network unavailable / restored | Bounded recovery; task may restart a failed runner up to three times one minute apart | Long outages can exhaust both budgets; explicit start or next logon is then required. Real network test pending |
| Sleep / resume | Fresh health probe after execution resumes | Real resume test pending |
| Logoff / shutdown | No continuous-execution promise; next authorised logon may start connector | Abrupt exit can retain a stale receipt. Do not interpret it as a current pass |
| Explicit Stop | Disable only the matching startup task; terminate the exact wrapper/supervisor by individual native handles, then reconcile its scope. Never call Task Scheduler tree-stop | Unknown owner or unreleased lock returns failure. Real installed Stop pending |
| Startup disabled | Upgrade does not enable or start it | Generator/installer fixture evidence; OS preference readback pending |
| Upgrade / reinstall | Share scope locks; refuse active runtime or enabled legacy launcher; migrate all declared profiles transactionally | Synthetic two-account upgrade, repeat and rollback evidence |
| Removal | Existing explicit Stop must precede removal; campus data is retained | Integrated uninstall wizard is not implemented |

Task actions must match the expected executable, full arguments and working
directory and current-user principal. Installation does not change task registrations or enabled preferences.
Older launchers must first be paused through their existing Stop entrypoint;
they do not understand the new cross-launcher lock. Do not manually restart an
old launcher during an upgrade.

Before updating, the installer saves readback-verified `lifecycle-backup-*`
files and their hash manifest alongside `runtime-backup-*`; both locations are
recorded in `installation.json`. A failure restores both layers. Manual support
rollback also verifies every launcher hash and preserves later user edits.
Connection/app identity files and encrypted secrets are never backup-migrated or
rewritten by the launcher generator. Custom scripts require review.

## Verification and remaining gates

The first pre-fix regression reproduced the old Stop failure: registry stop returned
nonzero and neither proven-owned process was cleaned. The five previous script
tests passed; the added regression failed. Those policy cases have moved to the
shared-core tests; Windows launcher/task-adapter tests exercise the thin boundary.
Governance subsequently reproduced an additional first-start orphan bug in the
initial source candidate. New tests failed before its repair, then verified no
new connect across a fresh supervisor with an empty or missing lineage receipt.
The initial passing suite did not establish that untested recovery branch.

The candidate tests cover startup before/after spawn, delayed readiness, malformed
status, hard deadlines, registry failure, cleanup-time child birth, PID reuse,
orphan preservation including a brand-new supervisor after a pre-receipt crash,
duplicate owners/children, account isolation, independently proved live
frontends, locking, exact Windows process termination, synthetic DPAPI roundtrip,
multi-account generation, custom/concurrent edits, repeat install and rollback.
A real disposable Windows PowerShell/Python tree verified that individual-handle
wrapper/supervisor termination preserved a detached synthetic job and its heartbeat.
This was not a registered Task Scheduler job: installed scheduler descendant
lifetime and job breakaway remain a separate OS acceptance gate. No real school
job was used or stopped in this test.
See the review receipt for the exact commit and current test totals.

Separate current-device evidence for the **unchanged installed 0.8.1**: its two
existing private connectors were restored without changing identities. Governance
reported successful fresh status-only ChatGPT Work calls in both accounts.
`live_connection_checked=false`; this is not a campus login pass. One separately
authorised Learn read returned a login landing page and partial/unknown
authentication. No additional campus read or login was performed in this repair.

Still open: candidate package/hash parity, installed startup/stop and upgrade,
each remote account after candidate installation, real logon/reboot/network/sleep
events, new-device acceptance, live campus authentication, and the historical
startup termination cause. The three old nonterminal school jobs and the local
binding-metadata discrepancy are separate read-only backlogs; they were not
deleted, replayed or used to overwrite a cloud identity.

Terra/max was selected in the governance host checks; backend model identity and
actual tokens/charges were not independently attested. No new end-user efficiency
or universal host-support claim follows from these source tests.
