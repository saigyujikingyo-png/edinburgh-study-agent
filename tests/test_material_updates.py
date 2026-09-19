from datetime import timedelta
from contextlib import contextmanager
import asyncio

from jsonschema import Draft202012Validator
import pytest

from edinburgh_study_agent import materials, school
from edinburgh_study_agent.contracts_school import MATERIAL_UPDATES
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.responses import page_job
from edinburgh_study_agent.store import Store


def capture(store, items, *, old=False):
    return store.capture(Observation(source="learn",source_url=school.LEARN_HOME,
        title="Synthetic materials",scope="Test fixture",authentication="authenticated",
        observed_at=now_utc()-timedelta(days=1) if old else now_utc(),
        text="\n".join(i.title for i in items),items=items))


def resource(key, title, course="_1_1"):
    return Item(kind="resource",native_id=key,course_id=course,course_title="Synthetic course",
        title=title,excerpt=title,url=f"https://www.learn.ed.ac.uk/ultra/courses/{course}/file/{key}")


def seed(store, count=1):
    capture(store,[Item(kind="course",native_id=f"_{i}_1",title=f"Synthetic course {i}",
        excerpt=f"Synthetic course {i}",status="available") for i in range(1,count+1)],old=True)


def observe(store, rows):
    receipt=capture(store,rows)
    return dict(live=True,items=store.items_by_ids(receipt["inserted"]+receipt["updated"]),
        observed_at=now_utc().isoformat(),remaining_collapsed=1,folders_not_opened=[])


def test_metadata_delta_preserves_unseen_files_and_does_not_claim_byte_changes(tmp_path,monkeypatch):
    store=Store(tmp_path);seed(store)
    capture(store,[resource("_11_1","Old.pdf"),resource("_12_1","Same.pdf"),resource("_13_1","Unseen.pdf")],old=True)
    calls=[]
    def read(s,p,args,progress):
        calls.append(args)
        return observe(s,[resource("_11_1","Renamed.pdf"),resource("_12_1","Same.pdf"),resource("_14_1","Added.pdf")])
    monkeypatch.setattr(school,"list_resources",read)
    value=materials.read(store,object(),dict(operation="updates",course="_1_1"),lambda *a:None)
    assert value["counts"]==dict(newly_observed=1,metadata_changed=1,baseline=0,unchanged_metadata=1,comparison_unknown=0)
    assert {(i["title"],i["change"]) for i in value["items"]}=={("Renamed.pdf","metadata_changed"),("Added.pdf","newly_observed")}
    assert value["courses"][0]["not_seen_in_scan"]==1
    assert len(store.list_items("resource")["items"])==4
    assert value["content_change_checked"] is False and value["coverage"]=="partial"
    assert len(calls)==1 and calls[0]["budget_seconds"]<=20
    Draft202012Validator(MATERIAL_UPDATES).validate(value)


def test_first_observation_is_baseline_and_completed_job_pages_without_rescan(tmp_path,monkeypatch):
    store=Store(tmp_path);seed(store)
    calls=[]
    def read(s,p,args,progress):
        calls.append(args)
        return observe(s,[resource(f"_{i}_1",f"File {i}.pdf") for i in range(10,14)])
    monkeypatch.setattr(school,"list_resources",read)
    value=materials.read(store,object(),dict(operation="updates"),lambda *a:None)
    assert value["counts"]["baseline"]==4 and value["counts"]["newly_observed"]==0
    job=dict(action="materials",result=value)
    first=page_job(job,0,2)["result"];second=page_job(job,2,2)["result"]
    assert first["has_more"] and first["next_offset"]==2
    assert first["continuation_tool"]=="study_school_job"
    assert len(first["items"]+second["items"])==4 and not second["has_more"]
    assert len(job["result"]["items"])==4 and len(calls)==1
    Draft202012Validator(MATERIAL_UPDATES).validate(first)


def test_batch_stops_on_authentication_path_failure_and_retains_completed_course(tmp_path,monkeypatch):
    store=Store(tmp_path);seed(store,3)
    calls=[]
    def read(s,p,args,progress):
        calls.append(args["course_id"])
        if args["course_id"]=="_2_1":
            raise school.SchoolNetworkError("NETWORK_TIMEOUT",host="idp.ed.ac.uk",stage="campus_sign_in")
        return observe(s,[resource("_20_1","Baseline.pdf",args["course_id"])])
    monkeypatch.setattr(school,"list_resources",read)
    value=materials.read(store,object(),dict(operation="updates",course="all"),lambda *a:None)
    assert calls==["_1_1","_2_1"] and value["checked_courses"]==1
    assert value["failure"]["code"]=="NETWORK_TIMEOUT"
    assert value["next_course_offset"]==1 and value["has_more_courses"]
    assert len(value["items"])==1
    assert value["courses"][-1]["checked"] is False
    Draft202012Validator(MATERIAL_UPDATES).validate(value)


