"""Small private persistent caches shared by repeated agent requests."""
from __future__ import annotations
import json
from datetime import datetime
from .models import now_utc

MAX_BYTES=2_100_000
MAX_ENTRIES=16


def put(store, namespace, key, value):
    payload=json.dumps(value,ensure_ascii=False,separators=(",",":"))
    if len(payload.encode())>MAX_BYTES:
        return False
    with store.connection() as db:
        db.execute("CREATE TABLE IF NOT EXISTS workflow_cache (namespace TEXT,cache_key TEXT,stamp TEXT,payload TEXT,PRIMARY KEY(namespace,cache_key))")
        db.execute("INSERT OR REPLACE INTO workflow_cache VALUES(?,?,?,?)",(namespace,key,now_utc().isoformat(),payload))
        db.execute("DELETE FROM workflow_cache WHERE namespace=? AND cache_key NOT IN (SELECT cache_key FROM workflow_cache WHERE namespace=? ORDER BY stamp DESC LIMIT ?)",(namespace,namespace,MAX_ENTRIES))
    return True


def get(store, namespace, key, ttl):
    with store.connection() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_cache'").fetchone():
            return None
        row=db.execute("SELECT stamp,payload FROM workflow_cache WHERE namespace=? AND cache_key=?",(namespace,key)).fetchone()
    if not row:
        return None
    age=(now_utc()-datetime.fromisoformat(row["stamp"])).total_seconds()
    if not 0<=age<ttl:
        return None
    return json.loads(row["payload"])


def invalidate(store):
    with store.connection() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_cache'").fetchone():
            db.execute("DELETE FROM workflow_cache")
