"""Compact model-facing responses; full dated evidence stays in the local store."""
from copy import deepcopy

ITEM_FIELDS = {
    "id", "item_id", "native_id", "kind", "title", "url", "course_id",
    "source", "source_url", "course_title", "service_id", "status", "observed_at", "observation_id", "needs_refresh",
    "due_at", "due_date", "starts_at", "ends_at", "excerpt", "timing",
    "display_due_at", "display_starts_at", "display_ends_at",
}


def compact(value):
    if isinstance(value,list):
        return [compact(v) for v in value]
    if not isinstance(value,dict):
        return value
    is_item = "kind" in value and "excerpt" in value and ("id" in value or "native_id" in value)
    result={}
    for key,entry in value.items():
        if entry is None or (is_item and key not in ITEM_FIELDS):
            continue
        if key in {"worker_pid","timings_ms","topics","launch_label","profile_location","data_directory"}:
            continue
        if key=="excerpt" and is_item:
            if entry==value.get("title"):
                continue
            result[key]=entry[:160]
            if len(entry)>160:
                result["excerpt_truncated"]=True
            continue
        if key in {"text","excerpt"} and isinstance(entry,str) and len(entry)>6000:
            result[key]=entry[:6000]
            result[key+"_truncated"]=True
            result[key+"_length"]=len(entry)
            continue
        if key=="links" and isinstance(entry,list) and len(entry)>10:
            result[key]=compact(entry[:10])
            result["links_total"]=len(entry)
            result["links_truncated"]=True
            result["expand_links"]="study_school_job(detail='full') or study_search"
            continue
        result[key]=compact(entry)
    # Preserve a true truncation flag if an earlier field generated it.
    for key in ("text","excerpt"):
        if isinstance(value.get(key),str) and len(value[key])>(160 if is_item and key=="excerpt" else 6000):
            result[key+"_truncated"]=True
    return result


def page_job(value,offset=0,limit=20):
    if not 0<=offset<=1000000 or not 1<=limit<=100:
        raise ValueError("offset 0..1000000; limit 1..100.")
    result=deepcopy(value)
    body=result.get("result",{})
    if body.get("operation")=="updates":
        rows=body["items"]
        body["items"]=rows[offset:offset+limit]
        body.update(offset=offset,returned_count=len(body["items"]),total_items=len(rows),
                    next_offset=offset+limit if offset+limit<len(rows) else None,
                    has_more=offset+limit<len(rows),continuation_tool="study_school_job")
        return result
    if result.get("action") in {"timetable","materials","messages"} and "total_items" in body:
        body["continuation_tool"]={"timetable":"study_timetable","materials":"study_materials","messages":"study_messages"}[result["action"]]
        return result
    rows=body.get("items")
    if isinstance(rows,list):
        body["items"]=rows[offset:offset+limit]
        body.update(offset=offset,returned_count=len(body["items"]),total_items=len(rows),
                    next_offset=offset+limit if offset+limit<len(rows) else None,
                    response_truncated=offset+limit<len(rows))
    return result
