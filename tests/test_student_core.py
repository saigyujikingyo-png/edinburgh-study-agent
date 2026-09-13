import json
from datetime import timedelta
import pytest
from edinburgh_study_agent import timetable, materials, learn_updates, campus_events, school, workflow_cache, agenda
from edinburgh_study_agent.models import Item,Observation,now_utc
from edinburgh_study_agent.store import Store
from edinburgh_study_agent.responses import page_job
from edinburgh_study_agent.html_content import table_rows

def export_html():
    header="<tr>"+"".join("<th>"+s+"</th>" for s in ["Title","Type","Date","Day of the Week","Start Time","End Time","Location","Weeks"])+"</tr>"
    rows=[
        ["Algebra","Lecture","Mon, 19th October 2026","Monday","09:00","09:50","Room A","(2026/7) S1 Wk 5"],
        ["Algebra","Lecture","Mon, 26th October 2026","Monday","09:00","09:50","Room A","(2026/7) S1 Wk 6"],
        ["Geometry","Lab","Tue, 12th January 2027","Tuesday","10:00","12:00","Room B","(2026/7) S2 Wk 1"],
        ["Old","Lecture","Mon, 20th October 2025","Monday","09:00","09:50","Room C","(2025/6) S1 Wk 5"]]
    return "<table>"+header+"".join("<tr>"+"".join("<td>"+v+"</td>" for v in row)+"</tr>" for row in rows)+"</table>"

def test_personal_export_filters_year_semester_and_keeps_dst_and_dates():
    data=timetable.parse_export(export_html())
    result=timetable.select(data,dict(academic_year="2026/27",semester=1))
    assert result["occurrence_count"]==2 and result["total_items"]==1
    assert result["items"][0]["dates"]==["2026-10-19","2026-10-26"]
    rows=timetable.select(data,dict(academic_year="2026/27",semester=1,view="occurrences"))["items"]
    assert rows[0]["starts_at"].endswith("+01:00")
    assert rows[1]["starts_at"].endswith("+00:00")
    assert data["unparsed_rows"]==0

def test_malformed_export_reports_partial_and_empty_year_is_not_empty_schedule():
    data=timetable.parse_export(export_html().replace("Mon, 19th October 2026","unknown date"))
    assert data["unparsed_rows"]==1 and data["coverage"]=="partial"
    value=timetable.select(data,dict(academic_year="2027/28"))
    assert value["coverage"]=="partial" and "does not prove" in value["warning"]
    with pytest.raises(ValueError,match="headers"):timetable.parse_export("<h1>Sign in</h1>")

def test_export_form_never_creates_link_or_saves_preferences():
    args=timetable.export_form()
    assert args["permittedPublishStatuses[]"]=="Live" and args["format"]=="HTML"
    assert args["startTime"].endswith("00:00:00") and args["endTime"].endswith("23:59:00")
    assert args["isCombinedWeeks"]=="false"
    assert not any(x in " ".join(args).casefold() for x in ("password","token","remember","studentid"))

def test_recipe_pagination_survives_job_poll():
    rows=[dict(week=x,days={"Mon":"x"*40}) for x in range(11)]
    body=timetable.paged(rows,dict(offset=2,limit=3))
    value=page_job(dict(action="timetable",result=body))
    assert value["result"]["offset"]==2 and value["result"]["next_offset"]==5
    assert value["result"]["total_items"]==11
    assert value["result"]["continuation_tool"]=="study_timetable"

def test_pagination_budget_never_silently_skips_rows():
    rows=[dict(text="x"*500) for _ in range(5)]
    seen=[];offset=0
    while True:
        value=timetable.paged(rows,dict(offset=offset,limit=5),1100)
        seen.extend(value["items"])
        if value["next_offset"] is None:break
        offset=value["next_offset"]
    assert seen==rows

def capture_resource(store,title="Lecture slides",native="_3_1",course="_1_1"):
    item=Item(native_id=native,kind="resource",title=title,course_id=course,url=f"https://www.learn.ed.ac.uk/ultra/courses/{course}/file/{native}",excerpt=title)
    store.capture(Observation(source="learn",source_url=item.url,title=title,observed_at=now_utc(),scope="Synthetic resource fixture",text=title,items=[item]))
    return store.list_items("resource")["items"][0]

