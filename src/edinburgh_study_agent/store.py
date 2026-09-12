from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from .models import Observation, clean_text, normal, now_utc, aware

def identifier(source: str, kind: str, native_id: str) -> str:
    return hashlib.sha256(f"{source}\0{kind}\0{native_id}".encode()).hexdigest()[:24]

class Store:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.environ.get("EDINBURGH_STUDY_HOME", Path.home() / ".edinburgh-study-agent"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "study.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                  id TEXT PRIMARY KEY, source TEXT NOT NULL, scope TEXT NOT NULL,
                  observed_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS items (
                  id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
                  native_id TEXT NOT NULL, course_id TEXT, title TEXT NOT NULL,
                  observed_at TEXT NOT NULL, observation_id TEXT NOT NULL,
                  payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS items_kind_course ON items(kind, course_id);
                CREATE TABLE IF NOT EXISTS downloads (
                  item_id TEXT NOT NULL, sha256 TEXT NOT NULL, downloaded_at TEXT NOT NULL,
                  payload TEXT NOT NULL, PRIMARY KEY(item_id,sha256));
                CREATE TABLE IF NOT EXISTS service_checks (
                  service_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS collections (
                  id TEXT PRIMARY KEY, item_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                  seq INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL,
                  object_id TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def audit(db, action, object_id):
        db.execute("INSERT INTO audit(at,action,object_id) VALUES(?,?,?)",
                   (now_utc().isoformat(), action, object_id))

    def capture(self, observation: Observation) -> dict:
        payload = observation.model_dump(mode="json")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        obs_id = hashlib.sha256(encoded.encode()).hexdigest()
        inserted, updated, older = [], [], []
        with self.connection() as db:
            duplicate = db.execute("SELECT 1 FROM observations WHERE id=?", (obs_id,)).fetchone()
            if duplicate:
                return {"observation_id": obs_id, "duplicate": True, "inserted": [], "updated": []}
            db.execute("INSERT INTO observations VALUES(?,?,?,?,?)",
                       (obs_id, observation.source, observation.scope, observation.observed_at.isoformat(), encoded))
            for item in observation.items:
                key = identifier(observation.source, item.kind, item.native_id)
                previous = db.execute("SELECT observed_at FROM items WHERE id=?", (key,)).fetchone()
                if previous and datetime.fromisoformat(previous["observed_at"]) > observation.observed_at:
                    older.append(key)
                    continue
                db.execute("""INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET course_id=excluded.course_id,
                    title=excluded.title, observed_at=excluded.observed_at,
                    observation_id=excluded.observation_id, payload=excluded.payload""",
                    (key, observation.source, item.kind, item.native_id, item.course_id, item.title,
                     observation.observed_at.isoformat(), obs_id, item.model_dump_json()))
                (updated if previous else inserted).append(key)
            self.audit(db, "capture", obs_id)
        return {"observation_id": obs_id, "duplicate": False, "inserted": inserted,
                "updated": updated, "older_items_ignored": older, "coverage": observation.coverage,
                "note": "Capture is a dated browser observation. Absent items are never deleted."}

    def _row(self, row) -> dict:
        item = json.loads(row["payload"])
        item.setdefault("service_id",None)
        item.update(id=row["id"], source=row["source"], observed_at=row["observed_at"],
                    observation_id=row["observation_id"])
        age = (now_utc() - datetime.fromisoformat(row["observed_at"])).total_seconds()
        item["age_hours"] = round(max(0, age) / 3600, 2)
        item["needs_refresh"] = age > 86400
        return item

    def list_items(self, kind=None, course_id=None, query="", limit=100) -> dict:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be 1..500.")
        clauses, params = [], []
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        if course_id:
            clauses.append("course_id=?")
            params.append(course_id)
        sql = "SELECT * FROM items" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        with self.connection() as db:
            rows = db.execute(sql + " ORDER BY observed_at DESC", params).fetchall()
        needle = normal(query)
        matches = [self._row(r) for r in rows if not needle or needle in normal(r["payload"])]
        return {"items": matches[:limit], "total_matches": len(matches), "truncated": len(matches) > limit,
                "live": False, "coverage": "cached_observations_only",
                "note": "No matches means not observed in this cache, not absent from the University."}

    def item(self, key) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM items WHERE id=?", (key,)).fetchone()
        if row is None:
            raise ValueError("Unknown item_id. Find it with study_search first.")
        return self._row(row)

    def evidence(self, observation_id) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM observations WHERE id=?", (observation_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown observation_id.")
        return {"observation": json.loads(row["payload"]), "content_is_untrusted": True}

    def status(self) -> dict:
        with self.connection() as db:
            counts = {r["kind"]: r["n"] for r in db.execute("SELECT kind,COUNT(*) n FROM items GROUP BY kind")}
            observations = [json.loads(r["payload"]) for r in
                            db.execute("SELECT payload FROM observations ORDER BY observed_at DESC")]
            task_count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        latest = {}
        for obs in observations:
            source = obs["source"]
            if source not in latest or datetime.fromisoformat(obs["observed_at"]) > datetime.fromisoformat(latest[source]["observed_at"]):
                latest[source] = {k: obs[k] for k in
                                  ("source_url", "observed_at", "scope", "coverage", "authentication")}
        return {"version": "0.3.0", "transport": "stdio", "browser": "plugin_owned_persistent_campus_session",
                "data_directory": str(self.root), "counts": counts, "tasks": task_count,
                "last_observations": latest, "live_connection_checked": False,
                "capabilities": ["plugin-owned live DOM course/resource discovery", "evidence cache", "local tasks",
                                 "bounded calendar import", "conflict-aware draft study plan", "calendar export", "direct verified file downloads", "central school service directory", "cross-service collections", "bounded PDF and Office text reading"],
                "unsupported": ["scheduled automatic refresh", "direct Blackboard REST integration",
                                "server-side assignment submission", "remote calendar writes"],
                "privacy": "The dedicated browser manages its own local campus profile. Credentials and cookies are never exported to the agent. No inbound network listener."}

    def create_task(self, title: str, estimate_minutes: int, item_id=None, due_at=None,
                    due_date=None, priority=3, notes="") -> dict:
        from datetime import date
        title, notes = clean_text(title.strip()), clean_text(notes)
        if not title or len(title) > 500 or len(notes) > 4000:
            raise ValueError("A title (1..500 characters) and notes up to 4000 characters are required.")
        if not isinstance(estimate_minutes, int) or not 5 <= estimate_minutes <= 6000:
            raise ValueError("estimate_minutes must be 5..6000.")
        if not 1 <= priority <= 5:
            raise ValueError("priority must be 1..5 (5 is highest).")
        linked = self.item(item_id) if item_id else None
        deadline_mode = "linked" if linked and due_at is None and due_date is None else "manual"
        if due_at is None and due_date is None and linked:
            due_at, due_date = linked.get("due_at"), linked.get("due_date")
        if due_at:
            due_at = aware(datetime.fromisoformat(due_at)).isoformat()
        if due_date:
            due_date = date.fromisoformat(due_date).isoformat()
        if due_at and due_date:
            raise ValueError("Choose an exact due_at or a date-only due_date.")
        task = {"id": uuid.uuid4().hex[:24], "title": title, "estimate_minutes": estimate_minutes,
                "item_id": item_id, "deadline_mode": deadline_mode, "due_at": due_at, "due_date": due_date, "priority": priority,
                "notes": notes, "status": "todo", "created_at": now_utc().isoformat(),
                "updated_at": now_utc().isoformat(), "local_only": True}
        with self.connection() as db:
            db.execute("INSERT INTO tasks VALUES(?,?)", (task["id"], json.dumps(task, ensure_ascii=False)))
            self.audit(db, "create_task", task["id"])
        return task

    def tasks(self, status=None) -> dict:
        if status not in (None, "todo", "doing", "done", "archived"):
            raise ValueError("Unknown task status.")
        with self.connection() as db:
            tasks = [json.loads(r["payload"]) for r in db.execute("SELECT payload FROM tasks ORDER BY rowid")]
        return {"tasks": [t for t in tasks if status is None or t["status"] == status], "local_only": True}

    def update_task(self, task_id, status=None, estimate_minutes=None, notes=None) -> dict:
        if status not in (None, "todo", "doing", "done", "archived"):
            raise ValueError("Unknown task status.")
        if estimate_minutes is not None and not 5 <= estimate_minutes <= 6000:
            raise ValueError("estimate_minutes must be 5..6000.")
        if notes is not None and len(clean_text(notes)) > 4000:
            raise ValueError("Notes too long.")
        with self.connection() as db:
            row = db.execute("SELECT payload FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown task_id.")
            task = json.loads(row["payload"])
            for field, value in (("status", status), ("estimate_minutes", estimate_minutes), ("notes", notes)):
                if value is not None:
                    task[field] = value
            task["updated_at"] = now_utc().isoformat()
            db.execute("UPDATE tasks SET payload=? WHERE id=?", (json.dumps(task, ensure_ascii=False), task_id))
            self.audit(db, "update_task", task_id)
        return {"task": task, "university_submission_changed": False}

    def deadlines(self, start: str, end: str) -> dict:
        from datetime import date
        from .models import LONDON
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if not 0 <= (last - first).days <= 366:
            raise ValueError("Use a date range of 0..366 days.")
        known, unknown = [], []
        with self.connection() as db:
            rows = db.execute("SELECT * FROM items WHERE kind='assignment'").fetchall()
        for row in rows:
            item = self._row(row)
            if item["status"] == "cancelled":
                continue
            if item["due_at"]:
                day = datetime.fromisoformat(item["due_at"]).astimezone(LONDON).date()
            elif item["due_date"]:
                day = date.fromisoformat(item["due_date"])
            else:
                unknown.append(item)
                continue
            if first <= day <= last:
                known.append(item)
        known.sort(key=lambda i: i["due_at"] or i["due_date"])
        return {"deadlines": known, "unknown_deadlines": unknown, "timezone": "Europe/London",
                "live": False, "coverage": "cached_observations_only",
                "range": {"start": start, "end_inclusive": end},
                "warning": "Refresh Learn Calendar and assessment pages before relying on absence or changes."}
