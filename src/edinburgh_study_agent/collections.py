"""Local collections connect school pages, course files and study tasks."""
import json
from .models import clean_text, now_utc
from .store import identifier
from .services import directory

def collect(store, item_id: str, collection: str = "收件箱", tags: list[str] | None = None,
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

def collections(store, query: str = "", collection: str | None = None, include_archived: bool = False) -> dict:
    with store.connection() as db:
        records=[json.loads(r["payload"]) for r in db.execute("SELECT payload FROM collections ORDER BY rowid DESC")]
    result=[]
    for record in records:
        if (record["archived"] and not include_archived) or (collection is not None and record["collection"] != collection):
            continue
        item=store.item(record["item_id"])
        if query and query.casefold() not in json.dumps([record,item],ensure_ascii=False).casefold():
            continue
        result.append({**record,"item":item})
    return {"entries":result[:200],"total_matches":len(result),"truncated":len(result)>200,"local_only":True}

def home(store) -> dict:
    with store.connection() as db:
        downloads=db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        grouped=[dict(r) for r in db.execute("SELECT source,kind,COUNT(*) count FROM items GROUP BY source,kind")]
    return {"services":directory(store)["services"],"indexed_items":grouped,"download_count":downloads,
            "tasks":store.tasks("todo")["tasks"][:50],"collections":collections(store)["entries"][:30],
            "live":False,"note":"This is your local school hub. Refresh a service for current information."}