def test_material_read_ambiguity_returns_choices_without_browser(tmp_path,monkeypatch):
    store=Store(tmp_path)
    capture_resource(store,native="_3_1");capture_resource(store,native="_4_1")
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw:pytest.fail("No browser worker expected"))
    value=school.start_job(store,"materials",dict(query="lecture",operation="read"))
    assert value["state"]=="partial" and value["browser_started"] is False
    assert value["result"]["needs_resource_selection"]

def test_material_aliases_and_scope_do_not_invent_missing_files(tmp_path):
    store=Store(tmp_path);capture_resource(store,"Semester timetable")
    rows,choice=materials.candidates(store,dict(query="课表"))
    assert len(rows)==1 and choice is None
    value=materials.listing([],{},False)
    assert value["coverage"]=="partial" and "not proven absent" in value["note"]

def test_cache_expiry_and_refresh_never_claim_live(tmp_path,monkeypatch):
    store=Store(tmp_path);data=timetable.parse_export(export_html())
    workflow_cache.put(store,"timetable","personal",data)
    v=school.cached_operation(store,"timetable",dict(academic_year="2026/27"))
    assert v["cache_hit"] and not v["remote_freshness_checked"]
    assert school.cached_operation(store,"timetable",dict(refresh=True)) is None
    stamp=now_utc()
    monkeypatch.setattr(workflow_cache,"now_utc",lambda:stamp+timedelta(seconds=301))
    assert school.cached_operation(store,"timetable",{}) is None

def test_public_calendar_source_and_field_provenance():
    html="""<div itemtype="http://schema.org/Event"><time itemprop="startDate" datetime="2026-09-21T14:00:00+01:00"></time>
    <a itemprop="url" href="/events/talk"><span itemprop="name">Research talk</span></a>
    <span itemprop="performer"><span itemprop="name">Speaker name</span></span>
    <span itemprop="location">Room A</span></div>"""
    rows=campus_events.event_rows(html,campus_events.PHYSICS)
    assert rows[0]["title"]=="Research talk" and rows[0]["location"]=="Room A"
    assert rows[0]["url"]=="https://www.ph.ed.ac.uk/events/talk"
    with pytest.raises(ValueError):campus_events.event_rows("<h1>Event directory</h1>",campus_events.PHYSICS)

def test_academic_range_preserves_multi_day_events():
    html="<table><tr><td>6-8 January 2027</td><td>January Welcome</td></tr><tr><td>Date unknown</td><td>Undated note</td></tr></table>"
    rows=campus_events.academic_rows(html,campus_events.SEMESTERS+"202627","2026/27")
    assert (rows[0]["start_date"],rows[0]["end_date"])==("2027-01-06","2027-01-08")
    assert rows[1]["start_date"] is None

def test_official_year_link_and_source_failures_are_not_empty_calendar(tmp_path,monkeypatch):
    with pytest.raises(ValueError):
        campus_events.academic_url('<a href="https://other.example/202627">2026/27</a>',"2026/27")
    assert campus_events.academic_url('<a href="/202627">2026/27</a>',"2026/27").endswith("/202627")
    monkeypatch.setattr(campus_events,"fetch",lambda _:(_ for _ in ()).throw(TimeoutError()))
    result=campus_events.read(Store(tmp_path),dict(source="all",academic_year="2026/27"))
    assert len(result["sources"])==2 and all(p["coverage"]=="unavailable" for p in result["sources"])
    assert result["coverage"]=="partial"

def test_message_zero_unread_is_not_empty_history(tmp_path):
    data=dict(items=[dict(title="Algebra",unread_count=0,course_code="ALG101")],
              scope="Unread counters are not message history.",coverage="partial")
    result=learn_updates.select(data,{},True)
    assert result["items"][0]["unread_count"]==0
    assert "not message history" in result["scope"] and result["cache_hit"]

def test_inert_html_ignores_script_content_and_retains_unicode():
    rows=table_rows("<table><tr><td>日程<script>bad()</script></td><td>A &amp; B<br>Room</td></tr></table>")
    assert rows==[["日程","A & B Room"]]

