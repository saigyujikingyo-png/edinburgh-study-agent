"""Personal Timetabler HTML export and checksum-bound course PDF timetables."""
from datetime import date, datetime, time
from collections import Counter
from pathlib import Path
import hashlib
import re
from . import workflow_cache
from .html_content import table_rows
from .models import LONDON, now_utc, Item, Observation
from .downloads import verified_copy
from .results import validate_year

ENTRY="https://timetabler.is.ed.ac.uk/Timetable"
TTL=300
MONTHS={m.lower():n for n,m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"],1)}

def source_date(value):
    match=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})",value)
    if match and match[2].lower() in MONTHS:
        return date(int(match[3]),MONTHS[match[2].lower()],int(match[1]))
    for fmt in ("%Y-%m-%d","%d/%m/%Y"):
        try:return datetime.strptime(value.strip(),fmt).date()
        except ValueError:pass
    raise ValueError("Unrecognised exported date; no date was guessed.")

def parse_export(html):
    rows=table_rows(html)
    header=next((r for r in rows if {"Title","Date","Start Time","End Time"}.issubset(r)),None)
    if not header:
        raise ValueError("Timetabler HTML table headers were not recognised.")
    events=[];unparsed=0
    for values in rows:
        if values==header or not values:
            continue
        if len(values)!=len(header):
            unparsed+=1;continue
        raw=dict(zip(header,values))
        try:
            day=source_date(raw["Date"])
            start=datetime.combine(day,time.fromisoformat(raw["Start Time"]),LONDON)
            end=datetime.combine(day,time.fromisoformat(raw["End Time"]),LONDON)
            if end<=start:raise ValueError("Invalid end time")
        except ValueError:
            unparsed+=1;continue
        label=raw.get("Weeks","")
        y=re.search(r"\((\d{4})/(\d{1,4})\)",label)
        year=(y[1]+"/"+str(int(y[1])+1)[-2:]) if y else None
        sem=re.search(r"\bS([12])\b",label)
        week=re.search(r"\bWk\s*(\d+)",label,re.I)
        key=hashlib.sha256("\0".join(values).encode()).hexdigest()[:24]
        events.append(dict(id=key,title=raw["Title"],type=raw.get("Type",""),
            starts_at=start.isoformat(),ends_at=end.isoformat(),location=raw.get("Location",""),
            academic_year=year,semester=int(sem[1]) if sem else None,
            week=int(week[1]) if week else None,week_label=label,
            modules=raw.get("Academic courses",raw.get("Modules","")),groups=raw.get("Groups",""),
            source_text=" | ".join(values)))
    # All-occurrence exports may repeat rows when activities are grouped.
    events=list({e["id"]:e for e in events}.values())
    events.sort(key=lambda e:(e["starts_at"],e["title"],e["id"]))
    return dict(items=events,unparsed_rows=unparsed,
        coverage="partial" if unparsed else "exported_personal_timetable",
        source_url=ENTRY,observed_at=now_utc().isoformat(),timezone="Europe/London",
        timezone_basis="Timetabler campus wall times interpreted in Europe/London, including DST.",
        scope="Personal activity export; unpublished allocations and separate exam systems are not proven complete.")

def current_year():
    today=now_utc().astimezone(LONDON).date()
    year=today.year if today.month>=8 else today.year-1
    return f"{year}/{str(year+1)[-2:]}"

def validate(args):
    validate_year(args.get("academic_year","current"))
    if args.get("semester") not in (None,1,2):raise ValueError("semester must be 1 or 2.")
    if args.get("week") is not None and not 1<=args["week"]<=60:raise ValueError("week must be 1..60.")
    if args.get("view","summary") not in ("summary","occurrences"):raise ValueError("Unknown timetable view.")
    if not 0<=args.get("offset",0)<=10000 or not 1<=args.get("limit",20)<=100:
        raise ValueError("offset 0..10000; limit 1..100.")
    for field in ("start","end"):
        if args.get(field):date.fromisoformat(args[field])
    if args.get("start") and args.get("end") and args["start"]>args["end"]:
        raise ValueError("end must not precede start.")

def paged(rows,args,budget=26000):
    offset=args.get("offset",0);limit=args.get("limit",20)
    selected=[];size=0
    import json
    for row in rows[offset:offset+limit]:
        amount=len(json.dumps(row,ensure_ascii=False))
        if selected and size+amount>budget:break
        selected.append(row);size+=amount
    end=offset+len(selected)
    return dict(items=selected,total_items=len(rows),offset=offset,
                next_offset=end if end<len(rows) else None,has_more=end<len(rows))

