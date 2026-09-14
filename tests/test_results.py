import json
import time
from datetime import datetime, timedelta
import pytest
from edinburgh_study_agent import results, school, server, portal
from edinburgh_study_agent.store import Store
from edinburgh_study_agent.models import now_utc


def panels():
    return [dict(academic_year="2026/27",panel_found=True,selected=True,block_count=1,
                 records=[dict(title="Example current - TEST10001",mark="",grade="",credits="20",result="",sit="")]),
            dict(academic_year="2025/26",panel_found=True,selected=False,block_count=1,
                 records=[dict(title="Example previous - TEST08001",mark="0",grade="F",credits="20",result="Published",sit="1")])]


class Page:
    def __init__(self, data=None): self.data=panels() if data is None else data
    def evaluate(self, script): return self.data


def test_all_years_preserve_blank_and_zero_marks_and_dated_evidence(tmp_path):
    store=Store(tmp_path)
    value=results.read_results(store,Page())
    assert value["record_count"]==2 and value["coverage"]=="complete_loaded_years"
    assert [r["mark"] for r in value["items"]]==["","0"]
    assert value["items"][1]["course_code"]=="TEST08001"
    for year in value["years"]:
        obs=store.evidence(year["observation_id"])["observation"]
        assert year["academic_year"] in obs["title"]
        assert obs["authentication"]=="authenticated" and obs["coverage"]=="partial"
        assert datetime.fromisoformat(obs["observed_at"])==datetime.fromisoformat(value["observed_at"])
    current=results.read_results(store,Page(),"current")
    assert len(current["items"])==1 and current["items"][0]["mark"]==""
    previous=results.read_results(store,Page(),"2025/26")
    assert len(previous["items"])==1 and previous["items"][0]["mark"]=="0"


def test_missing_year_and_missing_parser_fields_do_not_claim_no_results(tmp_path):
    store=Store(tmp_path)
    missing=results.read_results(store,Page(),"2024/25")
    assert missing["coverage"]=="partial" and missing["failed"]
    assert missing["available_years"]==["2026/27","2025/26"]
    broken=panels(); broken[1]["records"]=[]
    value=results.read_results(store,Page(broken))
    assert value["coverage"]=="partial" and not value["years"][1]["complete_loaded_panel"]
    assert results.cached_results(store,"all") is None


@pytest.mark.parametrize("year",["2025/27","2025-26","all;submit","2025/2026","../private"])
def test_invalid_year_fails_before_browser(tmp_path,monkeypatch,year):
    monkeypatch.setattr(server,"store",lambda:Store(tmp_path))
    monkeypatch.setattr(school,"start_job",lambda *a,**k:pytest.fail("started browser"))
    with pytest.raises(ValueError,match="academic_year"):
        server.study_results(year)


def test_cache_is_short_lived_private_invalidated_and_refreshable(tmp_path,monkeypatch):
    store=Store(tmp_path)
    results.read_results(store,Page())
    cache=results.cached_results(store,"all")
    assert cache["cache_hit"] and cache["live"] is False and not cache["remote_freshness_checked"]
    assert results.cached_results(Store(tmp_path/"different-student"),"all") is None
    assert school.cached_operation(store,"results",{"academic_year":"all","refresh":True}) is None
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw:pytest.fail("browser worker started"))
    hit=school.start_job(store,"results",{"academic_year":"all","refresh":False})
    assert hit["state"]=="complete" and hit["browser_started"] is False
    clock=now_utc()
    with monkeypatch.context() as patch:
        patch.setattr(results,"now_utc",lambda:clock+timedelta(seconds=301))
        assert results.cached_results(store,"all") is None
    results.invalidate_cache(store)
    assert results.cached_results(store,"all") is None


def test_duplicate_running_results_job_does_not_queue_a_browser(tmp_path,monkeypatch):
    store=Store(tmp_path); key="a"*32
    arguments={"academic_year":"all","refresh":True}
    school.write_json(school.job_path(store,key),dict(job_id=key,action="results",arguments=arguments,
        state="running",updated_at=now_utc().isoformat()))
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw:pytest.fail("duplicate browser"))
    hit=school.start_job(store,"results",arguments)
    assert hit["job_id"]==key and hit["reused_active_job"]