def test_batch_cursor_limits_work_and_does_not_repeat_previous_courses(tmp_path,monkeypatch):
    store=Store(tmp_path);seed(store,4)
    calls=[]
    def read(s,p,args,progress):
        calls.append(args["course_id"])
        return dict(live=True,items=[],observed_at=now_utc().isoformat())
    monkeypatch.setattr(school,"list_resources",read)
    first=materials.read(store,object(),dict(operation="updates",max_courses=2),lambda *a:None)
    assert calls==["_1_1","_2_1"] and first["next_course_offset"]==2
    second=materials.read(store,object(),dict(operation="updates",course_offset=2,max_courses=2),lambda *a:None)
    assert calls==["_1_1","_2_1","_3_1","_4_1"] and not second["has_more_courses"]
    with pytest.raises(ValueError):materials.validate(dict(operation="updates",max_courses=4))
    with pytest.raises(ValueError):materials.validate(dict(operation="updates",item_id="file"))


def test_partial_baseline_does_not_invent_new_files(tmp_path,monkeypatch):
    store=Store(tmp_path);seed(store)
    capture(store,[resource(f"_{i}_1",f"Existing {i}.pdf") for i in range(10,260)],old=True)
    capture(store,[resource(f"_{i}_1",f"Existing {i}.pdf") for i in range(260,511)],old=True)
    previous=store.list_items("resource",course_id="_1_1",limit=500)
    unseen=next(i for i in store.list_items("resource",course_id="_1_1",limit=500,offset=500)["items"])
    monkeypatch.setattr(school,"list_resources",lambda *a:dict(live=True,items=[unseen],observed_at=now_utc().isoformat()))
    value=materials.read(store,object(),dict(operation="updates"),lambda *a:None)
    assert previous["total_matches"]==501
    assert value["counts"]["comparison_unknown"]==1 and value["counts"]["newly_observed"]==0


def test_public_tool_worker_and_paged_poll_keep_one_scan(tmp_path,monkeypatch):
    from edinburgh_study_agent import server, contracts
    store=Store(tmp_path);seed(store)
    monkeypatch.setattr(server,"store",lambda:store)
    @contextmanager
    def browser(*args,**kwargs):
        yield type("Context",(),{"pages":[object()]})()
    monkeypatch.setattr(school,"browser_context",browser)
    calls=[]
    def read(s,p,args,progress):
        calls.append(args["course_id"])
        return observe(s,[resource("_40_1","First.pdf"),resource("_41_1","Second.pdf")])
    monkeypatch.setattr(school,"list_resources",read)
    def run(argv,**kwargs):
        school.execute_job(store,argv[-1])
        return type("Child",(),{"pid":1})()
    monkeypatch.setattr(school.subprocess,"Popen",run)
    reply=asyncio.run(server.mcp.call_tool("study_materials",{"operation":"updates","limit":1}))
    assert not reply.isError, reply.structuredContent
    first=reply.structuredContent
    assert first["result"]["has_more"] and len(first["result"]["items"])==1
    contracts.validate_result("study_materials",first)
    second=asyncio.run(server.mcp.call_tool("study_school_job",{"job_id":first["job_id"],"offset":1,"limit":1}))
    assert not second.isError, second.structuredContent
    assert len(second.structuredContent["result"]["items"])==1
    assert not second.structuredContent["result"]["has_more"] and len(calls)==1


def test_login_needed_preserves_partial_result_and_updates_session_observation(tmp_path,monkeypatch):
    from edinburgh_study_agent import server
    store=Store(tmp_path);seed(store)
    monkeypatch.setattr(server,"store",lambda:store)
    @contextmanager
    def browser(*args,**kwargs):
        yield type("Context",(),{"pages":[object()]})()
    monkeypatch.setattr(school,"browser_context",browser)
    def login(*args,**kwargs):
        raise school.LoginRequired(host="idp.ed.ac.uk",stage="campus_sign_in")
    monkeypatch.setattr(school,"list_resources",login)
    def run(argv,**kwargs):
        school.execute_job(store,argv[-1])
        return type("Child",(),{"pid":1})()
    monkeypatch.setattr(school.subprocess,"Popen",run)
    reply=asyncio.run(server.mcp.call_tool("study_materials",{"operation":"updates"}))
    assert not reply.isError, reply.structuredContent
    body=reply.structuredContent
    assert body["state"]=="needs_login" and not body["result"]["remote_freshness_checked"]
    assert body["failure"]["recovery_action"]=="sign_in"
    assert school.session_status(store)["previous_check"]["authenticated"] is False
