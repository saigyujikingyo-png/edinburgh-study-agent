from datetime import datetime, timedelta, timezone
import icalendar
import pytest
from pydantic import ValidationError
from edinburgh_study_agent.models import Item, Observation, now_utc, safe_url
from edinburgh_study_agent.store import Store, identifier
from edinburgh_study_agent.calendar_io import import_calendar, export_calendar
from edinburgh_study_agent.planner import build_plan

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "private-data")

def item(kind="resource", native_id="r1", title="Lecture notes", **extra):
    return Item(kind=kind, native_id=native_id, title=title, excerpt=title, **extra)

def observation(items=(), observed_at=None, **extra):
    return Observation(source="learn", source_url="https://www.learn.ed.ac.uk/ultra/course",
        title="Fixture page", observed_at=observed_at or now_utc(),
        scope="Synthetic isolated test", authentication="authenticated",
        text="\n".join(x.excerpt for x in items) or "No items in this visible scope.",
        items=list(items), **extra)

def test_capture_deduplicates_and_survives_reopen(store):
    obs = observation([item()])
    first = store.capture(obs)
    assert len(first["inserted"]) == 1
    assert store.capture(obs)["duplicate"]
    reopened = Store(store.root)
    found = reopened.list_items(query="lecture")
    assert found["total_matches"] == 1 and not found["live"]
    evidence = reopened.evidence(first["observation_id"])
    assert evidence["observation"]["text"] == "Lecture notes"

def test_newer_observation_wins_and_partial_does_not_delete(store):
    old = now_utc() - timedelta(days=2)
    store.capture(observation([item(title="Updated notes")]))
    store.capture(observation([item(title="Old notes")], observed_at=old))
    store.capture(observation([]))
    assert store.list_items()["items"][0]["title"] == "Updated notes"

def test_evidence_title_excerpt_and_auth_checked():
    with pytest.raises(ValidationError):
        observation([item()]).model_copy(update={"text": "Other text"}).model_validate(
            {**observation([item()]).model_dump(), "text": "Other text"})
    with pytest.raises(ValidationError):
        Observation(source="learn", source_url="https://www.learn.ed.ac.uk/",
            title="Login", observed_at=now_utc(), scope="login", text="Lecture notes",
            items=[item()], authentication="login_required")

@pytest.mark.parametrize("url", [
    "https://www.learn.ed.ac.uk.evil.example/",
    "https://www.myed.ed.ac.uk/",
])
def test_source_host_must_match(url):
    payload = observation().model_dump()
    payload["source_url"] = url
    with pytest.raises(ValidationError):
        Observation.model_validate(payload)

