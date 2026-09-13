from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sys
import icalendar
import pytest
import yaml
from edinburgh_study_agent import agenda, hosts, localization, services
from edinburgh_study_agent.store import Store
from edinburgh_study_agent.planner import build_plan
from edinburgh_study_agent.calendar_io import export_calendar
from test_workflows import item, observation

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/"campus")

def test_preferences_persist_across_hosts_without_lost_fields(store):
    def set_language():
        localization.preferences(Store(store.root),locale="zh_TW")
    def set_zone():
        localization.preferences(Store(store.root),display_timezone="Asia/Tokyo")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(set_language),pool.submit(set_zone)]
        for future in futures:
            future.result()
    settings=localization.preferences(Store(store.root))
    assert settings["preferences"]["locale"]=="zh-TW"
    assert settings["presentation"]["catalog_language"]=="zh-Hant"
    assert settings["preferences"]["display_timezone"]=="Asia/Tokyo"
    override=services.directory(store,"bibliotheque",locale="fr-CA")
    assert [s["id"] for s in override["services"]]==["library"]
    assert override["services"][0]["title"]=="Bibliothèque"
    assert localization.preferences(store)["preferences"]==settings["preferences"]

def test_locale_fallback_and_rtl_do_not_translate_evidence(store):
    store.capture(observation([item(title="Original English course material")]))
    localization.preferences(store,locale="ar",display_timezone="Europe/London")
    catalog=services.directory(store,"المكتبة")
    assert catalog["presentation"]["direction"]=="rtl"
    assert catalog["services"][0]["official_name"]=="Library"
    assert catalog["services"][0]["id"]=="library"
    assert store.list_items()["items"][0]["title"]=="Original English course material"
    fallback=localization.presentation(store,locale="sw-KE")
    assert fallback["response_language"]=="sw-KE" and fallback["catalog_fallback"]
    assert fallback["catalog_language"]=="en-GB"
    assert len(localization.LANGUAGES)==10

@pytest.mark.parametrize("kwargs",[{"locale":"../../fr"},{"display_timezone":"Mars/Olympus"},
                                    {"locale":""},{"bilingual_titles":"false"}])
def test_invalid_preferences_are_atomic(store,kwargs):
    with pytest.raises(ValueError):
        localization.preferences(store,**kwargs)
    assert store.preferences()=={}

def test_agenda_dst_overlap_date_only_and_linked_deadline(store):
    records=[item("event","overlap","Overnight lab",starts_at="2030-10-26T23:30:00+01:00",ends_at="2030-10-27T01:30:00+00:00"),
             item("assignment","day","Date only",due_date="2030-10-27"),
             item("assignment","exact","Exact due",due_at="2030-10-27T00:30:00+01:00"),
             item("assignment","unknown","Unknown date"),
             item("event","out","Outside",starts_at="2030-10-28T00:00:00Z",ends_at="2030-10-28T01:00:00Z")]
    captured=store.capture(observation(records))
    task=store.create_task("Prepare",30,item_id=captured["inserted"][2])
    store.create_task("Finished",10,due_date="2030-10-27")
    completed=next(t for t in store.tasks()["tasks"] if t["title"]=="Finished")
    store.update_task(completed["id"],status="done")
    result=agenda.agenda(store,"2030-10-27","2030-10-27",display_timezone="America/New_York")
    assert result["total_matches"]==5 and result["unknown_dates"]==1
    day=next(x for x in result["items"] if x["title"]=="Date only")
    assert day["due_date"]=="2030-10-27" and day["timing"]=="date_only"
    assert not day.get("display_due_at")
    exact=next(x for x in result["items"] if x["title"]=="Exact due")
    assert exact["display_due_at"]=="2030-10-26T19:30:00-04:00"
    assert exact["due_at"]=="2030-10-27T00:30:00+01:00"
    assert any(x["title"]=="Overnight lab" for x in result["items"])
    store.capture(observation([item("assignment","exact","Exact due",due_date="2030-10-28")]))
    updated=agenda.agenda(store,"2030-10-28","2030-10-28")
    linked=next(x for x in updated["items"] if x["id"]==task["id"])
    assert linked["due_date"]=="2030-10-28" and linked["due_at"] is None
    assert store.tasks()["tasks"][0]["due_at"] is not None  # read-only projection, no task rewrite

def test_agenda_filters_before_pagination_and_planning(store):
    for batch in range(3):
        store.capture(observation([item("resource",f"r{batch}-{n}",f"Resource {batch}-{n}") for n in range(250)]))
        store.capture(observation([item("event",f"old{batch}-{n}",f"Old event {batch}-{n}",
            starts_at="2025-01-01T09:00:00Z",ends_at="2025-01-01T10:00:00Z") for n in range(200)]))
    store.capture(observation([item("event",f"current{n}",f"Class {n}",
        starts_at=f"2030-01-07T{9+n:02d}:00:00Z",ends_at=f"2030-01-07T{10+n}:00:00Z") for n in range(3)]))
    store.create_task("Work",45,due_date="2030-01-08")
    first=agenda.agenda(store,"2030-01-07","2030-01-08",limit=2)
    second=agenda.agenda(store,"2030-01-07","2030-01-08",limit=2,offset=first["next_offset"])
    assert first["total_matches"]==4 and second["next_offset"] is None
    assert len({x["id"] for x in first["items"]+second["items"]})==4
    past=agenda.agenda(store,"2030-01-07","2030-01-08",offset=100)
    assert past["total_matches"]==4 and past["items"]==[]
    plan=build_plan(store,"2030-01-07",days=1,clock=datetime(2030,1,7,8,tzinfo=timezone.utc))
    assert plan["blocks"] and all(datetime.fromisoformat(x["starts_at"]).hour>=12 for x in plan["blocks"])
    receipt=export_calendar(store,"2030-01-07","2030-01-08")
    assert receipt["events"]==3
    from pathlib import Path
    calendar=icalendar.Calendar.from_ical(Path(receipt["path"]).read_bytes())
    assert len(calendar.walk("VEVENT"))==3

