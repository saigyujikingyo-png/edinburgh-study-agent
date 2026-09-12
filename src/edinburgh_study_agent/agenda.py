"""Bounded student timeline; SQL filters the date window before materialising rows."""
from __future__ import annotations
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from .models import LONDON, now_utc
from .localization import presentation

# Static SQL only. Dates, kinds, switches, limits and offsets are bound values.
RECORDS = """
WITH records AS (
 SELECT id,kind,payload,source,observed_at,observation_id,0 AS local_only,
 json_extract(payload,'$.status') AS status,
 json_extract(payload,'$.due_at') AS due_at,json_extract(payload,'$.due_date') AS due_date,
 json_extract(payload,'$.starts_at') AS starts_at,json_extract(payload,'$.ends_at') AS ends_at
 FROM items WHERE kind IN ('event','assignment') AND (? IS NULL OR kind=?)
 UNION ALL
 SELECT t.id,'task',t.payload,'local',json_extract(t.payload,'$.updated_at'),NULL,1,
 json_extract(t.payload,'$.status'),
 CASE WHEN json_extract(t.payload,'$.deadline_mode')='linked' AND i.id IS NOT NULL
 THEN json_extract(i.payload,'$.due_at') ELSE json_extract(t.payload,'$.due_at') END,
 CASE WHEN json_extract(t.payload,'$.deadline_mode')='linked' AND i.id IS NOT NULL
 THEN json_extract(i.payload,'$.due_date') ELSE json_extract(t.payload,'$.due_date') END,NULL,NULL
 FROM tasks t LEFT JOIN items i ON i.id=json_extract(t.payload,'$.item_id') WHERE ?=1
), selected AS (
 SELECT *, COALESCE(starts_at,due_at,due_date) AS sort_at FROM records
 WHERE status!='cancelled' AND (local_only=0 OR status IN ('todo','doing')) AND (
 (kind='event' AND julianday(starts_at)<julianday(?) AND
   (julianday(starts_at)>=julianday(?) OR julianday(ends_at)>julianday(?))) OR
 (kind!='event' AND julianday(due_at)>=julianday(?) AND julianday(due_at)<julianday(?)) OR
 (kind!='event' AND due_at IS NULL AND due_date>=? AND due_date<=?) OR
 (?=1 AND ((kind='event' AND starts_at IS NULL) OR (kind!='event' AND due_at IS NULL AND due_date IS NULL)))
 ))
"""
COUNT_SQL = RECORDS + "SELECT COUNT(*) AS total,SUM(sort_at IS NULL) AS unknown FROM selected"
PAGE_SQL = RECORDS + "SELECT * FROM selected ORDER BY sort_at IS NULL,julianday(sort_at),kind,id LIMIT ? OFFSET ?"

def window(store, start, end, *, kind=None, include_tasks=False, include_unknown=False, limit=500, offset=0):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first.isoformat()!=start or last.isoformat()!=end or not 0 <= (last-first).days <= 366:
        raise ValueError("Use YYYY-MM-DD dates in an ordered range of at most 367 days.")
    if kind not in (None, "event", "assignment") or not 1<=limit<=500 or not 0<=offset<=1000000:
        raise ValueError("kind must be event/assignment; limit 1..500; offset 0..1000000.")
    lower = datetime.combine(first,time(),LONDON).isoformat()
    upper = datetime.combine(last+timedelta(days=1),time(),LONDON).isoformat()
    params=(kind,kind,int(include_tasks),upper,lower,lower,lower,upper,start,end,int(include_unknown))
    with store.connection() as db:
        # One read transaction keeps counts and pages consistent during concurrent capture.
        db.execute("BEGIN")
        counts=db.execute(COUNT_SQL,params).fetchone()
        rows=db.execute(PAGE_SQL,(*params,limit,offset)).fetchall()
    items=[]
    for row in rows:
        if row["local_only"]:
            item=json.loads(row["payload"])
            item.update(kind="task",source="local",due_at=row["due_at"],due_date=row["due_date"])
        else:
            item=store._row(row)
        items.append(item)
    total=counts["total"]
    return {"items":items,"total_matches":total,"unknown_dates":counts["unknown"] or 0,
            "offset":offset,"next_offset":offset+len(rows) if offset+len(rows)<total else None,
            "truncated":offset+len(rows)<total,"live":False,"coverage":"cached_observations_only"}

def agenda(store, start=None, end=None, limit=20, offset=0, locale=None, display_timezone=None):
    first=date.fromisoformat(start) if start else now_utc().astimezone(LONDON).date()
    last=date.fromisoformat(end) if end else first+timedelta(days=6)
    view=presentation(store,locale,display_timezone)
    value=window(store,first.isoformat(),last.isoformat(),include_tasks=True,include_unknown=True,limit=limit,offset=offset)
    zone=ZoneInfo(view["display_timezone"])
    for item in value["items"]:
        item["timing"]="date_only" if item.get("due_date") else "exact" if item.get("starts_at") or item.get("due_at") else "unknown"
        for field in ("due_at","starts_at","ends_at"):
            if item.get(field):
                item["display_"+field]=datetime.fromisoformat(item[field]).astimezone(zone).isoformat()
    value.update(start=first.isoformat(),end=last.isoformat(),presentation=view,
        source_dates_unchanged=True,range_timezone="Europe/London",
        note="Cached events and deadlines in this London-date range, plus active local tasks and records with unknown dates. No matches does not prove an empty schedule. Local done does not mean submitted. Date-only deadlines have no inferred time.",
        refresh_tools=["study_live_resources","study_read_service","study_import_calendar"])
    return value
