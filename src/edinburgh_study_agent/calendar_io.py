from __future__ import annotations
import hashlib
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
import icalendar
import recurring_ical_events
from .models import Item, Observation, LONDON, now_utc, safe_url

def bounds(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 <= (b - a).days <= 366:
        raise ValueError("Calendar import/export range must be 0..366 days.")
    return datetime.combine(a, time(), LONDON), datetime.combine(b + timedelta(days=1), time(), LONDON)

def as_time(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=LONDON) if value.tzinfo is None else value
    return datetime.combine(value, time(), LONDON)

def import_calendar(store, file_path, source, source_url, start, end, semantics="events"):
    if semantics not in ("events", "deadlines"):
        raise ValueError("semantics must be events or deadlines.")
    if semantics == "deadlines" and source != "learn":
        raise ValueError("Use deadlines only for a Learn due-date calendar, not a timetable.")
    path = Path(file_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".ics":
        raise ValueError("Provide an existing exported .ics calendar file.")
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Calendar file exceeds the 5 MiB import limit.")
    first, stop = bounds(start, end)
    data = path.read_bytes()
    calendar = icalendar.Calendar.from_ical(data)
    if calendar.name != "VCALENDAR":
        raise ValueError("Expected VCALENDAR.")
    if len(calendar.walk("VEVENT")) > 5000:
        raise ValueError("Too many calendar components.")
    for component in calendar.walk("VEVENT"):
        rule = component.get("RRULE")
        if rule:
            frequency = str(rule.get("FREQ", [""])[0])
            if frequency not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}:
                raise ValueError("Only daily-or-longer recurrence is supported for study calendars.")
            if rule.get("BYSECOND") or len(rule.get("BYMINUTE", [])) > 1 or len(rule.get("BYHOUR", [])) > 1:
                raise ValueError("Sub-hourly recurrence expansion is not supported.")
    expanded = recurring_ical_events.of(calendar).between(first, stop)
    if len(expanded) > 500:
        raise ValueError("More than 500 events in this window; choose a shorter range.")
    digest = hashlib.sha256(data).hexdigest()
    feed_key = hashlib.sha256(source_url.encode()).hexdigest()[:12]
    items, excerpts, warnings = [], [], []
    for event in expanded:
        start_value = event.decoded("DTSTART", None)
        if start_value is None:
            raise ValueError("A calendar event lacks DTSTART.")
        uid = str(event.get("UID", "")).strip()
        if not uid:
            raise ValueError("A calendar event lacks UID; stable import is not possible.")
        start_time = as_time(start_value)
        end_value = event.decoded("DTEND", None)
        duration = event.decoded("DURATION", None)
        if end_value is not None:
            end_time = as_time(end_value)
        elif duration:
            end_time = start_time + duration
        elif isinstance(start_value, datetime):
            end_time = None
            warnings.append("An event has no duration; it will not block timetable availability.")
        else:
            end_time = start_time + timedelta(days=1)
        title = str(event.get("SUMMARY", "")).strip() or "Untitled calendar event"
        description = str(event.get("DESCRIPTION", ""))[:2000]
        recurrence_id = event.decoded("RECURRENCE-ID", start_value)
        occurrence = as_time(recurrence_id).isoformat()
        native = f"ical:{feed_key}:" + hashlib.sha256(f"{uid}|{occurrence}".encode()).hexdigest()[:32]
        excerpt = f"{title}\n{start_time.isoformat()}\n{description}".strip()
        excerpts.append(excerpt)
        url = str(event.get("URL", "")).strip() or None
        if url:
            try:
                safe_url(url)
            except ValueError:
                url = None
                warnings.append("A credential-bearing or non-HTTPS event URL was omitted.")
        fields = {"native_id": native, "kind": "assignment" if semantics == "deadlines" else "event",
                  "title": title, "url": url, "excerpt": excerpt,
                  "status": "cancelled" if str(event.get("STATUS", "")).upper() == "CANCELLED" else "unknown"}
        if semantics == "deadlines":
            if isinstance(start_value, datetime):
                fields["due_at"] = start_time
            else:
                fields["due_date"] = start_value.isoformat()
        else:
            fields.update(starts_at=start_time, ends_at=end_time)
        items.append(Item(**fields))
    observation = Observation(source=source, source_url=source_url, title="Imported calendar export",
            observed_at=now_utc(), scope=f"calendar-file:{digest}; {start}..{end}; {semantics}",
            coverage="complete_visible_scope", authentication="unknown",
            text="\n\n".join(excerpts) or "No VEVENT occurrences in the supplied file and selected window.",
            items=items)
    result = store.capture(observation)
    result.update(file_sha256=digest, imported_occurrences=len(items),
                  warnings=list(dict.fromkeys(warnings)),
                  note="Local export, not live sync. Floating times use Europe/London. Missing old items are retained.")
    return result

def export_calendar(store, start, end, filename="edinburgh-study.ics"):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}\.ics", filename):
        raise ValueError("Use a simple .ics filename, without directories.")
    first, stop = bounds(start, end)
    calendar = icalendar.Calendar()
    calendar.add("prodid", "-//UoE Companion//EN")
    calendar.add("version", "2.0")
    calendar.add("x-wr-calname", "Edinburgh study - observed deadlines and events")
    from .agenda import window
    items = window(store, start, end)
    if items["truncated"]:
        raise ValueError("Export supports up to 500 events/deadlines in this date range; choose a shorter range.")
    count = 0
    for item in items["items"]:
        if item["kind"] not in ("event", "assignment") or item["status"] == "cancelled":
            continue
        value = item.get("due_at") or item.get("starts_at") or item.get("due_date")
        if not value:
            continue
        timestamp = datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
        point = as_time(timestamp)
        if not first <= point < stop and not (item["kind"] == "event" and item.get("ends_at") and first < datetime.fromisoformat(item["ends_at"]) and point < stop):
            continue
        event = icalendar.Event()
        event.add("uid", item["id"] + "@edinburgh-study-agent.local")
        event.add("dtstamp", now_utc())
        event.add("summary", item["title"])
        event.add("dtstart", timestamp)
        if item["kind"] == "event" and item.get("ends_at"):
            event.add("dtend", datetime.fromisoformat(item["ends_at"]))
        if item["url"]:
            event.add("url", item["url"])
        event.add("description", "Observed: " + item["observed_at"] + "\n" + item["excerpt"])
        calendar.add_component(event)
        count += 1
    folder = store.root / "exports"
    folder.mkdir(exist_ok=True)
    destination = folder / filename
    # Do not overwrite a user's prior export.
    if destination.exists():
        destination = folder / (Path(filename).stem + "-" + now_utc().strftime("%Y%m%dT%H%M%S%f") + ".ics")
    content = calendar.to_ical()
    destination.write_bytes(content)
    return {"path": str(destination), "events": count, "sha256": hashlib.sha256(content).hexdigest(),
            "calendar_changed": False, "note": "A local file was created. No external calendar was changed."}
