# Windows connection command repair (0.8.3)

Version 0.8.2 introduced a remote-connection startup regression: the installed
interpreter's Windows path was encoded with `subprocess.list2cmdline`, but the
client parses the nested `--mcp-command` with its own quoted-word grammar. It
consumes backslashes inside and outside double quotes, so a valid path can become
an unresolvable executable name. This is a product adapter defect, not evidence
of invalid account credentials or a campus authentication failure.

The 0.8.3 change restores the previous launcher's forward-slash, always-quoted
interpreter path. The outer process invocation remains an argument array. There
is no change to credentials, environment key references, connection identities,
owner fencing, retry policy, campus sessions or school jobs.

The consumer grammar was checked against the official client source at
[revision 0f870e5, parseCommandArgv](https://github.com/openai/tunnel-client/blob/0f870e50a973fa820d4c409000059e181e8d242b/pkg/runtimeconfig/config.go#L2324).

## Verification

- Eight synthetic Windows path cases cover no spaces, spaces, Unicode, apostrophe,
  ampersand/parentheses, dollar/backtick, comma/semicolon/equal sign, and an already
  normalized path. Before the repair, seven failed and the normalized case passed.
- The actual official 0.0.14 client was exercised with its bounded loopback-only,
  in-memory `dev proxy`. All three cases passed: each verifies the old command
  fails and the repaired command starts exactly the intended interpreter/module.
  These checks establish parser and child-start behavior, not an MCP initialize
  exchange, hosted connection or campus read.
- The affected lifecycle, connection and installer tests passed (83); the full
  source suite passed (633, with five explicit skips). The isolated stdio smoke
  separately passed 38 tools, output schemas, structured/text parity, a synthetic
  local-task roundtrip and invalid-argument handling. The source publication audit
  passed. Installed bytes, both remote account connections and OS events require
  their own acceptance evidence.

Reproduce the portable suite and isolated stdio smoke using the development guide.
The optional official-client fixture is `tests/test_work_client.py`. Set
`UOE_TEST_TUNNEL_CLIENT` to a reviewed, already installed client executable before
running that file. It uses temporary profiles, a whitelisted environment and a
self-terminating synthetic MCP child; no personal key, alias or tunnel is used.
It does not install or download the client. These three cases skip by default.

## Installation and exceptional recovery

The normal 0.8.3 release uses the existing Windows installer and lifecycle
admission. Preserve valid account configurations and stop at unresolved ownership
instead of reinstalling repeatedly. A completed install does not prove a remote
connection is healthy.

A machine recovering an already completed 0.8.2 installation may instead receive
a separately reviewed, one-file controller overlay. Such a runtime must be
identified as **base 0.8.2 plus the recorded controller overlay**, with old/new file
hashes and its source/package provenance. It is neither an unmodified 0.8.2 runtime
nor a complete 0.8.3 installation. Original upgrade and start receipts must remain
intact; any new activation is recorded separately and an uncertain submission is
not repeated. The private maintenance helper is not a new public install route.

Reboot, logoff, sleep/network recovery, new-device setup, each host/account and
live campus/NOMAD access remain separate acceptance gates. This targeted repair
does not close them or reinterpret earlier source-only checks as host acceptance.