def overview(items):
    weeks={}
    for item in items:
        key=(item["academic_year"],item["semester"],item["week"])
        row=weeks.setdefault(key,dict(academic_year=key[0],semester=key[1],week=key[2],dates=set(),types=Counter()))
        row["dates"].add(item["starts_at"][:10])
        row["types"][item["type"] or "unspecified"]+=1
    rows=[dict(academic_year=r["academic_year"],semester=r["semester"],week=r["week"],
        first_class_date=min(r["dates"]),last_class_date=max(r["dates"]),
        active_dates=len(r["dates"]),occurrences=sum(r["types"].values()),types=dict(r["types"]))
        for r in weeks.values()]
    rows.sort(key=lambda r:r["first_class_date"])
    return dict(first_class_date=min((i["starts_at"][:10] for i in items),default=None),
        last_class_date=max((i["starts_at"][:10] for i in items),default=None),
        occurrence_count=len(items),types=dict(Counter(i["type"] or "unspecified" for i in items)),
        weeks=rows[:30],weeks_truncated=len(rows)>30,
        note="Counts and date spans describe exported occurrences, not continuous daily attendance or all University deadlines.")

def select(data,args,cache_hit=False):
    year=args.get("academic_year","current")
    resolved=current_year() if year=="current" else year
    items=[e for e in data["items"] if (resolved=="all" or e["academic_year"]==resolved)
        and (args.get("semester") is None or e["semester"]==args["semester"])
        and (args.get("week") is None or e["week"]==args["week"])
        and (not args.get("start") or e["starts_at"][:10]>=args["start"])
        and (not args.get("end") or e["starts_at"][:10]<=args["end"])]
    rows=items
    if args.get("view","summary")=="summary":
        groups={}
        for e in items:
            stamp=datetime.fromisoformat(e["starts_at"])
            fields=(e["title"],e["type"],stamp.strftime("%a"),e["starts_at"][11:16],
                    e["ends_at"][11:16],e["location"],e["modules"],e["groups"])
            g=groups.setdefault(fields,dict(title=fields[0],type=fields[1],weekday=fields[2],
                 start_time=fields[3],end_time=fields[4],location=fields[5],modules=fields[6],groups=fields[7],dates=[]))
            g["dates"].append(stamp.date().isoformat())
        rows=list(groups.values())
    result={k:v for k,v in data.items() if k!="items"}
    result.update(paged(rows,args))
    result.update(academic_year=resolved,academic_year_basis="Requested year; current uses the UK academic-year August boundary.",
        semester=args.get("semester"),view=args.get("view","summary"),occurrence_count=len(items),
        overview=overview(items),
        available_years=sorted({e["academic_year"] for e in data["items"] if e["academic_year"]}),
        cache_hit=cache_hit,remote_freshness_checked=not cache_hit,source_content_is_untrusted=True,
        response_guidance="For a semester overview, use the supplied weekly counts and date spans directly; paginate detailed patterns only when needed. Give a brief timetable table and dated scope. Do not build a website, inspect host files or write parsing scripts unless asked.")
    if not items:
        result.update(coverage="partial",warning="No matching occurrences in this export. This does not prove no classes or no published course timetable.",
            next_step="Search course timetable documents with study_materials, then use study_timetable(item_id=...) for the PDF week grid.")
    return result

def cached(store,args):
    if args.get("item_id"):
        return document(store,args)
    data=workflow_cache.get(store,"timetable","personal",TTL)
    return select(data,args,True) if data else None

def document(store,args):
    item_id=args["item_id"]
    saved=verified_copy(store,item_id)
    if not saved:return None
    path=Path(saved["path"])
    if path.suffix.lower()!=".pdf":raise ValueError("Course week-table reading currently supports PDF.")
    from .document_layout import extract
    key="v2:"+saved["sha256"]
    data=workflow_cache.get(store,"pdf_layout",key,86400*365)
    hit=data is not None
    if data is None:
        data=extract(path)
    if not hit or "pages" in data or "tables" in data:
        # The weekly reader needs only labelled cells. Raw pages and duplicate
        # table geometry remain derivable from the verified original PDF.
        data={key:data[key] for key in ("weeks","problems","scope","date_mapping")}
        workflow_cache.put(store,"pdf_layout",key,data)
    rows=[w for w in data["weeks"] if (args.get("semester") is None or w["semester"]==args["semester"])
          and (args.get("week") is None or w["week"]==args["week"])]
    summary=args.get("view","summary")=="summary"
    if summary:
        rows=[{**w,"days":{day:text if len(text)<=128 else text[:128]+"…" for day,text in w["days"].items()},
               "truncated_days":[day for day,text in w["days"].items() if len(text)>128]} for w in rows]
    return dict(**paged(rows,args),item_id=item_id,filename=saved["filename"],sha256=saved["sha256"],
        source_url=saved["source_page_url"],scope=data["scope"],date_mapping=data["date_mapping"],
        coverage="course_document_week_grid" if rows else "partial",problems=data["problems"],
        extraction_cache_hit=hit,verified=True,remote_freshness_checked=False,
        source_content_is_untrusted=True,
        view="week_previews" if summary else "week_cells",
        detail_tool={"tool":"study_timetable","arguments":{"item_id":item_id,"semester":args.get("semester"),"view":"occurrences"},
                     "optional_filter":"Set week to read one labelled week; next_offset pages the remaining rows."},
        response_guidance="For an overview use these week/day previews. truncated_days identifies incomplete cells: request view=occurrences and a week for full class details. No host files, Python setup or parser is needed. Do not infer calendar dates or personal groups from this course grid.")

