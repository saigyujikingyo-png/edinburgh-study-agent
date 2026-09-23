"""One-call material discovery, download and document reading."""
from datetime import datetime
import re
from .learn_attachments import document
from . import workflow_cache
from .downloads import verified_copy
from .file_text import read_file
from .timetable import paged
from .models import now_utc

TTL=300
ALIASES={"课表":("timetable","schedule"),"时间表":("timetable","schedule"),
         "课程手册":("handbook",),"课件":("lecture","slides"),"历年试卷":("past paper",)}
def terms(query):
    return ALIASES.get(query.strip(),(query.casefold(),))
def matches(title,query):
    return not query or any(q.casefold() in title.casefold() for q in terms(query))
def validate(args):
    if args.get("operation","list") not in ("list","read","download","updates"):
        raise ValueError("operation must be list, read, download or updates.")
    if len(args.get("course",""))>300 or len(args.get("query",""))>300:
        raise ValueError("Course/query limited to 300 characters.")
    if not 1<=args.get("limit",20)<=30 or not 0<=args.get("offset",0)<=10000:
        raise ValueError("limit 1..30; offset 0..10000.")
    if not 0<=args.get("text_offset",0)<=2000000:raise ValueError("Invalid text offset.")
    if not 0<=args.get("course_offset",0)<=500 or not 1<=args.get("max_courses",3)<=3:
        raise ValueError("course_offset 0..500; max_courses 1..3.")
    if args.get("operation")=="updates" and args.get("item_id"):
        raise ValueError("For updates choose a course or all, not a file item_id.")

def courses(store,query):
    rows=[i for i in store.list_items("course",limit=500)["items"] if i["source"]=="learn"]
    if not query:return []
    exact=[i for i in rows if query in (i["id"],i["native_id"]) or i["title"].casefold()==query.casefold()]
    return exact or [i for i in rows if query.casefold() in i["title"].casefold()]


def scope_choice(store,args):
    """Resolve missing live scope before acquiring a browser or bypassing cache."""
    if args.get("operation")=="updates" and args.get("course") not in (None,"","all"):
        selected=courses(store,args["course"])
        if len(selected)!=1:
            return dict(coverage="partial",needs_course_selection=True,remote_freshness_checked=False,
                courses=[dict(course=i["native_id"],title=i["title"]) for i in selected[:20]],
                note="Choose a matching Learn course or use course='all'. If the course is not indexed, refresh study_live_courses once. No browser was started.")
    if args.get("item_id") or args.get("course") or not args.get("refresh") or args.get("operation","list") != "list":
        return None
    rows=[i for i in store.list_items("course",limit=500)["items"] if i["source"]=="learn"]
    return dict(coverage="partial",needs_course_selection=True,
        courses=[dict(course=i["native_id"],title=i["title"]) for i in rows[:20]],
        remote_freshness_checked=False,
        note="A list refresh needs a course name/id. To check new or changed files across observed courses use study_materials(operation='updates'). No browser was started and no cached files were relabelled as fresh.")

def resource_matches(store,item,query):
    if matches(item["title"]+" "+item.get("excerpt",""),query):
        return True
    if query.strip().casefold() in {"timetable","schedule","课表","时间表","日程"}:
        saved=verified_copy(store,item["id"])
        if saved:
            layout=workflow_cache.get(store,"pdf_layout","v2:"+saved["sha256"],86400*365)
            return bool(layout and layout.get("weeks"))
    return False

def candidates(store,args):
    if args.get("item_id"):
        item=store.item(args["item_id"])
        if item["source"]!="learn" or item["kind"]!="resource":
            raise ValueError("Choose an observed Learn resource.")
        return [item],None
    selected=courses(store,args.get("course",""))
    if args.get("course") and len(selected)!=1:
        return [],dict(coverage="partial",needs_course_selection=True,
            courses=[dict(course=i["native_id"],title=i["title"]) for i in selected[:20]],
            note="Choose an exact course from these matches; no year or course was guessed.")
    cid=selected[0]["native_id"] if selected else None
    rows=store.list_items("resource",course_id=cid,limit=500)["items"]
    return [i for i in rows if i["source"]=="learn" and resource_matches(store,i,args.get("query",""))],None

def listing(rows,args,live=False):
    result=paged([{k:i.get(k) for k in ("id","title","course_title","url","observed_at","attachment")} for i in rows],args,14000)
    result.update(live=live,coverage="partial",remote_freshness_checked=live,
        note="Bounded observed course resources. Unseen or restricted files are not proven absent.",
        next_step="Read or download a returned id with study_materials(item_id=..., operation='read' or 'download'). Document pages discover embedded originals; download expands up to 30 files. Timetable PDFs use study_timetable(item_id=...).",
        response_guidance="Return the requested files/content directly. Do not inspect host download folders or install document libraries.")
    return result

