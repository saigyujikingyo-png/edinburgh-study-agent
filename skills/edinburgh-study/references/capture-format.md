# Capture schema

Call `study_capture` with `observation`:
- source: learn | myed | timetable | library
- source_url: actual HTTPS page URL
- title: observed page title
- observed_at: real ISO timestamp with timezone offset
- scope: course/page/filter/date range actually inspected
- coverage: partial (default) | complete_visible_scope
- authentication: authenticated | login_required | unknown
- text: exact relevant visible text excerpts joined with newlines
- items: structured records justified by that text

Each item:
- native_id: stable site id; e.g. a course/content id from a visible URL or DOM. For a service use its canonical content URL.
- kind: course | resource | assignment | event | announcement | service
- title: exact visible title, present in text
- excerpt: exact visible supporting text, present in text
- url: actual HTTPS content URL, or null for javascript/LTI controls without a real target yet
- course_id and course_title: known parent course, otherwise null
- due_at: exact aware ISO datetime, or due_date: YYYY-MM-DD when time is unknown; never both
- starts_at, ends_at: aware timestamps for a real timetable event; ends_at must be later
- status: unknown | available | unavailable | submitted | graded | cancelled

Unknown is the default. An item's title and excerpt must occur in the supplied text. Date and status interpretation still requires honest semantic checking by the host. Do not fabricate evidence snippets to make validation pass.

A live browser reading has an observation time. An imported calendar has an import time and file hash; it is not a fresh browser reading. Repeated identical observations deduplicate. Older snapshots cannot overwrite more recent records. Absence from a partial or complete-visible page never deletes prior records; explicit cancellation can be captured.

Use the returned item ids to link local tasks and the observation id to fetch source evidence. All outputs from search/planning are labelled cached, never live.