def test_terminal_result_requires_no_poll_and_has_explicit_pagination(tmp_path,monkeypatch):
    store=Store(tmp_path)
    monkeypatch.setattr(server,"store",lambda:store)
    source=panels(); source[0]["records"]*=110; source[0]["block_count"]=110
    results.read_results(store,Page(source))
    monkeypatch.setattr(school,"wait_job",lambda *a,**kw:pytest.fail("terminal job polled"))
    value=server.study_results().structuredContent
    assert value["state"]=="complete"
    body=value["result"]
    assert len(body["items"])==100 and body["next_offset"]==100 and body["total_items"]==111


@pytest.fixture(scope="module")
def browser_page():
    from playwright.sync_api import sync_playwright, Error
    with sync_playwright() as runtime:
        try:
            browser=runtime.chromium.launch(channel="chrome",headless=True)
        except Error:
            pytest.skip("Optional DOM contract test requires installed Chrome")
        context=browser.new_context()
        context.route("**/*",lambda route:route.fulfill(status=200,body="<html><body></body></html>",content_type="text/html"))
        page=context.new_page()
        yield page
        browser.close()


def test_real_dom_reads_labelled_hidden_years_without_inputs_or_phone_duplicates(browser_page):
    page=browser_page
    page.goto("https://www.euclid.ed.ac.uk/")
    def panel(year,title,mark,hidden=False):
        return f'''
          <div id="tab{year}" style="{'display:none' if hidden else ''}">
           <div data-uoeid="student-course-mark"><div class="accordion-heading">
            <div class="hidden-phone"><txtbold>{title}</txtbold></div>
            <div class="visible-phone"><txtbold>Duplicate phone title</txtbold></div></div>
            <div data-uoeid="course-mark">{mark}</div><div data-uoeid="course-grade">A</div>
            <div data-uoeid="course-credits">20</div><div data-uoeid="course-result">Published</div>
            <input type="hidden" name="session" value="must-never-leave-browser">
           </div>
          </div>'''
    page.set_content('<a href="#tab2026">2026/27</a><a href="#tab2025">2025/26</a>'+
        panel(2026,"Example current - TEST10001","")+panel(2025,"Example previous - TEST08001","0",True))
    data=page.evaluate(results.COURSE_RESULTS)
    assert len(data)==2 and data[0]["selected"] and not data[1]["selected"]
    assert data[1]["records"][0]["mark"]=="0"
    assert "must-never" not in json.dumps(data) and "Duplicate" not in json.dumps(data)


def test_dynamic_myed_ready_controls_do_not_wait_for_widget_stability(browser_page):
    page=browser_page;page.goto("https://www.myed.ed.ac.uk/")
    page.set_content('<button>Accounts</button><div id="widget"></div>'
        '<script>setInterval(()=>document.querySelector("#widget").textContent=Date.now(),10)</script>')
    start=time.monotonic();portal.wait_page(page)
    assert time.monotonic()-start<1
    page.goto("https://outside.example/")
    page.set_content('<button>Accounts</button>')
    assert page.evaluate(portal.CAMPUS_READY) is False


def test_service_keyword_list_finds_results_instead_of_empty_directory(tmp_path):
    from edinburgh_study_agent.services import directory
    value=directory(Store(tmp_path),"result grade mark assessment")
    assert "euclid" in [item["id"] for item in value["services"]]


@pytest.mark.parametrize("direct_fails",[False,True])
@pytest.mark.parametrize("legacy_query",[False,True])
def test_euclid_uses_fixed_entry_with_one_myed_fallback(tmp_path,monkeypatch,direct_fails,legacy_query):
    from edinburgh_study_agent.services import service
    calls=[]
    class Control:
        first=None
        def count(self): return 0
        def evaluate_all(self,script):
            return [{"title":"My student record","url":portal.EUCLID_ENTRY}]
    class PortalPage:
        url="about:blank"
        def goto(self,url,**kwargs):
            calls.append(url)
            if direct_fails and len(calls)==1: raise RuntimeError("navigation unavailable")
            self.url=url
        def title(self): return "EUCLID: Courses"
        def get_by_role(self,*a,**kw): return Control()
        def locator(self,*a,**kw): return Control()
    monkeypatch.setattr(portal,"follow_sso",lambda page,store:page)
    monkeypatch.setattr(portal,"authentication",lambda page:"authenticated")
    monkeypatch.setattr(portal,"select_read_link",lambda page,label:(page,True))
    monkeypatch.setattr(results,"read_results",lambda store,page,year:{"academic_year":year,"coverage":"complete_loaded_years"})
    value=portal.read_service(Store(tmp_path),PortalPage(),
        {"service_id":"euclid","section":"Courses","results_only":not legacy_query,"query":"all" if legacy_query else ""},lambda x:None)
    assert value["academic_year"]=="all"
    expected=[portal.EUCLID_ENTRY]
    if direct_fails: expected += [service("euclid")["url"],portal.EUCLID_ENTRY]
    assert calls==expected