@pytest.mark.parametrize("url", [
    "http://www.learn.ed.ac.uk/", "https://user:pass@www.learn.ed.ac.uk/",
    "https://www.learn.ed.ac.uk/calendar?token=secret",
    "https://www.learn.ed.ac.uk/calendar?access_token=secret",
    "https://www.learn.ed.ac.uk/auth-saml/saml/login?apId=x",
    "https://www.learn.ed.ac.uk:9000/",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        safe_url(url)

def test_credentials_never_persist(store):
    payload = observation().model_dump()
    payload["text"] = "access_token=do-not-save"
    with pytest.raises(ValidationError):
        store.capture(Observation.model_validate(payload))
    assert store.status()["counts"] == {}

def test_missing_date_is_not_midnight_and_dst_boundary(store):
    records = [item("assignment", "a", "Unknown deadline"),
               item("assignment", "b", "Exact deadline", due_at="2026-10-25T00:30:00+01:00"),
               item("assignment", "c", "Day-only deadline", due_date="2026-10-25")]
    store.capture(observation(records))
    result = store.deadlines("2026-10-25", "2026-10-25")
    assert len(result["deadlines"]) == 2
    assert result["unknown_deadlines"][0]["title"] == "Unknown deadline"
    assert next(x for x in result["deadlines"] if x["native_id"] == "c")["due_at"] is None
    with pytest.raises(ValidationError):
        item("assignment", due_at="2026-10-25T09:00:00")

def test_dates_must_be_consistent():
    with pytest.raises(ValidationError):
        item("assignment", due_at="2026-10-25T09:00:00Z", due_date="2026-10-25")
    with pytest.raises(ValidationError):
        item("event", starts_at="2026-10-25T11:00:00Z", ends_at="2026-10-25T10:00:00Z")

def test_done_is_local_and_archive_is_reversible(store):
    captured = store.capture(observation([item("assignment", "a", "Report")]))
    task = store.create_task("Write report", 90, item_id=captured["inserted"][0])
    finished = store.update_task(task["id"], status="done")
    assert finished["university_submission_changed"] is False
    assert store.item(captured["inserted"][0])["status"] == "unknown"
    store.update_task(task["id"], status="archived")
    store.update_task(task["id"], status="todo")
    assert len(store.tasks("todo")["tasks"]) == 1

def test_plan_avoids_classes_and_respects_effort_capacity_and_deadline(store):
    store.capture(observation([item("event", "lab", "Lab",
        starts_at="2030-01-07T09:00:00Z", ends_at="2030-01-07T10:00:00Z")]))
    store.create_task("Urgent task", 90, due_at="2030-01-07T11:00:00Z")
    store.create_task("Long task", 180)
    plan = build_plan(store, "2030-01-07", days=1, daily_minutes=120,
        clock=datetime(2030, 1, 7, 8, tzinfo=timezone.utc))
    assert sum(b["minutes"] for b in plan["blocks"]) <= 120
    assert plan["unallocated"]
    for block in plan["blocks"]:
        start, end = datetime.fromisoformat(block["starts_at"]), datetime.fromisoformat(block["ends_at"])
        assert start.hour >= 10
        if block["title"] == "Urgent task":
            assert end <= datetime(2030, 1, 7, 11, tzinfo=timezone.utc)
    ordered = sorted(plan["blocks"], key=lambda b: b["starts_at"])
    for a, b in zip(ordered, ordered[1:]):
        assert datetime.fromisoformat(a["ends_at"]) <= datetime.fromisoformat(b["starts_at"])

def test_plan_uses_updated_linked_deadline(store):
    first = now_utc() - timedelta(minutes=1)
    captured = store.capture(observation([item("assignment", "a", "Report",
        due_at="2030-01-08T12:00:00Z")], observed_at=first))
    store.create_task("Report work", 60, item_id=captured["inserted"][0])
    store.capture(observation([item("assignment", "a", "Report", due_at="2030-01-07T08:00:00Z")]))
    plan = build_plan(store, "2030-01-07", clock=datetime(2030, 1, 7, 9, tzinfo=timezone.utc))
    assert not plan["blocks"]
    assert plan["unallocated"][0]["reason"] == "deadline_passed"

def test_date_only_deadline_is_conservative(store):
    store.create_task("Day-only task", 30, due_date="2030-01-07")
    plan = build_plan(store, "2030-01-07", clock=datetime(2030, 1, 7, 8, tzinfo=timezone.utc))
    assert plan["blocks"] == []

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Synthetic Tests//EN
BEGIN:VEVENT
UID:weekly-lab
DTSTART;TZID=Europe/London:20261018T090000
DTEND;TZID=Europe/London:20261018T100000
RRULE:FREQ=WEEKLY;COUNT=3
EXDATE;TZID=Europe/London:20261025T090000
SUMMARY:Weekly laboratory
DESCRIPTION:First line\\nSecond line
END:VEVENT
END:VCALENDAR
"""

def test_calendar_recurrence_exdates_dst_and_dedup(store, tmp_path):
    source = tmp_path / "test.ics"
    source.write_text(ICS)
    output = import_calendar(store, source, "timetable",
        "https://www.myed.ed.ac.uk/myed-progressive/timetables", "2026-10-01", "2026-11-05")
    assert output["imported_occurrences"] == 2
    events = sorted(store.list_items(kind="event")["items"], key=lambda x: x["starts_at"])
    assert events[0]["starts_at"].endswith("+01:00")
    assert datetime.fromisoformat(events[1]["starts_at"]).utcoffset() == timedelta(0)
    import_calendar(store, source, "timetable",
        "https://www.myed.ed.ac.uk/myed-progressive/timetables", "2026-10-01", "2026-11-05")
    assert store.list_items(kind="event")["total_matches"] == 2

def test_date_only_calendar_and_export_reopen(store, tmp_path):
    path = tmp_path / "deadline.ics"
    path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:day-only\n"
        "DTSTART;VALUE=DATE:20261025\nSUMMARY:Report due\nEND:VEVENT\nEND:VCALENDAR\n")
    import_calendar(store, path, "learn", "https://www.learn.ed.ac.uk/ultra/calendar",
                    "2026-10-01", "2026-10-31", "deadlines")
    observed = store.list_items(kind="assignment")["items"][0]
    assert observed["due_date"] == "2026-10-25" and observed["due_at"] is None
    output = export_calendar(store, "2026-10-01", "2026-10-31")
    reopened = icalendar.Calendar.from_ical(__import__("pathlib").Path(output["path"]).read_bytes())
    assert str(reopened.walk("VEVENT")[0]["SUMMARY"]) == "Report due"
    assert output["calendar_changed"] is False

def test_export_path_and_calendar_semantics_protected(store, tmp_path):
    with pytest.raises(ValueError):
        export_calendar(store, "2026-01-01", "2026-01-31", "../outside.ics")
    with pytest.raises(ValueError):
        import_calendar(store, tmp_path / "none.ics", "myed",
            "https://www.myed.ed.ac.uk/", "2026-01-01", "2026-01-31", "deadlines")

def test_login_observation_preserves_cache(store):
    store.capture(observation([item()]))
    payload = observation().model_dump()
    payload.update(authentication="login_required", text="Login to MyEd")
    store.capture(Observation.model_validate(payload))
    assert store.status()["last_observations"]["learn"]["authentication"] == "login_required"
    assert store.list_items()["total_matches"] == 1

def test_manual_task_deadline_is_not_overwritten_by_linked_item(store):
    captured = store.capture(observation([item("assignment", "a", "Report",
        due_at="2030-01-09T12:00:00Z")]))
    store.create_task("Self-imposed early milestone", 30, item_id=captured["inserted"][0],
                      due_at="2030-01-07T08:00:00Z")
    plan = build_plan(store, "2030-01-07", clock=datetime(2030, 1, 7, 9, tzinfo=timezone.utc))
    assert not plan["blocks"]
    assert plan["unallocated"][0]["reason"] == "deadline_passed"

def test_high_frequency_calendar_is_rejected_before_expansion(store, tmp_path):
    source = tmp_path / "dense.ics"
    source.write_text(ICS.replace("FREQ=WEEKLY;COUNT=3", "FREQ=SECONDLY;COUNT=999999999"))
    with pytest.raises(ValueError, match="daily-or-longer"):
        import_calendar(store, source, "learn", "https://www.learn.ed.ac.uk/ultra/calendar",
                        "2026-10-01", "2026-11-05")
    assert store.list_items()["total_matches"] == 0

def test_changed_recurring_instance_has_one_stable_identity(store, tmp_path):
    path = tmp_path / "rescheduled.ics"
    exception = """BEGIN:VEVENT
UID:weekly-lab
RECURRENCE-ID;TZID=Europe/London:20261101T090000
DTSTART;TZID=Europe/London:20261101T110000
DTEND;TZID=Europe/London:20261101T120000
SUMMARY:Rescheduled laboratory
END:VEVENT
"""
    path.write_text(ICS.replace("END:VCALENDAR", exception + "END:VCALENDAR"))
    import_calendar(store, path, "timetable", "https://www.myed.ed.ac.uk/myed-progressive/timetables",
                    "2026-10-01", "2026-11-05")
    events = store.list_items(kind="event")["items"]
    assert len(events) == 2
    moved = next(i for i in events if i["title"] == "Rescheduled laboratory")
    assert datetime.fromisoformat(moved["starts_at"]).hour == 11
