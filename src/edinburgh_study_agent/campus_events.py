"""Fast public school calendar reading with explicit source coverage."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import re
from urllib.parse import urljoin, urlsplit
import httpx
from .html_content import Tree
from .models import now_utc, safe_url
from .timetable import paged, source_date, current_year
from .results import validate_year
from . import workflow_cache

SEMESTERS="https://semester-dates.ed.ac.uk/"
PHYSICS="https://www.ph.ed.ac.uk/events/calendar"
SOURCES={"academic_dates":SEMESTERS,"physics_events":PHYSICS}

def fetch(url):
    with httpx.Client(timeout=12,follow_redirects=False) as client:
        for _ in range(5):
            safe_url(url);host=urlsplit(url).hostname or ""
            if host!="ed.ac.uk" and not host.endswith(".ed.ac.uk"):
                raise ValueError("Public calendar redirect left official school hosts.")
            with client.stream("GET",url) as response:
                if response.is_redirect:
                    url=urljoin(url,response.headers["Location"]);continue
                response.raise_for_status()
                parts=[];size=0
                for block in response.iter_bytes():
                    size+=len(block)
                    if size>2_000_000:raise ValueError("Public calendar exceeds the reading limit.")
                    parts.append(block)
                return b"".join(parts).decode("utf-8",errors="replace")
        raise ValueError("Calendar redirect limit reached.")

def academic_url(home,year):
    suffix=year.replace("/","")
    for a in Tree(home).root.find("a"):
        url=urljoin(SEMESTERS,a.attrs.get("href",""))
        if urlsplit(url).hostname=="semester-dates.ed.ac.uk" and urlsplit(url).path.rstrip("/")=="/"+suffix:
            return url
    raise ValueError("Requested academic year was not linked by the official calendar.")


def date_range(label):
    """Only complete source ranges become dates; missing year remains unknown."""
    text=label.strip()
    match=re.fullmatch(r"(\d{1,2})(?:\s+([A-Za-z]+))?(?:\s+(\d{4}))?\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",text)
    if match:
        month=match[2] or match[5];year=match[3] or match[6]
        start=source_date(match[1]+" "+month+" "+year)
        end=source_date(match[4]+" "+match[5]+" "+match[6])
        if end<start:raise ValueError("Reversed source date range.")
        return start.isoformat(),end.isoformat()
    if re.fullmatch(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}",text):
        day=source_date(text).isoformat()
        return day,day
    return None,None

def academic_rows(html,url,year):
    root=Tree(html).root
    output=[]
    tables=list(root.find("table"))
    for index,table in enumerate(tables[:2],1):
        for tr in table.find("tr"):
            cells=[n.text() for n in tr.children if getattr(n,"tag",None)=="td"]
            if len(cells)!=2:continue
            label,title=cells
            start=end=None
            try:start,end=date_range(label)
            except ValueError:pass
            output.append(dict(title=title,date_text=label,start_date=start,end_date=end,
                semester=index,academic_year=year,source="academic_dates",url=url))
    if not output:raise ValueError("No recognised academic calendar table rows.")
    return output

def event_rows(html,url):
    result=[]
    root=Tree(html).root
    nodes=list(root.find(itemtype="http://schema.org/Event"))+list(root.find(itemtype="https://schema.org/Event"))
    for e in nodes[:300]:
        link=next(e.find("a",itemprop="url"),None)
        start=next(e.find(itemprop="startDate"),None)
        location=next(e.find(itemprop="location"),None)
        if link is None or start is None:continue
        stamp=start.attrs.get("datetime",start.attrs.get("content",""))
        try:
            dt=datetime.fromisoformat(stamp)
            if dt.tzinfo is None:continue
            target=urljoin(url,link.attrs.get("href",""))
            safe_url(target)
            if urlsplit(target).hostname!=urlsplit(url).hostname:continue
        except ValueError:continue
        result.append(dict(title=link.text(),starts_at=stamp,start_date=stamp[:10],
            end_date=stamp[:10],location=location.text() if location else None,
            source="physics_events",url=target))
    if not result:raise ValueError("No recognised event records; a directory/empty page does not prove no events.")
    return result

def validate(args):
    if args.get("source","all") not in (*SOURCES,"all"):raise ValueError("Choose all, academic_dates or physics_events.")
    year=args.get("academic_year","current")
    validate_year(year)
    if year=="all":raise ValueError("Choose current or one academic year.")
    for key in ("start","end"):
        if args.get(key):date.fromisoformat(args[key])
    if args.get("start") and args.get("end") and args["start"]>args["end"]:raise ValueError("Invalid date range.")
    if not 1<=args.get("limit",20)<=50 or not 0<=args.get("offset",0)<=10000:raise ValueError("Invalid page.")
    if len(args.get("query",""))>300:raise ValueError("Query too long.")

def read(store,args):
    validate(args)
    year=current_year() if args.get("academic_year","current")=="current" else args["academic_year"]
    names=list(SOURCES) if args.get("source","all")=="all" else [args["source"]]
    def one(name):
        key=name+":"+year
        saved=None if args.get("refresh") else workflow_cache.get(store,"campus_events",key,300)
        if saved:return {**saved,"cache_hit":True}
        try:
            if name=="academic_dates":
                url=academic_url(fetch(SEMESTERS),year)
                rows=academic_rows(fetch(url),url,year)
            else:
                url=PHYSICS;rows=event_rows(fetch(url),url)
            data=dict(source=name,items=rows,url=url,observed_at=now_utc().isoformat(),cache_hit=False)
            workflow_cache.put(store,"campus_events",key,data)
            return data
        except Exception as error:
            return dict(source=name,items=[],error=type(error).__name__,coverage="unavailable",
                        warning="This source could not be read; do not infer no events.")
    with ThreadPoolExecutor(max_workers=2) as pool:parts=list(pool.map(one,names))
    query=args.get("query","").casefold()
    all_rows=[r for part in parts for r in part["items"]]
    rows=[r for r in all_rows if (not query or query in r["title"].casefold())
        and (not args.get("start") or (r.get("end_date") and r["end_date"]>=args["start"]))
        and (not args.get("end") or (r.get("start_date") and r["start_date"]<=args["end"]))]
    rows.sort(key=lambda r:(r.get("start_date") or "9999",r.get("starts_at",""),r["title"]))
    return dict(**paged(rows,args,16000),coverage="partial",
        sources=[{k:v for k,v in p.items() if k!="items"}|{"record_count":len(p["items"])} for p in parts],
        undated_records=sum(not r.get("start_date") for r in all_rows),
        scope="Official standard academic calendar and School of Physics & Astronomy public events only. Programme exceptions apply; university-wide student Events App, EUSA bookings and private calendars are not covered.",
        source_content_is_untrusted=True,
        response_guidance="Return a brief dated list/table with the selected source scope; do not call this all University events or create charts unless asked.")
