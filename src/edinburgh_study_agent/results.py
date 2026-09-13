"""Read the student's own loaded EUCLID course results, without year clicks.

Only labelled year panels and the observed data-uoeid course-result fields are
read. SITS URLs, hidden inputs, staff details and scripts never leave the browser.
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from .models import Item, Observation, clean_text, now_utc
from .store import identifier

ENTRY = "https://www.myed.ed.ac.uk/"
CACHE_SECONDS = 300
YEAR = re.compile(r"^(\d{4})/(\d{2})$")

# Courses serves all student year panels in one authenticated HTML document.
# textContent on these explicit read-only fields also reads collapsed year tabs;
# it does not reveal inputs or unrelated hidden account/administration content.
COURSE_RESULTS = r"""() => {
  const text=e=>(e?.textContent || '').replace(/\s+/g,' ').trim();
  const tabs=[...document.querySelectorAll('a[href^="#"]')]
    .filter(a=>/^\d{4}\/\d{2}$/.test(text(a)));
  const seen=new Set();
  return tabs.filter(a=>{const y=text(a);if(seen.has(y))return false;seen.add(y);return true;})
    .slice(0,30).map(a=>{
      const panel=document.getElementById(a.getAttribute('href').slice(1));
      const blocks=[...(panel?.querySelectorAll('[data-uoeid="student-course-mark"]') || [])];
      return {academic_year:text(a),panel_found:!!panel,
        selected:!!panel?.getClientRects().length,block_count:blocks.length,
        records:blocks.slice(0,500).map(block=>{
          const heading=block.querySelector('.accordion-heading');
          const title=text(heading?.querySelector('.hidden-phone txtbold') || heading?.querySelector('txtbold'));
          const field=name=>text(block.querySelector('[data-uoeid="course-'+name+'"]'));
          return {title,mark:field('mark'),grade:field('grade'),credits:field('credits'),
            result:field('result'),sit:field('sit')};
        })};
    });
}"""


def validate_year(value: str) -> str:
    if value in {"all", "current"}:
        return value
    match=YEAR.fullmatch(value)
    if not match or int(match[2]) != (int(match[1])+1) % 100:
        raise ValueError("academic_year must be all, current or YYYY/YY (for example 2025/26).")
    return value


def read_results(store, page, academic_year="all"):
    validate_year(academic_year)
    panels=page.evaluate(COURSE_RESULTS)
    available=[p["academic_year"] for p in panels]
    selected=[p for p in panels if academic_year=="all" or
              (academic_year=="current" and p["selected"]) or p["academic_year"]==academic_year]
    stamp=now_utc()
    items, years, failures=[],[],[]
    if not selected:
        failures.append("The requested academic year was not observed. Available years are listed; do not guess another record.")
    for panel in selected:
        year=validate_year(panel["academic_year"])
        rows=panel["records"]
        complete=(panel["panel_found"] and 0<len(rows)==panel["block_count"] and
                  all(r["title"] for r in rows))
        if not complete:
            failures.append(f"{year}: the loaded course-result fields were missing or incomplete.")
        records=[]
        evidence=[]
        for index,row in enumerate(rows):
            if not row["title"]:
                continue
            row={k:clean_text(str(v)) for k,v in row.items()}
            code=re.search(r"\b([A-Z]{4}\d{5})$",row["title"])
            native=f"euclid-result:{year}:{code[1] if code else 'course'}:{index}"
            key=identifier("university","resource",native)
            # Preserve published strings; an empty mark never becomes zero.
            records.append({"item_id":key,"academic_year":year,
                            "course_code":code[1] if code else None,**row})
            excerpt=" | ".join([row["title"]]+[k+": "+row[k] for k in ("mark","grade","credits","result","sit")])
            evidence.append(Item(native_id=native,kind="resource",title=row["title"],
                url=ENTRY,service_id="euclid",excerpt=excerpt[:3000],status="available"))
        if records:
            text="EUCLID course results | "+year+"\n"+"\n".join(i.excerpt for i in evidence)
            observation=Observation(source="university",source_url=ENTRY,
                title="EUCLID: Course results "+year,observed_at=stamp,
                scope="Labelled academic-year panel; loaded student-course-mark fields only",
                coverage="partial",authentication="authenticated",text=text,items=evidence)
            receipt=store.capture(observation)
            years.append({"academic_year":year,"record_count":len(records),
                          "observation_id":receipt["observation_id"],"complete_loaded_panel":complete})
            items.extend(records)
        else:
            years.append({"academic_year":year,"record_count":0,"complete_loaded_panel":False})
    result={"live":True,"service_id":"euclid","section":"Courses","academic_year":academic_year,
        "observed_at":stamp.isoformat(),"authentication":"authenticated","source_url":ENTRY,
        "available_years":available,"years":years,"items":items,"record_count":len(items),
        "coverage":"partial" if failures else "complete_loaded_years","failed":failures,
        "source_content_is_untrusted":True,
        "note":"Own published course-result fields as observed, including blank marks. Coverage is limited to loaded year panels, not an official transcript or every assessment component."}
    if not failures:
        with store.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS result_cache (academic_year TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO result_cache VALUES(?,?)",(academic_year,json.dumps(result,ensure_ascii=False)))
    return result


def cached_results(store, academic_year):
    validate_year(academic_year)
    with store.connection() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='result_cache'").fetchone():
            return None
        row=db.execute("SELECT payload FROM result_cache WHERE academic_year=?",(academic_year,)).fetchone()
    if not row:
        return None
    result=json.loads(row[0])
    age=(now_utc()-datetime.fromisoformat(result["observed_at"])).total_seconds()
    if not 0<=age<CACHE_SECONDS:
        return None
    result.update(live=False,cache_hit=True,cache_age_seconds=round(age,1),
                  cache_ttl_seconds=CACHE_SECONDS,remote_freshness_checked=False)
    return result


def invalidate_cache(store):
    # A fresh interactive login may belong to a different student in this profile.
    with store.connection() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='result_cache'").fetchone():
            db.execute("DELETE FROM result_cache")


def workflow_hint():
    # Existing conversations may remember the old catalog. Return discovery
    # metadata on their known portal tools, rather than relying on initialize
    # instructions or assuming that a host re-injects every changed schema.
    from . import __version__
    return {"plugin_version":__version__,"host_browser_required":False,
        "available_workflows":{"course_results":{"tool":"study_results",
            "arguments":{"academic_year":"all"},
            "status":"implemented",
            "if_tool_not_listed":{"tool":"study_read_service","arguments":{"service_id":"euclid","section":"Courses","query":"all","max_pages":1}},
            "scope":"Own published course marks/grades across loaded academic years. No year-tab clicks, HEAR preview or host browser needed."}}}
