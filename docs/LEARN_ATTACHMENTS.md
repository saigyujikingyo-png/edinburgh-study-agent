# Learn inline attachments (0.8.7)

The outline adapter previously indexed file/document/assessment links, while the
page reader captured only text. Learn document attachment cards were therefore
missing from the resource index. A container download correctly refused to treat
the document identity as a file, but could not discover the requested originals.

## Behavior

- Read a document with `study_read_resource` or list its `item_id` with
  `study_materials`. Visible attachment metadata becomes independently indexed
  resources with the parent document, stable asset identity, original filename,
  media type and expected byte count.
- Download a document with `study_materials(operation="download", item_id=...)`
  or `study_download_files`. Its observed originals expand into a bounded batch
  of at most 30 files. Use `query` with the parent `item_id` to select particular
  filenames/labels, or use returned child identifiers directly.
- Keyword searches reuse indexed children. If the bounded outline search finds
  no match, `study_materials` reads up to three relevant document pages internally.
  It reports unvisited page coverage and suggested page identifiers. Absence from
  that read is not proof of absence from Learn. Outline-only metadata updates
  still do not claim exhaustive attachment freshness.
- Each transfer reobserves the child's metadata on its original page, then makes
  a body-free authenticated HEAD request to the observed Learn attachment URL.
  Only the transient, allowlisted download redirect reaches the existing HTTP
  streaming downloader. Cookies/passwords stay in the private browser profile.
  Transfer addresses are never stored in item or download records.
- No preview rendering, screenshots, GUI download controls, new dependency or
  additional public tool is required. Existing campus login and original files
  are preserved. Verified cache reuse does not claim a remote freshness check.

Hidden copies, malformed metadata, conflicting identities, wrong parent pages,
unsafe redirects, mismatching names/sizes and invalid file content fail closed.
Each successful receipt records independent file identity, filename, actual byte
count, SHA-256, source page and stable parent/asset binding. Public metadata never
contains signed download addresses.

## Verification on 23 September 2026

Synthetic browser/HTTP fixtures exercise discovery, hidden ancestors, duplicate
and conflicting cards, unsupported metadata, source/redirect identity, changed
metadata, original-byte integrity, child-only batch receipts, cache reuse,
keyword filtering, bounded traversal and compact/full structured contracts.
The nullable attachment model is also checked through portable MCP discovery.

A source candidate reused the authorized campus session and observed ten visible
attachments on one live document. Both requested Word/PDF originals were saved;
DOM sizes matched and independent SHA-256 readback passed. One measured run took
about 11 seconds including browser startup/page reading, 2.4 seconds for the two
transfers, and 0.025 seconds for a repeated verified cache lookup. These are local
adapter timings, not a host/model response-time, token or billing benchmark.
Private course identifiers, files, exact URLs and receipts are not published.

The current adapter supports the observed Learn document attachment-card format
and the existing dedicated file-preview format. Other widgets, external/LTI
content, converted alternative formats and unvisited pages remain outside this
claim. Campus source acceptance, exact packaged/installed execution, individual
ChatGPT/WorkBuddy/other-host turns and final file delivery are separate gates.
