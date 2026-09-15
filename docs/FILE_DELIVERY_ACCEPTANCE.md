# 0.7.2 original-file delivery acceptance

Date: 15 September 2026. Status: **student prerelease**.

## Problem and resulting behaviour

A course original downloaded on the campus computer previously reached a remote
agent only as a Windows path. The new export tool returns the verified original
bytes as MCP resources with a bounded manifest. Chat can receive native attachments;
cloud Work can save the received bytes in its own workspace and use its declared
file-upload adapter. Source verification, host receipt and destination readback are
separate evidence.

## Actual host results

| Check | Result |
| --- | --- |
| Existing account A, Chat | Fresh native PDF/XLSX references observed; final `study_status` returned 0.7.2 successfully. No replacement plugin identity. |
| Existing account B, official hosted calls | 37 tools with 37 output schemas; status and cached export manifest succeeded at about 2 seconds each. |
| Legacy project Chat | Tool discovery succeeded but execution returned `FORBIDDEN: This conversation does not support developer MCPs`. Recorded as a host/conversation limit, not a campus-login failure. |
| New cloud Work, GPT-5.6 Terra, highest effort | Original-file export, receiving-workspace materialisation, two Drive uploads and raw-byte readback completed. |
| Independent Drive readback | PDF 153,413 bytes and XLSX 12,533 bytes; both SHA-256 values matched the cached originals. The target contained exactly two private acceptance copies with the requested names. |
| Local Work, Claude, WorkBuddy, DeepSeek and other hosts | Shared MCP contract available; this release does not claim new end-to-end file-transfer acceptance for these hosts. |

The receiving host preserved the original bytes. No PDF, spreadsheet or course
content was reconstructed. The acceptance created only the explicitly approved
folder/copies; it did not alter existing migration manifests, original files,
classification or sharing permissions. It does not complete the wider migration.

## Efficiency and first-attempt failures

The cloud Work model displayed GPT-5.6 Terra with highest effort. The first upload
attempt failed: the agent passed `BlobResourceContents` to a field declaring a
path string. Read-only diagnosis then established the adapter boundary. During
the corrected attempt, an oversized shell argument failed before file creation
and a lost in-memory export result required another cached export. The successful
route used streamed input and a verified receiving-workspace path.

The corrected turn displayed **5 minutes 52 seconds**, including those failures.
The Work agent reported **25.5 seconds** for its final successful transfer/check
sequence; this narrower figure is not the whole-turn latency. The earlier failed
turn displayed **2 minutes 11 seconds**. First-attempt end-to-end success is **no**.
Several developer corrections were required, and fresh-user automatic routing
with the final guidance remains unverified. No quota-saving percentage is claimed.

A separate five-call in-process probe exported the same 165,946 original bytes
with a **14.28 ms median**. It measured cached source validation and binary assembly
only, excluding the model, private tunnel, host materialisation and destination.
A full catalog measured 200,417 UTF-8 bytes, versus 81,390 for the 14-tool daily
profile. Catalog bytes are not model tokens or charges. Actual token counts,
reasoning tokens and billing were unavailable for this acceptance.

## Regression, installation and preservation

- Full local suite: **292 passed, 2 skipped** (Windows symlink permissions).
- Final delivery/contract-focused checks: **105 passed, 2 skipped** after updating
  the materialisation guidance. Binary and schema behavior remained valid.
- Real stdio discovery/call smoke: 37 tools, structured results, output schemas,
  exact JSON text parity and invalid-request rejection passed.
- Windows connection tests exercise readiness delay, failed-connect cleanup,
  exact profile ownership and PID-reuse protection. Other plugin processes are
  excluded from cleanup.
- Windows and Linux CI cover Python 3.11/3.12, plus Windows 3.13 and bundled
  installer execution. The workflow derives filenames from current version
  metadata, rather than retaining a previous release's wheel name.
- Fresh and repeat installation were exercised in an isolated path containing
  spaces/non-ASCII characters, with unrelated WorkBuddy/Claude settings preserved.
  The existing private installation was upgraded transactionally with rollback.
- Six existing account configuration/encrypted-key files retained their SHA-256
  values. Campus login/cache and both original plugin identities were retained.
- A portable MIME table prevents Windows registry differences from labelling
  Office originals as generic binary files. Wheel inventory is checked against
  the reviewed source before building the Windows archive.

CI completion and published archive checksums belong to the release associated
with this record. Private file IDs, hashes, account details, source originals and
full execution receipts are intentionally excluded from public source.

## Remaining limits

The campus computer must be online for its private connection. Native attachment
handling and local-path upload adapters vary by host. Some existing Chat
conversations reject developer MCPs despite showing their tools. The release
therefore remains a prerelease: it is not a universal host or additional-student
certification, and it does not implement direct Drive/OneDrive OAuth storage.

Reference: [OpenAI plugin file APIs](https://developers.openai.com/plugins/reference#file-apis)
describe host file APIs. The cloud path adapter above was additionally established
by its actual declared tool input and successful upload/readback, not inferred
from a visible MCP tool or attachment card.
