# Download binding and receipt compatibility

Version 0.8.5 is a bounded correction to the existing download path. It adds no
dependency, daemon, campus permission or automatic re-download.

## Attachment selection

A direct Learn file must retain the requested course/content route after
navigation. The resolver checks the entire iframe visibility chain, rejects
multiple visible previews even when names match, and requires a stable unique
preview. Recognisable filename labels, preview filenames and supplied HTTP
attachment filenames must agree. A descriptive label is not used as a filename;
the preview or response header supplies it.

New Learn receipts retain a small attachment_binding object with the observed
content path/id, selection method and available filename checks. Signed transfer
URLs are transient and are not retained. This is an observed binding, not proof
that the university never attaches the same bytes to different labels.

A document or assessment page is a container, not a directly downloadable
file. Its embedded links can be read through the existing page-reading workflow.
The download path does not silently choose an embedded attachment.

## Specific outcomes

| Code | Meaning / next step |
| --- | --- |
| UNSUPPORTED_CONTAINER | Read the page and choose an observed file. |
| ATTACHMENT_AMBIGUOUS | Multiple previews; inspect the returned bounded filename candidates. |
| ATTACHMENT_MISMATCH | Route or filename disagreement; inspect/refresh the resource. |
| PREVIEW_NOT_READY | No unique supported preview became ready within the bounded wait. |
| UNSUPPORTED_FILE | No supported original filename. |
| DOWNLOAD_HTTP_ERROR / DOWNLOAD_NETWORK_ERROR | Transfer failed; inspect connectivity/status before another attempt. |
| FILE_VERIFICATION_FAILED / FILE_SAVE_FAILED | Check the source bytes or local storage respectively. |

Failures have automatic_retry=false and a recovery action. Batch downloads
retain completed files and per-file failures. File-reading worker failures retain
the same classification. There is no retry to make output validation pass.

## Existing Learn and NMR records

Older NMR receipts lack the course title required by the common download-list
contract. The list now uses the already stored filename as a display title with
title_source=filename, without rewriting the database or changing any bytes.
New NMR receipts store that same explicit display-title source. Other missing or
invalid required fields remain validation errors; schema-required field names
are reported without echoing private result values.

Historical downloads are preserved and are not retroactively given new
attachment-binding evidence. Equal SHA-256 values establish equal bytes, not
correct label/source association. A true duplicate-source investigation and
any re-download require their own scoped evidence and authorisation.

## Acceptance boundaries

Focused offline checks cover hidden and same-name previews, route/filename
mismatches, page-only entries, header disagreement, transfer versus verification
failures, new NMR receipts and old mixed-catalog direct/dispatcher calls. All
browser requests in these tests are fulfilled by synthetic fixtures.

Live campus attachment layouts, both installed account connections, model-host
calls and destination receipt are separate checks. Passing synthetic cases does
not settle the origin of a previously reported duplicate or relabel old cached
files as newly source-verified.
