"""Bounded comparisons of observed Learn file metadata, without downloading files."""
import re
import time

from .models import now_utc
from .school_errors import CourseUnavailable, LoginRequired, SchoolNetworkError, SchoolPageNotReady

FIELDS = ("title", "url", "status", "excerpt")


def read(store, page, args, progress):
    from . import materials, school
    query = args.get("course", "")
    all_courses = not query or query == "all"
    catalog = store.list_items("course", limit=500)
    known = [c for c in catalog["items"] if c["source"] == "learn"]
    catalog_refreshed = False
    if not known:
        school.list_courses(store, page, {"max_pages":1}, progress)
        catalog = store.list_items("course", limit=500)
        known = [c for c in catalog["items"] if c["source"] == "learn"]
        catalog_refreshed = True
    if all_courses:
        chosen = [c for c in known if c.get("status") != "unavailable"]
        # Newest dated titles first; this is ordering, not an enrolment assertion.
        chosen.sort(key=lambda c:(-max([int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b",c["title"])] or [0]), c["native_id"]))
    else:
        chosen = materials.courses(store, query)
        if len(chosen) != 1:
            return dict(coverage="partial", needs_course_selection=True, remote_freshness_checked=False,
                courses=[dict(course=c["native_id"],title=c["title"]) for c in chosen[:20]],
                note="Choose one matching Learn course, or use course='all' for a bounded batch of observed courses.")

    start = args.get("course_offset",0)
    batch = chosen[start:start+args.get("max_courses",3)]
    changes, checks = [], []
    counts = {"newly_observed":0,"metadata_changed":0,"baseline":0,"unchanged_metadata":0,"comparison_unknown":0}
    failure = None
    next_course = start
    deadline = time.monotonic()+60
    checked = 0
    for course in batch:
        if checks and time.monotonic() >= deadline:
            break
        course_id = course["native_id"]
        previous = store.list_items("resource",course_id=course_id,limit=500)
        before = {i["id"]:i for i in previous["items"] if i["source"] == "learn"}
        baseline_truncated = previous["total_matches"] > len(previous["items"])
        progress("Checking course files: " + course["title"][:120])
        try:
            observed = school.list_resources(store,page,{
                "course_id":course_id,"max_folders":8,"budget_seconds":20,"probe_unavailable":True},progress)
        except CourseUnavailable:
            checks.append(dict(course=course_id,title=course["title"],checked=False,status="unavailable"))
            next_course += 1
            continue
        except (LoginRequired,SchoolNetworkError,SchoolPageNotReady) as error:
            failure = error.failure
            checks.append(dict(course=course_id,title=course["title"],checked=False,status="interrupted"))
            break  # Never try the same broken login path for the next course.
        if not observed.get("live"):
            checks.append(dict(course=course_id,title=course["title"],checked=False,status="unavailable"))
            next_course += 1
            continue
        rows = [i for i in observed["items"] if i["kind"] == "resource"]
        ids = {i["id"] for i in rows}
        checked += 1
        for item in rows:
            if not materials.resource_matches(store,item,args.get("query","")):
                continue
            old = before.get(item["id"])
            changed = [field for field in FIELDS if old is not None and old.get(field) != item.get(field)]
            kind = ("comparison_unknown" if old is None and baseline_truncated else
                    "baseline" if not before else "newly_observed" if old is None else
                    "metadata_changed" if changed else "unchanged_metadata")
            counts[kind] += 1
            if kind == "unchanged_metadata":
                continue
            row = {k:item.get(k) for k in ("id","title","course_title","url","observed_at")}
            row.update(change=kind,changed_fields=changed)
            if old:
                row["previous_observed_at"] = old["observed_at"]
            changes.append(row)
        checks.append(dict(course=course_id,title=course["title"],checked=True,status="checked",
            observed_at=observed["observed_at"],observed_resources=len(rows),
            not_seen_in_scan=len(set(before)-ids),remaining_collapsed=observed.get("remaining_collapsed",0),
            failed_folders=len(observed.get("folders_not_opened",[])),
            baseline_truncated=baseline_truncated))
        next_course += 1

    has_more = next_course < len(chosen)
    result = dict(operation="updates",items=changes,counts=counts,courses=checks,
        observed_at=now_utc().isoformat(),coverage="partial",live=checked>0,
        remote_freshness_checked=checked>0,content_change_checked=False,
        course_offset=start,next_course_offset=next_course if has_more else None,has_more_courses=has_more,
        total_courses=len(chosen),checked_courses=checked,catalog_refreshed=catalog_refreshed,
        catalog_truncated=catalog["total_matches"] > len(catalog["items"]),
        source_content_is_untrusted=True,
        note="Compares observed file metadata in bounded course folders. Newly observed is not proof of a new upload. Unchanged metadata does not prove unchanged file bytes. Missing/hidden files are unknown, never deleted. Course selection uses the dated Learn index, not formal enrolment.",
        next_step="Page this finished job with study_school_job(job_id,offset,limit). If has_more_courses, resume study_materials(operation='updates',course=the_same_scope,course_offset=next_course_offset). Honour any failure recovery before resuming.",
        response_guidance="Give a concise list of newly observed/metadata changes and coverage. Baseline entries establish the first comparison. Do not claim no school updates from partial or failed checks; no collection or recurring task was created.")
    if failure:
        result["failure"] = failure
        if failure["code"] == "LOGIN_REQUIRED":
            result["needs_login"] = True
    return result