def test_host_merge_preserves_existing_settings_and_is_idempotent(tmp_path):
    target=tmp_path/"mcp.json"
    original={"mcpServers":{"existing":{"command":"other","env":{"EXAMPLE_SETTING":"keep"}},
        "edinburgh-study":{"command":"old-python","args":["-m",hosts.MODULE],"disabled":True,"env":{"CUSTOM_OPTION":"keep"}}},
        "theme":"dark"}
    target.write_text(json.dumps(original),encoding="utf-8")
    config=hosts.server_config(sys.executable,tmp_path/"private data",locale="fr")
    receipt=hosts.merge_config(target,config)
    merged=json.loads(target.read_text(encoding="utf-8"))
    assert merged["theme"]=="dark" and merged["mcpServers"]["existing"]==original["mcpServers"]["existing"]
    assert receipt["server_name"]=="edinburgh-study" and merged["mcpServers"]["edinburgh-study"]["disabled"]
    from pathlib import Path
    assert json.loads(Path(receipt["backup"]).read_text(encoding="utf-8"))==original
    assert not hosts.merge_config(target,config)["changed"]
    assert len(list(tmp_path.glob("*.bak")))==1

def test_host_conflict_invalid_json_and_generation_do_not_overwrite(tmp_path):
    target=tmp_path/"mcp.json"
    config=hosts.server_config(sys.executable,tmp_path/"private")
    for content in ('not-json','{"mcpServers":{"uoe-companion":{"command":"unrelated"}}}'):
        target.write_text(content,encoding="utf-8")
        with pytest.raises(ValueError):
            hosts.merge_config(target,config)
        assert target.read_text(encoding="utf-8")==content
    folder=tmp_path/"bundle"
    receipt=hosts.generate(folder,config)
    assert len(receipt["generated"])==6
    deepseek=yaml.safe_load((folder/"deepseek-harness.yaml").read_text(encoding="utf-8"))
    bridge=deepseek[0]["insert"][0]
    assert bridge["name"]=="@deepseek-ai/dsh-mcp-client"
    assert bridge["config"]["transport"]=="stdio"
    assert bridge["config"]["args"]==["-m",hosts.MODULE]
    with pytest.raises(ValueError):
        hosts.generate(folder,config)

def test_mcp_student_profile_tools_and_language_roundtrip(store):
    config=hosts.server_config(sys.executable,store.root)
    checked=hosts.doctor(config)
    assert checked["tools"]==33 and checked["host_model_roundtrip"]=="not_tested"


def test_portable_catalog_retains_runtime_validation(store,monkeypatch):
    import asyncio
    from edinburgh_study_agent import server
    from edinburgh_study_agent.protocol import portable_schema
    monkeypatch.setattr(server,"store",lambda:store)
    catalog=asyncio.run(server.mcp.list_tools())
    assert all("anyOf" not in json.dumps(t.inputSchema) and "$ref" not in json.dumps(t.inputSchema) for t in catalog)
    estimate=next(t for t in catalog if t.name=="study_task_create").inputSchema["properties"]["estimate_minutes"]
    assert "minimum=5" in estimate["description"]
    assert "title" not in estimate
    with pytest.raises(ValueError):
        server.study_task_create("Too short",1)
    with pytest.raises(ValueError):
        portable_schema({"anyOf":[{"type":"number"},{"type":"integer"}]})
    with pytest.raises(ValueError):
        portable_schema({"$defs":{"x":{"$ref":"#/$defs/x"}},"$ref":"#/$defs/x"})


def test_claude_cli_argument_boundary_and_batch_refusal(tmp_path,monkeypatch):
    captured=[]
    monkeypatch.setattr(hosts.shutil,"which",lambda name:str(tmp_path/"claude.exe"))
    monkeypatch.setattr(hosts.subprocess,"run",lambda argv,**options:captured.append((argv,options)))
    private=tmp_path/"spaces & shell metacharacters"
    monkeypatch.setattr(sys,"argv",["hosts","install","--host","claude-code","--home",str(private)])
    hosts.main()
    argv,options=captured[0]
    assert options["shell"] is False
    assert json.loads(argv[-1])["env"]["EDINBURGH_STUDY_HOME"]==str(private.resolve())
    assert argv[1:6]==["mcp","add-json","--scope","user","uoe-companion"]
    monkeypatch.setattr(hosts.shutil,"which",lambda name:str(tmp_path/"claude.cmd"))
    with pytest.raises(SystemExit):
        hosts.main()
    assert len(captured)==1

def test_agenda_sql_inputs_and_empty_count_row(store):
    empty=agenda.window(store,"2030-01-01","2030-01-07",include_unknown=True,offset=50)
    assert empty["total_matches"]==0 and empty["items"]==[] and empty["next_offset"] is None
    with pytest.raises(ValueError):
        agenda.window(store,"2030-01-01' OR 1=1 --","2030-01-07")
    with pytest.raises(ValueError):
        agenda.window(store,"2030-01-01","2030-01-07",kind="event' OR 1=1 --")
    assert store.status()["counts"]=={}
