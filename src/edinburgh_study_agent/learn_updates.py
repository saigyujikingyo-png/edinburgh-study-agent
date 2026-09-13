"""Visible Learn activity and course-message counters without host browser work."""
from datetime import datetime
import hashlib
import re
from urllib.parse import urlsplit
from . import workflow_cache
from .models import Item, Observation, now_utc, safe_url
from .timetable import paged
STREAM="https://www.learn.ed.ac.uk/ultra/stream"
MESSAGES="https://www.learn.ed.ac.uk/ultra/messages"
TTL=120
STREAM_ROWS=r"""() => [...document.querySelectorAll('.activity-feed li.stream-item-container')]
 .filter(e=>e.innerText.trim()).slice(0,100).map(e=>{
 const title=e.querySelector('a.js-title-link');
 const course=[...e.querySelectorAll('a[href]')].find(a=>/\/ultra\/courses\/_\d+_\d+\/outline/.test(a.href));
 return {title:title?.innerText.trim() || e.innerText.split('\n').filter(Boolean).pop(),
 url:title?.href || location.href,course:course?.innerText.trim() || '',
 course_url:course?.href || null, published_text:e.querySelector('.js-split-datetime')?.innerText.trim() || '',
 text:e.innerText.trim().slice(0,3000)};
})"""
MESSAGE_ROWS=r"""() => [...document.querySelectorAll('main .title.ellipsis')].map(e=>{
 const node=e.cloneNode(true);node.querySelectorAll('.summary').forEach(s=>s.remove());
 const card=e.closest('.flex-column-10');
 return {title:node.textContent.trim(),course_code:card?.querySelector('.subtitle bdi')?.textContent.trim() || '',
 unread_text:e.querySelector('.summary')?.textContent.trim() || '',url:location.href};
}).slice(0,100)"""

def validate(args):
    if args.get("view","activity") not in ("activity","inboxes"):
        raise ValueError("view must be activity or inboxes.")
    if len(args.get("query",""))>300 or len(args.get("course",""))>300:raise ValueError("Query too long.")
    if not 1<=args.get("limit",20)<=50 or not 0<=args.get("offset",0)<=10000:raise ValueError("Invalid page.")

def select(data,args,hit=False):
    query=args.get("query","").casefold();course=args.get("course","").casefold()
    rows=[i for i in data["items"] if (not query or query in " ".join(str(v) for v in i.values()).casefold())
          and (not course or course in (i.get("course","")+" "+i.get("title","")+" "+i.get("course_code","")).casefold())]
    return {**{k:v for k,v in data.items() if k!="items"},**paged(rows,args,18000),
        "cache_hit":hit,"remote_freshness_checked":not hit,"source_content_is_untrusted":True,
        "response_guidance":"Answer with the requested updates/counters and dated coverage. Do not launch a host browser or infer an empty inbox from zero unread."}

def cached(store,args):
    data=workflow_cache.get(store,"learn_updates",args.get("view","activity"),TTL)
    return select(data,args,True) if data else None

def read(store,page,args,progress):
    from . import school
    view=args.get("view","activity");url=STREAM if view=="activity" else MESSAGES
    progress("Reading Learn "+view+".")
    school.goto_learn(page,url)
    selector=".activity-feed li.stream-item-container" if view=="activity" else "main .title.ellipsis"
    try:page.locator(selector).first.wait_for(timeout=15000)
    except Exception:
        return dict(coverage="unavailable",items=[],source_url=url,
            warning="No supported loaded rows were found. This is not evidence of no updates/messages.",
            next_step="Retry the UoE tool once later; do not open another browser or loop over service sections.")
    if view=="activity":
        # Visible cards attach before their displayed dates; read the settled DOM once.
        try:page.wait_for_function("()=>!!document.querySelector('.activity-feed li.stream-item-container .date')?.textContent.trim()",timeout=5000)
        except Exception:pass
    rows=page.evaluate(STREAM_ROWS if view=="activity" else MESSAGE_ROWS)
    items=[];result=[]
    for row in rows:
        if view=="activity":
            try:
                safe_url(row["url"])
                if urlsplit(row["url"]).hostname not in school.LEARN_HOSTS:
                    row["url"]=url
            except ValueError:row["url"]=url
            key=hashlib.sha256((row["url"]+"\0"+row["title"]+"\0"+row["published_text"]).encode()).hexdigest()[:24]
            row["id"]="activity:"+key
            native=re.search(r"/courses/(_\d+_\d+)/",row.get("course_url") or "")
            items.append(Item(native_id=row["id"],kind="announcement",title=row["title"][:500],url=row["url"],
                course_id=native[1] if native else None,course_title=row["course"][:500] or None,
                excerpt=row["text"],status="available"))
        else:
            count=re.search(r"\b(\d+)\b",row["unread_text"])
            row["unread_count"]=int(count[1]) if count else None
        result.append(row)
    stamp=now_utc()
    text="\n".join(i["text"] if view=="activity" else " | ".join(str(v) for v in i.values()) for i in result)
    if text:
        store.capture(Observation(source="learn",source_url=url,title="Learn "+view,observed_at=stamp,
            scope="Loaded Learn activity rows" if view=="activity" else "Loaded course message overview counters",
            coverage="partial",authentication="authenticated",text=text[:100000],items=items))
    data=dict(items=result,source_url=url,observed_at=stamp.isoformat(),coverage="partial",
        scope="Loaded Learn activity stream only; may include new materials, announcements and other updates. Published date text retains the page display; timezone is not inferred."
          if view=="activity" else "Loaded course inbox overview only; unread counts are not message history. Reading Learn conversation bodies is not yet implemented. University email is handled through Outlook, outside this plugin scope.",
        view=view)
    workflow_cache.put(store,"learn_updates",view,data)
    school.mark_session(store,True)
    return select(data,args)
