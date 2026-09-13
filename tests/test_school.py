from contextlib import contextmanager
import json
import os
import pytest
from edinburgh_study_agent import school
from edinburgh_study_agent.store import Store
from edinburgh_study_agent.school_dom import (COURSE_CARDS, RESOURCE_LINKS, EXPANDERS,
    course_items, resource_items, observation, learn_url)


@pytest.fixture(scope="module")
def dom_page():
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Sandboxed Chrome requires a non-root runner; run DOM checks in CI.")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chrome",headless=True,chromium_sandbox=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_real_dom_course_cards_exclude_placeholders_and_preserve_status(dom_page):
    dom_page.set_content("""
    <div><a id="course-link-_12_1" href="javascript:void(0)">Chemistry 2026</a><span class="course-status">Open</span></div>
    <div><a id="course-link-_13_1" href="javascript:void(0)">Physics 2026</a><span class="course-status">Closed</span></div>
    <div><a id="course-link-" href="javascript:void(0)"></a></div>
    """)
    items = course_items(dom_page.evaluate(COURSE_CARDS))
    assert [(i.native_id,i.status) for i in items] == [("_12_1","available"),("_13_1","unavailable")]
    assert all(i.url is None for i in items)
    obs = observation("https://www.learn.ed.ac.uk/ultra/course","Courses",items,"Page 1 of 2")
    assert obs.coverage == "partial"


def test_only_content_expansion_controls_are_selected(dom_page):
    dom_page.set_content("""
    <button id="learning-module-title-_1_1" aria-expanded="false">Week 1</button>
    <button id="folder-title-_2_1" aria-expanded="false">Notes</button>
    <button id="learning-module-title-_3_1" aria-expanded="true">Open</button>
    <button id="delete-_9_1" aria-expanded="false">Delete</button>
    <button aria-expanded="false">Download</button>
    """)
    assert [r["id"] for r in dom_page.evaluate(EXPANDERS)] == [
        "learning-module-title-_1_1","folder-title-_2_1"]


def test_resource_dom_and_parser_reject_wrong_course_and_sensitive_links(dom_page):
    dom_page.set_content("""
    <a href="https://www.learn.ed.ac.uk/ultra/courses/_12_1/file/_99_1?courseId=_12_1">Notes.pdf</a>
    <a href="https://www.learn.ed.ac.uk/ultra/courses/_12_1/assessment/_98_1">Exam</a>
    <a href="https://www.learn.ed.ac.uk/ultra/courses/_13_1/file/_97_1">Other.pdf</a>
    <a href="https://evil.example/ultra/courses/_12_1/file/_96_1">External.pdf</a>
    <a href="https://www.learn.ed.ac.uk/ultra/courses/_12_1/file/_95_1?token=secret">Auth.pdf</a>
    """)
    items = resource_items(dom_page.evaluate(RESOURCE_LINKS),{"native_id":"_12_1","title":"Chemistry"})
    assert [(i.native_id,i.kind) for i in items] == [("_99_1","resource"),("_98_1","assignment")]
    assert items[1].due_at is None and items[1].due_date is None


@pytest.mark.parametrize("url",[
    "http://www.learn.ed.ac.uk/ultra/course",
    "https://www.learn.ed.ac.uk.evil.example/ultra/course",
    "https://www.learn.ed.ac.uk/ultra/course?SAMLResponse=secret",
    "https://www.learn.ed.ac.uk:8443/ultra/course",
])
def test_navigation_rejects_foreign_or_credential_urls(url):
    with pytest.raises(ValueError):
        learn_url(url)


def test_profile_lock_is_exclusive_and_released(tmp_path):
    with school.profile_lock(tmp_path):
        with pytest.raises(school.BrowserBusy):
            with school.profile_lock(tmp_path,timeout=0):
                pass
    with school.profile_lock(tmp_path,timeout=0):
        pass


