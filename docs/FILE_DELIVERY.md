# Original-file delivery

`study_export_files` prepares selected, already downloaded Learn originals for
host attachments and subsequent cloud-storage workflows. It returns the file
bytes through MCP together with their size, SHA-256 and source evidence.
The agent no longer needs to reconstruct a document from extracted text or ask
another computer to open a campus-machine path.

## Everyday use

Ask in your preferred language, for example:

- "Export the handbook and past-paper spreadsheet that are already downloaded."
- "Make a ZIP of these six cached originals and include a manifest."
- "List the sizes and checksums of these downloaded files without attaching them."
- "Export these cached originals, then upload them to the Drive folder I selected.
  Verify the uploaded files before marking the migration complete."

The agent selects observed resource IDs from the existing course/download
results. If a selected original is missing or no longer matches its recorded
checksum, export stops. A separate, authorised download is needed to repair the
cache; export does not refresh the campus session or fetch the file again.

Uploading to Drive or another destination remains a separate operation performed
by that destination's connector. Existing migration folders, categorisation,
source documents and manifest records are not changed by this export tool.

## Export choices

| Mode | Result | Use |
| --- | --- | --- |
| `files` | One MCP binary resource per original, plus a compact receipt | Attach or transfer individual PDF, Office and other supported downloaded files. |
| `manifest` | Verified metadata only; no binary resources | Inspect the selection, size, provenance and hashes before transfer. |
| `bundle` | One ZIP containing original bytes and `manifest.json` | Transfer a bounded collection while retaining an item-to-file inventory. |

The default is `files`. ZIP entries use numbered directories, so two originals
with the same filename remain separate. The manifest records each entry's
original filename, resource ID, source page, download time, size and SHA-256.
Repeated bundle exports from the same cached selection produce the same ZIP
bytes; they do not create another saved ZIP in the campus cache.

## Limits and integrity

- Select **1 to 30 unique resource IDs** from Learn. Duplicate IDs and other
  record types are rejected.
- The default combined-original limit is **16 MiB**. `max_megabytes` accepts an
  integer from **1 to 32**, measured in MiB (1,048,576 bytes).
- The byte limit applies to the complete selection. A bundle must also fit the
  limit after ZIP and manifest overhead; compression does not bypass the source
  limit.
- Every original must be a nonempty regular file inside the expected download
  cache. Redirected cache paths, unsafe filenames, and inconsistent size or
  SHA-256 records are rejected.
- All selected files are checked before a result is returned. An incomplete
  selection does not produce a partial result labelled successful.
- The source page is a validated Learn content URL. Signed download addresses,
  campus credentials and local filesystem paths are not exported as provenance.

Binary resources use base64 inside the MCP transport, which adds approximately
one third to their wire size. Host-specific message, attachment or upload limits
can be lower than the server's limit. Reduce the selection when a host reports
its own size limit; never copy base64 into the conversation to work around it.

## Delivery states

The server's receipt describes the cache and transfer payload, not a completed
cloud upload:

| Evidence | Meaning |
| --- | --- |
| `verified_local` with `host_registration: not_requested` | Manifest mode checked the cached originals and returned metadata only. |
| `awaiting_host_receipt` with `host_registration: required` | Verified binary resources were returned; the receiving host still needs to materialise usable files. |
| Actual host attachment/file reference | The host has accepted the file. Check the received bytes or available integrity evidence. |
| Destination file ID and successful readback | The requested destination received the file; compare size and SHA-256 before marking migration verified. |

An `export_id` identifies a deterministic export selection. It is not a host file
ID, a Drive file ID, or a guarantee that a destination deduplicates retries.
A `uoe://` resource URI identifies the bytes carried by MCP; do not pass it to a
connector as though it were an HTTP download URL or a registered attachment.

If a destination upload times out, inspect that destination and the last receipt
before retrying. Preserve confirmed destination IDs. Keep the migration pending
when the final outcome or integrity cannot be established.

## Host integration

Prefer the host's native handling of MCP embedded binary resources. The final
implementation does not register the same bytes again through an additional widget.
A passive compatibility resource remains readable for older development catalogs;
it contains no script, upload API or automatic network request. Tool output schemas and the exact
JSON text fallback describe compact metadata; the binary stays in MCP resource
blocks.

Hosts handle file references differently:

- A Chat host may materialise the returned resources as conversation attachments.
  Use only references that the host actually returns, and follow the receiving
  connector's declared file-input format.
- A local agent can save the returned bytes through its authorised file API,
  verify size and SHA-256, and use its supported upload adapter. The saved path
  must exist in that agent's execution environment.
- A cloud agent cannot read a different computer's filesystem path. It needs the
  transferred bytes or an actual host-provided file reference.

A valid MCP resource, a declared output schema and a visible attachment card are
separate evidence. None alone proves that another connector can consume the
original bytes. Missing host materialisation is reported as a delivery gap;
UoE Companion does not invent file IDs or expose public download links for
private course documents.

## Verification and acceptance

The synthetic test suite covers original PDF and XLSX bytes, metadata-only
manifests, repeatable ZIPs, filename collisions, cache corruption and escape,
unsafe provenance, selection limits and aggregate byte limits. Public
`PortableFastMCP` calls additionally check discovery, schema validation, exact
metadata/text parity, preservation of binary resources, and safe rejection of
malformed results across full, student and daily tool profiles.

On 15 September 2026, the native export candidate produced new ChatGPT Chat
file references for a 153,413-byte PDF and a 12,533-byte XLSX. The host reported
both runtime files readable; its document browser did not support the XLSX.
The refreshed tool catalog has no widget output template. A trial uploader was
removed because the host already materialised binary resources. This proves
Chat file receipt, not destination upload or every other host.

| Surface | Current evidence boundary |
| --- | --- |
| Portable MCP core | Synthetic public-tool and integrity tests; no campus account required. |
| ChatGPT Chat | Native PDF/XLSX file references and original sizes observed; destination acceptance is separate. This Chat session did not expose Google Drive tools. |
| ChatGPT local Work / cloud Work | Verify the final file route separately; earlier status or course-query acceptance does not establish file delivery. |
| Codex / Claude / WorkBuddy / other suitable agents | Shared MCP binary contract; each host's materialisation and destination transfer require their own acceptance. |
| Google Drive or another cloud destination | Upload and destination readback remain separate gates. Consult the final release verification record. |

No private account identifiers, resource IDs, signed URLs, original course files
or local acceptance paths belong in public tests or documentation. See
[output contracts](OUTPUT_CONTRACTS.md) and the repository's [verification
record](../VERIFICATION.md) for the applicable release evidence.
