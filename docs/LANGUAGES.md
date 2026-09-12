# Language and international student support

Use UoE Companion in the language you normally use with your agent. The default `locale=auto` asks the host to follow the current user's language. A saved preference is shared by clients using the same local data directory; a per-call override is temporary.

The local service catalog has ten language variants: English (`en-GB`), simplified Chinese (`zh-Hans`), traditional Chinese (`zh-Hant`), French (`fr-FR`), Spanish (`es-ES`), German (`de-DE`), Arabic (`ar`), Hindi (`hi`), Japanese (`ja`) and Korean (`ko`). Chinese region aliases choose the matching script. Other BCP 47 tags remain valid for host responses and explicitly report an English catalog fallback. Arabic and other common RTL language preferences report right-to-left presentation.

What is localized: names/categories for the 17 curated service entries and cross-language catalog search aliases. What is host-generated: explanations, summaries and optional translations of course titles. The catalog is a starting translation set, not a professionally reviewed translation of every university page. Corrections from native speakers are welcome.

Source documents, official course names/codes, filenames, quoted evidence, URLs and school records remain unchanged. The plugin makes no external translation/model API calls. Errors and workflow guidance may be returned in English for the agent to explain in the requested language. Live-page searches still need words matching the source page; cached course-content search is not semantic multilingual retrieval.

## Examples

| User request | Tool behavior |
| --- | --- |
| “以后用中文，保留英文课名” | `study_preferences(locale="zh-Hans", bilingual_titles=True)` |
| “Show today's schedule in Tokyo time” | `study_agenda(display_timezone="Asia/Tokyo")`, with unchanged source timestamps |
| “Trouve la bibliothèque” | `study_services(query="bibliotheque", locale="fr-FR")` |
| “ابحث عن المكتبة” | `study_services(query="المكتبة", locale="ar")` |
| “この授業の教材をダウンロードして” | Standard discovery/download workflow; respond in Japanese, preserve source names |
| “한국어로 이번 주 학습 일정을 보여 줘” | `study_agenda(locale="ko")`; the host explains cached evidence in Korean |

`study_preferences()` reads only. Supply only fields that the user wants to change. `locale="auto"` restores per-request language following. `bilingual_titles` guides host-added translations; original evidence is always retained. A temporary `locale` on `study_services`, `study_agenda` or `study_help` does not write preferences.

## Dates and timezones

School-date ranges use `Europe/London`, including British Summer Time transitions. Display timezone is an independent IANA timezone, not inferred from language or nationality. Exact instants keep their source value and gain a `display_*` field. A date-only deadline stays date-only; no midnight/time-of-day is invented or shifted into another date.

The agenda combines cached events/deadlines in the selected range, active local tasks and records with unknown dates. `unknown_dates`, pagination, observation times and cache coverage remain explicit. Submitted/graded statuses are retained as observed; a local completed task does not prove a university submission. A missing cached item never proves there is no work.