def test_dispatch_does_not_pass_connection_credentials(tmp_path,monkeypatch):
    launched = []
    class Child:
        pid = 12345
    monkeypatch.setenv("CONTROL_PLANE_API_KEY","sentinel-private-key")
    monkeypatch.setenv("OPENAI_API_KEY","another-private-key")
    for key in ("ANTHROPIC_API_KEY","DEEPSEEK_API_KEY","DSH_AUTH_TOKEN","AZURE_CLIENT_SECRET"):
        monkeypatch.setenv(key,"synthetic-credential")
    monkeypatch.setenv("UOE_LOCALE","fr")
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw: launched.append((a,kw)) or Child())
    result = school.start_job(Store(tmp_path),"courses",{"query":"chemistry"})
    assert result["state"] == "queued" and "arguments" not in result
    assert "CONTROL_PLANE_API_KEY" not in launched[0][1]["env"]
    assert "OPENAI_API_KEY" not in launched[0][1]["env"]
    assert all(key not in launched[0][1]["env"] for key in ("ANTHROPIC_API_KEY","DEEPSEEK_API_KEY","DSH_AUTH_TOKEN","AZURE_CLIENT_SECRET"))
    assert launched[0][1]["env"]["UOE_LOCALE"]=="fr"
    assert launched[0][0][0][-1] == result["job_id"]
    assert result["source_content_is_untrusted"] is True


def test_job_id_cannot_read_arbitrary_files(tmp_path):
    with pytest.raises(ValueError):
        school.read_job(Store(tmp_path),"../../secrets/key")


def test_worker_redacts_browser_error_urls(tmp_path,monkeypatch):
    store = Store(tmp_path)
    job_id = "a"*32
    school.write_json(school.job_path(store,job_id),{
        "job_id":job_id,"action":"courses","arguments":{},"state":"queued"})
    @contextmanager
    def broken(*args,**kwargs):
        raise RuntimeError("https://example.test/file?signature=TOP_SECRET")
        yield
    monkeypatch.setattr(school,"browser_context",broken)
    school.execute_job(store,job_id)
    raw = school.job_path(store,job_id).read_text()
    assert "TOP_SECRET" not in raw and "signature=" not in raw
    assert school.read_job(store,job_id)["state"] == "failed"


def test_login_required_does_not_fabricate_course_results(tmp_path,monkeypatch):
    store = Store(tmp_path)
    job_id = "b"*32
    school.write_json(school.job_path(store,job_id),{
        "job_id":job_id,"action":"courses","arguments":{},"state":"queued"})
    @contextmanager
    def unauthenticated(*args,**kwargs):
        raise school.LoginRequired()
        yield
    monkeypatch.setattr(school,"browser_context",unauthenticated)
    school.execute_job(store,job_id)
    data = school.read_job(store,job_id)
    assert data["state"] == "needs_login"
    assert "result" not in data
    assert school.session_status(store)["previous_check"]["authenticated"] is False
    assert store.list_items(kind="course")["items"] == []

def test_lazy_course_rows_load_without_waiting_for_visual_stability(dom_page):
    dom_page.set_content("""
      <style>#main{height:150px;overflow:auto}
      .row{height:160px;animation:drift 50ms linear infinite alternate}
      @keyframes drift{from{transform:translateX(0)}to{transform:translateX(2px)}}
      </style>
      <div id="main">
        <div class="row"><a id="course-link-_1_1">Chemistry</a></div>
        <div class="row"><a id="course-link-" style="display:block;height:30px"></a></div>
      </div>
      <script>
      const target=document.getElementById('course-link-');
      new IntersectionObserver(entries=>{
        if(entries.some(e=>e.isIntersecting)){
          target.id='course-link-_2_1';target.textContent='Physics';
        }
      },{root:document.getElementById('main')}).observe(target);
      </script>""")
    result=school.wait_cards(dom_page)
    assert {r["native_id"] for r in result}=={"_1_1","_2_1"}

def test_deep_link_is_revisited_after_sso_returns_courses(monkeypatch):
    class Page:
        url="https://www.learn.ed.ac.uk/"
        visited=[]
        def goto(self,url,**kwargs):
            self.visited.append(url)
            self.url=url
    page=Page()
    def ensure(p):
        if len(p.visited)==1:
            p.url="https://www.learn.ed.ac.uk/ultra/course"
    monkeypatch.setattr(school,"ensure_learn",ensure)
    target="https://www.learn.ed.ac.uk/ultra/courses/_1_1/file/_2_1"
    school.goto_learn(page,target)
    assert page.visited==[target,target]
