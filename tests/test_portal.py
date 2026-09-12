import json
import zipfile
from datetime import timedelta
import pytest
from edinburgh_study_agent.store import Store
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.services import content_url, directory
from edinburgh_study_agent import collections, school, portal
from edinburgh_study_agent.file_text import read_file
from edinburgh_study_agent.downloads import digest_file

def observed(store):
    item=Item(native_id="internship",kind="resource",title="Chemistry internship",
        url="https://careers.ed.ac.uk/jobs-and-internships",excerpt="Chemistry internship",service_id="careers")
    receipt=store.capture(Observation(source="university",source_url=item.url,title=item.title,
        observed_at=now_utc(),scope="test fixture",text=item.title,items=[item]))
    return receipt["inserted"][0]

@pytest.mark.parametrize("url",[
 "https://ed.ac.uk.evil.example/page","http://www.ed.ac.uk/events",
 "https://www.myed.ed.ac.uk/account/logout","https://www.myed.ed.ac.uk/?action=delete",
 "https://www.hub.ed.ac.uk/providers/saml/SsoPostRedirect/1",
 "https://www.euclid.ed.ac.uk/urd/sits.urd/run/SECRET",
 "https://www.ed.ac.uk/events?session=secret"])
def test_portal_rejects_noncontent_and_session_links(url):
    with pytest.raises(ValueError):
        content_url(url)

def test_directory_is_not_proof_of_private_access(tmp_path):
    s=Store(tmp_path)
    d=directory(s)
    assert len(d["services"])>=15 and d["directory_is_not_connection_proof"]
    assert all(i["coverage"]=="not_yet_verified" for i in d["services"])
    assert directory(s,"实习")["services"]

def test_collection_survives_resource_refresh_and_can_archive(tmp_path):
    s=Store(tmp_path)
    key=observed(s)
    result=collections.collect(s,key,"实习",["化学"],"核实截止日期")
    collections.collect(s,key,"实习",["化学","暑期"],"准备申请")
    entries=collections.collections(s,query="暑期")["entries"]
    assert len(entries)==1 and entries[0]["item"]["id"]==key
    assert result["university_record_changed"] is False
    collections.collect(s,key,"实习",archived=True)
    assert collections.collections(s)["entries"]==[]
    assert len(collections.collections(s,include_archived=True)["entries"])==1

def test_dead_worker_is_reported_without_rewriting_history(tmp_path,monkeypatch):
    s=Store(tmp_path)
    job="f"*32
    original={"job_id":job,"action":"login","state":"waiting_for_login","worker_pid":99,
              "updated_at":(now_utc()-timedelta(minutes=5)).isoformat()}
    path=school.job_path(s,job)
    school.write_json(path,original)
    monkeypatch.setattr(school,"worker_running",lambda _:False)
    assert school.read_job(s,job)["state"]=="failed"
    assert school.session_status(s)["active_jobs"]==[]
    assert json.loads(path.read_text())["state"]=="waiting_for_login"

def add_file(s,key,path,filename):
    with s.connection() as db:
        record=dict(item_id=key,path=str(path),filename=filename,sha256=digest_file(path),
                    source_page_url="https://www.learn.ed.ac.uk/ultra/course",downloaded_at=now_utc().isoformat())
        db.execute("INSERT INTO downloads VALUES(?,?,?,?)",(key,record["sha256"],record["downloaded_at"],json.dumps(record)))

def test_xlsx_text_reads_shared_and_inline_strings_and_detects_tampering(tmp_path):
    s=Store(tmp_path)
    key=observed(s)
    path=s.root/"downloads"/"notes.xlsx"
    path.parent.mkdir()
    with zipfile.ZipFile(path,"w") as z:
        z.writestr("xl/sharedStrings.xml",'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Chemistry</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml",'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c><c t="inlineStr"><is><t>Exam</t></is></c></row></sheetData></worksheet>')
    add_file(s,key,path,"notes.xlsx")
    result=read_file(s,key)
    assert "Chemistry\tExam" in result["text"] and result["verified"]
    path.write_bytes(b"changed")
    with pytest.raises(ValueError,match="differs"):
        read_file(s,key)

def test_download_metadata_cannot_read_arbitrary_file(tmp_path):
    s=Store(tmp_path/"data")
    key=observed(s)
    external=tmp_path/"private.txt"
    external.write_text("not a plugin download")
    add_file(s,key,external,"private.txt")
    with pytest.raises(ValueError,match="unavailable"):
        read_file(s,key)

def test_file_text_pagination(tmp_path):
    s=Store(tmp_path)
    key=observed(s)
    path=s.root/"downloads"/"notes.txt"
    path.parent.mkdir()
    path.write_text("abcdef "*500,encoding="utf-8")
    add_file(s,key,path,"notes.txt")
    first=read_file(s,key,max_chars=500)
    second=read_file(s,key,offset=first["next_offset"],max_chars=500)
    assert first["has_more"] and second["offset"]==500
    assert len(first["text"])==500

def test_read_only_euclid_section_selection_rejects_actions():
    with pytest.raises(ValueError,match="read-only"):
        portal.select_read_link(None,"Submit registration")

def test_timetabler_login_page_never_counts_as_school_data():
    class Page:
        def title(self): return "Log in - Timetabler"
    assert portal.login_gate(Page())

def test_identity_lookup_ignores_course_text(tmp_path):
    s=Store(tmp_path)
    observed(s)
    assert portal.campus_email(s) is None

def test_timetabler_uses_documented_uun_login_suffix(tmp_path):
    s=Store(tmp_path)
    text="Logged in: Test Student (s0000000)\nUniversity Email:\ns0000000@sms.ed.ac.uk"
    s.capture(Observation(source="university",source_url="https://www.myed.ed.ac.uk/",
        title="EUCLID: Personal Details",observed_at=now_utc(),scope="synthetic identity",
        authentication="authenticated",text=text,items=[]))
    assert portal.campus_email(s)=="s0000000@ed.ac.uk"

def test_directory_uses_actual_learn_evidence(tmp_path):
    s=Store(tmp_path)
    s.capture(Observation(source="learn",source_url="https://www.learn.ed.ac.uk/ultra/course",
        title="Courses",observed_at=now_utc(),scope="displayed list",
        authentication="authenticated",coverage="complete_visible_scope",text="Courses",items=[]))
    learn=next(x for x in directory(s)["services"] if x["id"]=="learn")
    assert learn["coverage"]=="complete_visible_scope"
    assert learn["last_check"]["authentication"]=="authenticated"
