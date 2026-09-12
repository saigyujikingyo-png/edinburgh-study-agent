"""Local collections connect school pages, course files and study tasks."""
import json
from .models import clean_text, now_utc
from .store import identifier
from .services import directory

def collect(store, item_id: str, collection: str = "Inbox", tags: list[str] | None = None,
            notes: str = "", archived: bool = False) -> dict:
    item = store.item(item_id)
    collection = clean_text(collection.strip())
    tags = sorted(set(clean_text(t.strip()) for t in (tags or []) if t.strip()))
    if not 1 <= len(collection) <= 100 or len(tags)>20 or any(len(t)>60 for t in tags) or len(clean_text(notes))>4000:
        raise ValueError("Collection 1..100 characters; up to 20 tags of 60 characters; notes up to 4000.")
    key=identifier("collection",collection,item_id)
    record={"id":key,"item_id":item_id,"collection":collection,"tags":tags,"notes":notes,
            "archived":archived,"updated_at":now_utc().isoformat(),"local_only":True}
    with store.connection() as db:
        db.execute("INSERT OR REPLACE INTO collections VALUES(?,?,?)",(key,item_id,json.dumps(record,ensure_ascii=False)))
        store.audit(db,"collect_item",key)
    return {"collection_entry":record,"item":item,"university_record_changed":False}

def collections(store, query: str = "", collection: str | None = None,
                include_archived: bool = False, limit: int = 50, offset: int = 0) -> dict:
    if not 1<=limit<=200 or not 0<=offset<=1000000:
        raise ValueError("limit 1..200; offset 0..1000000.")
    with store.connection() as db:
        rows=db.execute("SELECT i.*,c.payload AS collection_payload FROM collections c "
                        "JOIN items i ON i.id=c.item_id ORDER BY c.rowid DESC").fetchall()
    result=[]
    for row in rows:
        record=json.loads(row["collection_payload"])
        if (record["archived"] and not include_archived) or (collection is not None and record["collection"]!=collection):
            continue
        item=store._row(row)
        if query and query.casefold() not in json.dumps([record,item],ensure_ascii=False).casefold():
            continue
        result.append({**record,"item":item})
    entries=result[offset:offset+limit]
    return {"entries":entries,"total_matches":len(result),"truncated":offset+len(entries)<len(result),
            "offset":offset,"next_offset":offset+len(entries) if offset+len(entries)<len(result) else None,
            "local_only":True}


def home(store) -> dict:
    with store.connection() as db:
        downloads=db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        grouped=[dict(r) for r in db.execute("SELECT source,kind,COUNT(*) count FROM items GROUP BY source,kind")]
    saved=collections(store,limit=10)
    tasks=[t for t in store.tasks()["tasks"] if t["status"] in ("todo","doing")]
    service_rows=[{k:s[k] for k in ("id","title","official_name","category","url","coverage","last_check")}
                  for s in directory(store)["services"]]
    return {"name":"UoE Companion","services":service_rows,"indexed_items":grouped,"download_count":downloads,
            "tasks":tasks[:10],"task_count":len(tasks),"tasks_truncated":len(tasks)>10,
            "collections":saved["entries"],"collection_count":saved["total_matches"],
            "collections_truncated":saved["truncated"],"live":False,
            "next_tools":{"tasks":"study_tasks","collections":"study_collections","source":"study_evidence"},
            "note":"Cached school hub; refresh a service for current information."}