def export_form():
    day=now_utc().astimezone(LONDON).date().isoformat()
    form={"layout":"List","format":"HTML","startTime":day+" 00:00:00",
        "endTime":day+" 23:59:00","permittedPublishStatuses[]":"Live",
        "isGroupEvents":"false","includeBookings":"false","includeExams":"false",
        "includeHolidays":"false","isFitOneDay":"false","includeSetupTakedown":"false",
        "includeUnscheduledEvents":"false","isCombineResources":"true","isCombinedWeeks":"false",
        "colourBy":"Standard","excludeResourcesWithNoEvents":"false",
        "titleProperty":"Description","excludeHeaders":"false"}
    included={"Ids","Description","Modules","Groups","Rooms","Buildings","Weeks"}
    for key in ("Ids","Description","Notes","Courses","Modules","Staff","Groups","Rooms","Capacity",
                "Buildings","Departments","OnlineMeetingLink","StudentCount","Weeks","AltIds"):
        form["cellPreferences[include"+key+"]"]="true" if key in included else "false"
    return form

def read(store,page,args,progress):
    from . import school,portal
    if args.get("item_id"):
        if args.get("refresh") or not verified_copy(store,args["item_id"]):
            school.download_items(store,page,dict(item_ids=[args["item_id"]],refresh=args.get("refresh",False)),progress)
        value=document(store,args)
        if value is None:raise ValueError("The timetable document could not be downloaded.")
        return value
    progress("Exporting your personal timetable as structured HTML.")
    page.goto(ENTRY,wait_until="domcontentloaded")
    portal.follow_sso(page,store)
    if portal.login_gate(page):raise school.LoginRequired()
    page.locator(".calendar-action-btn.options-btn").wait_for(timeout=20000)
    # Observed export API used by the site's "Download my timetable" form.
    # The browser-owned request context supplies its own cookies; none are read,
    # copied to the agent, or persisted outside the campus profile.
    response=page.request.post("https://timetabler.is.ed.ac.uk/api/download/timetable/user",
        form=export_form(),headers={"X-Requested-With":"XMLHttpRequest"},timeout=20000)
    if response.status in (401,403):raise school.LoginRequired()
    if response.status!=200:raise ValueError("Timetabler export request failed.")
    if len(response.body())>8_000_000:raise ValueError("Timetable export exceeds the reading limit.")
    payload=response.json()
    html=payload.get("timetableHTML") if isinstance(payload,dict) else None
    if not isinstance(html,str):raise ValueError("Timetabler returned no supported HTML export.")
    data=parse_export(html)
    # Store dated event evidence in bounded chunks, usable by agenda/planning.
    for offset in range(0,len(data["items"]),200):
        batch=data["items"][offset:offset+200]
        items=[Item(native_id="timetabler:"+e["id"],kind="event",title=e["title"],url=ENTRY,
            service_id="timetable",excerpt=e["source_text"][:3000],
            starts_at=e["starts_at"],ends_at=e["ends_at"],status="available") for e in batch]
        store.capture(Observation(source="timetable",source_url=ENTRY,title="Personal Timetabler HTML export",
            observed_at=datetime.fromisoformat(data["observed_at"]),scope="All dates; individual occurrences; 00:00-23:59; no saved preference changes",
            coverage="partial",authentication="authenticated",
            text="\n".join(e["source_text"] for e in batch),items=items))
    if not data["unparsed_rows"]:
        store.capture(Observation(source="timetable",source_url=ENTRY,title="Personal Timetabler snapshot",
            observed_at=datetime.fromisoformat(data["observed_at"]),scope="Personal Timetabler activity export snapshot",
            coverage="partial",authentication="authenticated",
            text="Parsed personal export with "+str(len(data["items"]))+" occurrences. Unpublished and separate exam records are outside this scope."))
    workflow_cache.put(store,"timetable","personal",data)
    return select(data,args)