def test_current_timetable_snapshot_excludes_superseded_items_without_cancelling(tmp_path):
    store=Store(tmp_path);stamp=now_utc()
    title="Class"
    item=Item(native_id="timetabler:test",kind="event",title=title,url=timetable.ENTRY,excerpt=title,
        starts_at="2026-09-21T09:00:00+01:00",ends_at="2026-09-21T10:00:00+01:00")
    store.capture(Observation(source="timetable",source_url=timetable.ENTRY,title=title,observed_at=stamp,
        scope="Exported rows",text=title,items=[item]))
    assert agenda.window(store,"2026-09-21","2026-09-21")["total_matches"]==1
    store.capture(Observation(source="timetable",source_url=timetable.ENTRY,title="Snapshot",
        observed_at=stamp+timedelta(seconds=1),scope="Personal Timetabler activity export snapshot",text="New empty export"))
    assert agenda.window(store,"2026-09-21","2026-09-21")["total_matches"]==0
    assert store.list_items("event")["items"][0]["status"]=="unknown"


@pytest.mark.parametrize("text,expected",[
 ("18 November - 26 November 2026",("2026-11-18","2026-11-26")),
 ("26 April - 21 May 2027",("2027-04-26","2027-05-21")),
 ("21 December 2026 - 10 January 2027",("2026-12-21","2027-01-10")),
 ("7 - 8 December",(None,None))])
def test_source_date_ranges_do_not_silently_use_only_last_date(text,expected):
    assert campus_events.date_range(text)==expected


def test_repeated_pdf_header_keeps_cross_page_continuation():
    from edinburgh_study_agent.document_layout import weekly_grid
    headers=["","Mon","Tue","Wed","Thu","Fri"]
    rows=[dict(page=1,top=90,cells=headers),dict(page=1,top=80,cells=["1","Lab","","","",""]),
          dict(page=2,top=90,cells=headers),dict(page=2,top=80,cells=["","continued","","","",""])]
    weeks,problems=weekly_grid(rows,[dict(page=1,top=100,semester=1)])
    assert weeks[0]["days"]["Mon"]=="Lab\ncontinued"
    assert weeks[0]["pages"]==[1,2] and not problems

def test_closed_course_is_not_login_failure(monkeypatch):
    class Locator:
        first=None
        def __init__(self):self.first=self
        def count(self):return 1
        def is_visible(self):return True
    class Page:
        url="https://www.learn.ed.ac.uk/ultra/courses/_1_1/outline"
        def get_by_text(self,*args,**kwargs):return Locator()
    monkeypatch.setattr(school,"authenticated",lambda p:False)
    with pytest.raises(school.CourseUnavailable):school.ensure_learn(Page())


def test_legacy_chat_work_catalog_routes_to_same_core(tmp_path,monkeypatch):
    from edinburgh_study_agent import server
    store=Store(tmp_path);monkeypatch.setattr(server,"store",lambda:store)
    workflow_cache.put(store,"timetable","personal",timetable.parse_export(export_html()))
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw:pytest.fail("No browser expected"))
    reply=server.study_read_service(service_id="timetable",query='{"semester":1,"academic_year":"2026/27","view":"occurrences","limit":1}')
    body=reply.structuredContent["result"]
    assert body["occurrence_count"]==2 and body["legacy_catalog_compatible"]
    continuation=body["continuation"]
    assert continuation["tool"]=="study_read_service"
    next_reply=server.study_read_service(**{k:v for k,v in continuation.items() if k!="tool"})
    assert next_reply.structuredContent["result"]["offset"]==1
    with pytest.raises(ValueError):
        server.study_read_service(service_id="timetable",query='{"download_url":"https://other.example"}')


def test_semester_overview_includes_all_occurrences_before_detail_pagination():
    data=timetable.parse_export(export_html())
    value=timetable.select(data,dict(academic_year="2026/27",semester=1,view="occurrences",limit=1))
    assert len(value["items"])==1 and value["has_more"]
    assert value["overview"]["occurrence_count"]==2
    assert sum(w["occurrences"] for w in value["overview"]["weeks"])==2
    assert value["overview"]["types"]=={"Lecture":2}


def test_legacy_event_detail_still_uses_existing_link_reader():
    from edinburgh_study_agent import server
    assert server.legacy_basic_workflow("events","observed-event-id","") is None