def test_old_portal_call_advertises_results_without_an_extra_catalog_roundtrip(tmp_path,monkeypatch):
    store=Store(tmp_path)
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw:object())
    queued=school.start_job(store,"myed")
    hint=queued["available_workflows"]["course_results"]
    from edinburgh_study_agent import __version__
    assert queued["plugin_version"] == __version__
    assert queued["host_browser_required"] is False
    assert hint["tool"]=="study_results" and hint["arguments"]=={"academic_year":"all"}
    assert hint["status"]=="implemented"


def test_summary_uses_credits_preserves_zero_and_does_not_infer_blank_marks():
    rows=[dict(mark="80%",credits="20"),dict(mark="50",credits="40"),
          dict(mark="0",credits="20"),dict(mark="-",credits="-")]
    summary=results.year_summary(rows,True)
    assert summary==dict(numeric_marks=3,marks_not_in_mean=1,
        mean_status="calculated",credits_used=80.0,credit_weighted_mean=45.0)
    assert rows[-1]==dict(mark="-",credits="-")


@pytest.mark.parametrize("weight",["", "-", "0", "-20", "NaN", "Infinity"])
def test_summary_withholds_mean_when_any_numeric_mark_has_unusable_credits(weight):
    summary=results.year_summary([dict(mark="80",credits="20"),dict(mark="50",credits=weight)],True)
    assert summary["mean_status"]=="missing_or_nonpositive_credits"
    assert "credit_weighted_mean" not in summary and "credits_used" not in summary


def test_summary_withholds_incomplete_panel_and_missing_marks():
    partial=results.year_summary([dict(mark="80",credits="20")],False)
    assert partial["mean_status"]=="incomplete_panel" and "credit_weighted_mean" not in partial
    blank=results.year_summary([dict(mark="-",credits="20"),dict(mark="",credits="20")],True)
    assert blank["mean_status"]=="no_numeric_marks" and blank["numeric_marks"]==0
    assert "credit_weighted_mean" not in blank


def test_summary_rejects_nonpercentage_values_and_rounds_explicitly():
    rows=[dict(mark="60.005%",credits="20"),
          *[dict(mark=mark,credits="20") for mark in ("101","-1","NaN","P","Infinity")]]
    value=results.year_summary(rows,True)
    assert value["numeric_marks"]==1 and value["marks_not_in_mean"]==5
    assert value["credit_weighted_mean"]==60.01


def test_old_cache_gets_current_summaries_before_response_pagination(tmp_path,monkeypatch):
    store=Store(tmp_path)
    source=panels(); source[0]["records"]*=110; source[0]["block_count"]=110
    value=results.read_results(store,Page(source))
    for year in value["years"]:
        year.pop("summary")
    value.pop("answer_guidance")
    value.pop("summary_method")
    with store.connection() as db:
        db.execute("UPDATE result_cache SET payload=? WHERE academic_year='all'",(json.dumps(value),))
    monkeypatch.setattr(server,"store",lambda:store)
    actual=server.study_results().structuredContent["result"]
    assert actual["years"][0]["summary"]["marks_not_in_mean"]==110
    assert actual["years"][1]["summary"]["credit_weighted_mean"]==0
    assert len(actual["items"])==100
    assert actual["answer_guidance"] and actual["summary_method"]


def test_learn_activity_and_messages_shell_is_not_misclassified_as_logged_out(browser_page):
    page=browser_page
    html='<main>Messages</main><nav><a href="/ultra/profile">Profile</a><a href="/ultra/course">Courses</a><a href="/ultra/messages">Messages</a></nav>'
    page.goto("https://www.learn.ed.ac.uk/ultra/messages")
    page.set_content(html)
    assert school.authenticated(page)
    page.set_content(html+'<input type="password">')
    assert not school.authenticated(page)
    page.goto("https://outside.example/")
    page.set_content(html)
    assert not school.authenticated(page)
