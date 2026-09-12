# Verified website routes

Observed on the user's Chrome session, 2026-09-11. Reinspect relevant structured DOM on use; labels and selectors may change. Do not take screenshots or use coordinate clicks.

## MyEd

Start at https://www.myed.ed.ac.uk/ . "Login to MyEd" may complete through an existing EASE session. An authenticated home has Studies and a sign-out control. Read only relevant study content; avoid unrelated email previews.

Studies includes:
- My courses: https://www.myed.ed.ac.uk/myed-progressive/euclid-my-courses
- Timetables: https://www.myed.ed.ac.uk/myed-progressive/timetables
- Resource lists: https://resourcelists.ed.ac.uk/
- Past exam papers: https://library.ed.ac.uk/exam-papers
- Library: https://www.myed.ed.ac.uk/myed-progressive/library
- Media Hopper Create: https://media.ed.ac.uk/

## Timetabler

The current service is https://timetabler.is.ed.ac.uk/ and the authenticated timetable page is /Timetable. MyEd links to it. It has separate Microsoft sign-in; reuse the existing authenticated session.

The user's personal teaching timetable for 21–27 September 2026 was read after login. That is a dated observation of one week, not evidence of ongoing authentication or a complete calendar/exam import. The page can first show a timetable-selection list. Do not misread that list as scheduled events or inspect other people's timetables. Use DOM-backed semantic controls if a selection is needed; do not use a visual fallback.

## Learn Ultra

https://www.learn.ed.ac.uk/ resolves to /ultra/course after login.
Base navigation: Activity, Courses, Essentials, Calendar, Messages, Marks, Tools.

Courses has Terms, Filters, Search your courses and pagination. The observed list had 26 results across two pages. Scope refresh to the requested term. Loading placeholders may lack titles and ids; do not capture them. An enrolled-but-unopened course is unavailable, not absent.

A course card may have a javascript link with a stable element id such as course-link-_123_1. The server opens the validated Learn outline route using an observed native course id, then verifies the actual page before saving evidence. No private API is called.

In an open course: Content, Calendar, Announcements, Gradebook, Messages, Groups. Modules are collapsible; inspect relevant folders through semantic selectors. Observed Assessment resources included an information document, previous assessment examples and a past-paper spreadsheet. An LTI recording control without a usable href is not a download URL.

A document may open in a content view with Exit, Contents and Next. Read its rendered DOM text before interpreting dates. A 100% written-exam breakdown does not specify an exam date. Learn marks may be provisional; the observed guidance directed confirmed results to EUCLID.

Calendar > Due Dates is the cross-course deadline route. Establish the displayed range and preserve exact no-results wording. Teaching and centrally scheduled exams are not guaranteed to appear there.

## Downloads

Use `study_download_files`; it obtains original-file addresses internally through the plugin-owned browser. See [structured-access.md](structured-access.md). Never click Download or open Save As for this workflow. A preview alone does not prove a local download. Return the verified local file and retain course context for unsupported LTI recordings, reading lists and external library services.

## EUCLID and school-wide services

Use study_services and study_read_service. MyEd Accounts > My student record launches EUCLID; transient SITS links stay inside the browser. Programme, Courses, Assessment and Documents are observed read-only sections. Student records are not modified. MyCareerHub reuses campus SSO and provides observed job/event links. Service coverage is recorded individually.
