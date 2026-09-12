from __future__ import annotations
from datetime import date, datetime, time, timedelta
from .models import LONDON, now_utc

def subtract(intervals, busy):
    for bstart, bend in busy:
        result = []
        for start, end in intervals:
            if bend <= start or bstart >= end:
                result.append((start, end))
            else:
                if start < bstart:
                    result.append((start, bstart))
                if bend < end:
                    result.append((bend, end))
        intervals = result
    return intervals

def build_plan(store, start_date: str, days: int = 7, daily_minutes: int = 120,
               day_start: int = 9, day_end: int = 18, block_minutes: int = 50,
               clock: datetime | None = None) -> dict:
    first = date.fromisoformat(start_date)
    if not 1 <= days <= 31 or not 5 <= daily_minutes <= 600:
        raise ValueError("days must be 1..31; daily_minutes must be 5..600.")
    if not 0 <= day_start < day_end <= 24 or not 5 <= block_minutes <= 120:
        raise ValueError("Use an ordered hour range 0..24 and block_minutes 5..120.")
    clock = (clock or now_utc()).astimezone(LONDON)
    if first < clock.date():
        raise ValueError("A study plan cannot start in the past.")
    tasks = [t for t in store.tasks()["tasks"] if t["status"] in ("todo", "doing")]
    from .agenda import window
    events = window(store, start_date, (first+timedelta(days=days-1)).isoformat(), kind="event")
    if events["truncated"]:
        raise ValueError("More than 500 events in this planning window; choose fewer days.")
    busy = []
    for item in events["items"]:
        if item["status"] != "cancelled" and item["starts_at"] and item["ends_at"]:
            busy.append((datetime.fromisoformat(item["starts_at"]).astimezone(LONDON),
                         datetime.fromisoformat(item["ends_at"]).astimezone(LONDON)))
    # A linked deadline may have changed since task creation.
    for task in tasks:
        if task["item_id"] and task.get("deadline_mode") == "linked":
            item = store.item(task["item_id"])
            task["due_at"], task["due_date"] = item["due_at"], item["due_date"]

    def cutoff(task):
        if task["due_at"]:
            return datetime.fromisoformat(task["due_at"]).astimezone(LONDON)
        if task["due_date"]:
            return datetime.combine(date.fromisoformat(task["due_date"]), time(), LONDON)
        return datetime.max.replace(tzinfo=LONDON)

    tasks.sort(key=lambda t: (cutoff(t), -t["priority"], t["created_at"]))
    left = {t["id"]: t["estimate_minutes"] for t in tasks}
    blocks = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        begin = max(datetime.combine(day, time(day_start), LONDON), clock)
        finish = (datetime.combine(day + timedelta(days=1), time(), LONDON) if day_end == 24
                  else datetime.combine(day, time(day_end), LONDON))
        # Start on a whole minute, never before now.
        if begin.second or begin.microsecond:
            begin = begin.replace(second=0, microsecond=0) + timedelta(minutes=1)
        remaining = daily_minutes
        for free_start, free_end in subtract([(begin, finish)] if begin < finish else [], busy):
            cursor = free_start
            for task in tasks:
                latest = min(free_end, cutoff(task))
                while left[task["id"]] and remaining and cursor < latest:
                    available = int((latest - cursor).total_seconds() // 60)
                    duration = min(available, left[task["id"]], remaining, block_minutes)
                    if duration < 5:
                        break
                    end = cursor + timedelta(minutes=duration)
                    blocks.append({"task_id": task["id"], "title": task["title"],
                                   "starts_at": cursor.isoformat(), "ends_at": end.isoformat(),
                                   "minutes": duration, "item_id": task["item_id"]})
                    left[task["id"]] -= duration
                    remaining -= duration
                    cursor = end + timedelta(minutes=10)
    unallocated = [{"task_id": t["id"], "title": t["title"], "remaining_minutes": left[t["id"]],
                    "reason": "deadline_passed" if cutoff(t) <= clock else "insufficient_time_before_deadline"}
                   for t in tasks if left[t["id"]]]
    assignments = store.list_items(kind="assignment", limit=500)
    linked = {t["item_id"] for t in tasks}
    return {"blocks": blocks, "unallocated": unallocated, "timezone": "Europe/London", "draft": True,
            "calendar_changed": False,
            "assignments_without_active_tasks": [i for i in assignments["items"] if i["id"] not in linked],
            "assumptions": [f"{daily_minutes} study minutes per day between {day_start}:00 and {day_end}:00.",
                            "10-minute breaks after blocks; only cached timetable events are excluded.",
                            "Date-only deadlines are conservatively treated as the START of that day.",
                            "Unknown effort is never inferred: create tasks with explicit time estimates."],
            "coverage": "cached_observations_only",
            "warning": "A fresh MyEd/Timetabler calendar is needed to establish real availability."}