def cached(store,args):
    if args.get("operation")=="updates":return None
    rows,choice=candidates(store,args)
    if choice:return choice if choice["courses"] else None
    if not rows:return None
    operation=args.get("operation","list")
    if operation=="list":
        if args.get("item_id") and document(rows[0]):return None
        fresh=all(0<=(now_utc()-datetime.fromisoformat(i["observed_at"])).total_seconds()<TTL for i in rows)
        # A global cache search is explicitly scoped; live traversal needs a course.
        if fresh or not args.get("course"):
            return listing(rows,args)
        return None
    if operation=="read" and len(rows)!=1:
        return listing(rows,args)|{"needs_resource_selection":True}
    if operation=="read":
        saved=verified_copy(store,rows[0]["id"])
        if saved:
            return dict(content=read_file(store,rows[0]["id"],args.get("text_offset",0),10000),
                remote_freshness_checked=False,cache_hit=True)
    if operation=="download":
        if len(rows)>args.get("limit",20) and not args.get("item_id"):
            return listing(rows,args)|{"needs_resource_selection":True}
        saved=[verified_copy(store,i["id"]) for i in rows]
        if all(saved):return dict(saved=saved,failed=[],cache_hit=True,remote_freshness_checked=False)
    return None

def read(store,page,args,progress):
    from . import school
    if args.get("operation")=="updates":
        from .material_updates import read as read_updates
        return read_updates(store,page,args,progress)
    choice=scope_choice(store,args)
    if choice is not None:return choice
    rows,choice=candidates(store,args)
    selected=courses(store,args.get("course",""))
    if choice and not selected:
        school.list_courses(store,page,{"query":args.get("course",""),"max_pages":10},progress)
        rows,choice=candidates(store,args);selected=courses(store,args.get("course",""))
    if choice:return choice
    if not args.get("item_id") and selected and (args.get("refresh") or not rows or (args.get("operation","list")=="list" and not any(i.get("attachment") for i in rows))):
        value=school.list_resources(store,page,dict(course_id=selected[0]["native_id"],query="",
            max_folders=8,budget_seconds=20,probe_unavailable=True,search_terms=list(terms(args.get("query",""))),
            stop_after_matches=bool(args.get("query"))),progress)
        # Use this traversal's observed set; do not relabel stale retained items as fresh.
        rows=[i for i in value["items"] if i["kind"]=="resource" and resource_matches(store,i,args.get("query",""))]
        live=bool(value.get("live"))
        if not rows and not args.get("refresh"):
            indexed,_=candidates(store,args)
            rows=[i for i in indexed if i.get("attachment")]
            if rows:live=False
    else:
        live=False
    # Index page attachments inside the plugin, so hosts do not write parsers or
    # repeatedly scan the outline. Reuse known children unless refresh was asked.
    operation=args.get("operation","list")
    if args.get("item_id") and rows and document(rows[0]) and (operation=="list" or args.get("query")):
        value=school.read_resource(store,page,{"item_id":rows[0]["id"]},progress)
        rows=[i for i in value.get("attachments",[]) if resource_matches(store,i,args.get("query",""))]
        live=True
        if operation=="list" or not rows:return listing(rows,args,True)
    discovery=None
    if not rows and selected and args.get("query"):
        documents=[i for i in store.list_items("resource",course_id=selected[0]["native_id"],limit=500)["items"]
                   if i["source"]=="learn" and document(i)]
        words=[w for term in terms(args["query"]) for w in re.findall(r"\w+",term.casefold()) if len(w)>2]
        def priority(item):
            text=(item["title"]+" "+item.get("excerpt","")).casefold()
            return (-sum(w in text for w in words), "general information" not in text, item["id"])
        documents.sort(key=priority)
        scanned=0
        for parent in documents[:3]:
            progress("Reading page attachments: "+parent["title"][:100])
            value=school.read_resource(store,page,{"item_id":parent["id"]},progress)
            scanned+=1
            rows.extend(i for i in value.get("attachments",[]) if resource_matches(store,i,args["query"]))
            if rows:break
        live=bool(scanned) or live
        discovery={"pages_read":scanned,"remaining_pages":max(0,len(documents)-scanned)}
        suggestions=documents[scanned:scanned+5]
    if not rows:
        suggestions=suggestions if discovery else (store.list_items("resource",course_id=selected[0]["native_id"],limit=5)["items"] if selected else [])
        return listing([],args,live)|({"document_discovery":discovery} if discovery else {})|{"suggested_observed_files":[dict(id=i["id"],title=i["title"]) for i in suggestions],
            "next_step":"No match in this bounded read; unvisited pages may contain attachments. Read/list a suggested page id to discover its files; do not search host directories."}
    operation=args.get("operation","list")
    if operation=="list":return listing(rows,args,live)|({"document_discovery":discovery} if discovery else {})
    if operation=="read":
        if len(rows)!=1:return listing(rows,args,live)|{"needs_resource_selection":True}
        item=rows[0]
        if verified_copy(store,item["id"]) and not args.get("refresh"):
            return dict(content=read_file(store,item["id"],args.get("text_offset",0),10000),remote_freshness_checked=False)
        value=school.read_resource(store,page,dict(item_id=item["id"],refresh=args.get("refresh",False)),progress)
        if value.get("download"):
            value["content"]=read_file(store,item["id"],args.get("text_offset",0),10000)
        return value
    if len(rows)>args.get("limit",20) and not args.get("item_id"):
        return listing(rows,args,live)|{"needs_resource_selection":True}
    return school.download_items(store,page,dict(item_ids=[i["id"] for i in rows],refresh=args.get("refresh",False)),progress)
