import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
import pytest
from edinburgh_study_agent import server, school, collections, file_text
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.store import Store
from edinburgh_study_agent.downloads import digest_file


def capture(store, titles=("Straße notes","Café notes","实验资源")):
    items=[Item(native_id=str(n),kind="resource",title=title,
                url="https://www.learn.ed.ac.uk/ultra/course",
                excerpt=title+" "+("Synthetic study text. "*80)) for n,title in enumerate(titles)]
    obs=Observation(source="learn",source_url="https://www.learn.ed.ac.uk/ultra/course",
        title="Synthetic",observed_at=now_utc(),scope="synthetic fixture",
        text="\n".join(i.excerpt for i in items),items=items)
    return store.capture(obs)


def add_text(store,key):
    path=store.root/"downloads"/"sample.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text("Synthetic lecture text.\n"*1200,encoding="utf-8")
    record=dict(item_id=key,path=str(path),filename=path.name,sha256=digest_file(path),
                downloaded_at=now_utc().isoformat(),source_page_url="https://www.learn.ed.ac.uk/ultra/course")
    with store.connection() as db:
        db.execute("INSERT INTO downloads VALUES(?,?,?,?)",(key,record["sha256"],record["downloaded_at"],json.dumps(record)))
    return path


def test_search_migrates_existing_database_and_preserves_unicode(tmp_path):
    store=Store(tmp_path)
    capture(store)
    with store.connection() as db:
        db.execute("ALTER TABLE items DROP COLUMN search_text")
    reopened=Store(tmp_path)
    assert reopened.list_items(query="STRASSE")["total_matches"]==1
    assert reopened.list_items(query="CAFÉ")["total_matches"]==1
    assert reopened.list_items(query="实验")["total_matches"]==1
    pages=[reopened.list_items(limit=1,offset=n) for n in range(3)]
    assert len({p["items"][0]["id"] for p in pages})==3
    assert pages[0]["next_offset"]==1 and pages[-1]["next_offset"] is None


def test_status_only_deserializes_latest_observation_per_source(tmp_path,monkeypatch):
    store=Store(tmp_path)
    for _ in range(20):
        capture(store)
    loads=json.loads
    count=[]
    monkeypatch.setattr(json,"loads",lambda *a,**kw:(count.append(1),loads(*a,**kw))[1])
    store.status()
    assert len(count)==1


def test_collection_listing_uses_one_database_connection(tmp_path,monkeypatch):
    store=Store(tmp_path)
    receipt=capture(store)
    for key in receipt["inserted"]:
        collections.collect(store,key,"Example")
    connection=store.connection
    calls=[]
    @contextmanager
    def counted():
        calls.append(1)
        with connection() as db:
            yield db
    monkeypatch.setattr(store,"connection",counted)
    result=collections.collections(store,limit=1)
    assert len(calls)==1
    assert result["total_matches"]==3 and result["next_offset"]==1


def test_compact_search_keeps_provenance_and_full_evidence(tmp_path,monkeypatch):
    store=Store(tmp_path)
    receipt=capture(store)
    monkeypatch.setattr(server,"store",lambda:store)
    compact=server.study_search(limit=2)
    full=server.study_search(limit=2,detail="full")
    row=compact.structuredContent["items"][0]
    assert len(row["excerpt"])==160 and row["excerpt_truncated"]
    assert row["observation_id"]==receipt["observation_id"]
    assert row["source"]=="learn" and row["observed_at"] and row["url"]
    assert len(json.dumps(compact.structuredContent))<len(json.dumps(full.structuredContent))/2
    assert json.loads(compact.content[0].text)==compact.structuredContent
    evidence=server.study_evidence(receipt["observation_id"],max_chars=500).structuredContent
    assert evidence["has_more"] and evidence["next_offset"]==500
    assert evidence["observation"]["item_count"]==3
    assert "items" not in evidence["observation"]


def test_job_result_pagination_is_explicit_and_nonmutating(tmp_path,monkeypatch):
    store=Store(tmp_path)
    capture(store,tuple("Resource "+str(n) for n in range(25)))
    monkeypatch.setattr(server,"store",lambda:store)
    job="c"*32
    original={"job_id":job,"action":"courses","state":"complete","updated_at":now_utc().isoformat(),
              "result":{"items":store.list_items()["items"]}}
    school.write_json(school.job_path(store,job),original)
    first=server.study_school_job(job).structuredContent["result"]
    second=server.study_school_job(job,offset=20).structuredContent["result"]
    assert len(first["items"])==20 and first["next_offset"]==20
    assert len(second["items"])==5 and not second["response_truncated"]
    assert len(school.read_job(store,job)["result"]["items"])==25


def test_long_poll_returns_completion_without_extra_agent_calls(tmp_path):
    store=Store(tmp_path)
    job="d"*32
    value={"job_id":job,"action":"courses","state":"running","updated_at":now_utc().isoformat()}
    school.write_json(school.job_path(store,job),value)
    def finish():
        time.sleep(0.1)
        school.write_json(school.job_path(store,job),value|{"state":"complete","result":{"items":[]}})
    worker=threading.Thread(target=finish)
    worker.start()
    try:
        assert school.wait_job(store,job,1)["state"]=="complete"
    finally:
        worker.join()
    with pytest.raises(ValueError):
        school.wait_job(store,job,30)


def test_unchanged_poll_does_not_repeat_payload(tmp_path):
    store=Store(tmp_path)
    job="f"*32
    stamp=now_utc().isoformat()
    school.write_json(school.job_path(store,job),dict(job_id=job,action="courses",state="running",updated_at=stamp))
    value=school.wait_job(store,job,0,stamp)
    assert value["unchanged"] and "result" not in value


def test_verified_cached_resource_read_never_starts_browser(tmp_path,monkeypatch):
    store=Store(tmp_path)
    key=capture(store)["inserted"][0]
    add_text(store,key)
    monkeypatch.setattr(school.subprocess,"Popen",lambda *a,**kw:pytest.fail("browser worker started"))
    value=school.start_job(store,"read_resource",{"item_id":key,"refresh":False})
    assert value["state"]=="complete" and value["browser_started"] is False
    assert value["result"]["live"] is False
    assert value["result"]["remote_freshness_checked"] is False


def test_warm_text_cache_still_detects_file_tampering(tmp_path):
    store=Store(tmp_path)
    key=capture(store)["inserted"][0]
    path=add_text(store,key)
    first=file_text.read_file(store,key,max_chars=500)
    second=file_text.read_file(store,key,offset=500,max_chars=500)
    assert first["text"].startswith("\n[text]\n")
    assert second["text_cache_hit"]
    path.write_text("tampered",encoding="utf-8")
    with pytest.raises(ValueError,match="differs"):
        file_text.read_file(store,key)


def test_teacher_workflows_are_not_claimed_as_verified(tmp_path,monkeypatch):
    monkeypatch.setattr(server,"store",lambda:Store(tmp_path))
    result=server.study_status(include_capabilities=True).structuredContent
    assert result["name"]=="UoE Companion"
    assert any("Teacher" in item for item in result["feature_status"]["unverified"])
    assert any("marking" in item for item in result["feature_status"]["not_implemented"])
