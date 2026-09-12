"""Optional synthetic benchmark; install tiktoken in the development environment only."""
import argparse, json, sys, tempfile, time, statistics, zipfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from edinburgh_study_agent.store import Store, identifier
from edinburgh_study_agent.models import Item, Observation, normal
from edinburgh_study_agent import server, collections, school, file_text
from edinburgh_study_agent.downloads import digest_file
import tiktoken

parser=argparse.ArgumentParser()
parser.add_argument("--output", required=True)
args=parser.parse_args()
encoding=tiktoken.get_encoding("o200k_base")

def measure(fn, repeats=7):
    times=[]
    result=None
    for _ in range(repeats):
        start=time.perf_counter()
        result=fn()
        times.append((time.perf_counter()-start)*1000)
    return {"median_ms":round(statistics.median(times),3),
            "min_ms":round(min(times),3), "max_ms":round(max(times),3)},result

def response_tokens(value):
    data=value.model_dump(mode="json",exclude_none=True)
    text=json.dumps(data,ensure_ascii=False,separators=(",",":"))
    return {"tokens_o200k_base":len(encoding.encode(text)),
            "utf8_bytes":len(text.encode())}

with tempfile.TemporaryDirectory(prefix="campus-benchmark-") as temporary:
    store=Store(Path(temporary))
    server.store=lambda:store
    identifiers=[]
    for batch in range(100):
        items=[]
        for n in range(batch*30,(batch+1)*30):
            title=f"Synthetic lecture resource {n}"
            excerpt=title+" "+("Study material for chemistry and research. "*28)
            items.append(Item(native_id=f"fixture-{n}",kind="resource",title=title,
                url=f"https://www.learn.ed.ac.uk/ultra/course/fixture-{n}",
                course_id="fixture-course",excerpt=excerpt,status="available"))
        obs=Observation(source="learn",source_url="https://www.learn.ed.ac.uk/ultra/course",
            title="Synthetic benchmark",observed_at=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=batch),
            scope="synthetic benchmark only",coverage="partial",authentication="unknown",
            text="\n".join(i.excerpt for i in items),items=items)
        receipt=store.capture(obs)
        identifiers.extend(receipt["inserted"])
    for key in identifiers[:200]:
        collections.collect(store,key,"Synthetic collection",["example"],"Synthetic note")
    measurements={}
    for name,fn in [
        ("status",store.status),
        ("search",lambda:store.list_items(query="lecture",limit=20)),
        ("collections",lambda:collections.collections(store)),
        ("home",lambda:collections.home(store))]:
        measurements[name],_=measure(fn)
    tokens={
        "search_20":response_tokens(server.study_search(query="lecture",limit=20)),
        "home":response_tokens(server.study_home())}
    path=store.root/"downloads/fixture.pptx"
    path.parent.mkdir()
    with zipfile.ZipFile(path,"w") as z:
        for n in range(120):
            z.writestr(f"ppt/slides/slide{n+1}.xml",
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                +('<a:t>Synthetic lecture text for repeatable document reading.</a:t>'*30)+'</p:sld>')
    record=dict(item_id=identifiers[0],filename="fixture.pptx",path=str(path),sha256=digest_file(path),
                downloaded_at="2026-01-01T00:00:00+00:00",source_page_url="https://www.learn.ed.ac.uk/ultra/course")
    with store.connection() as db:
        db.execute("INSERT INTO downloads VALUES(?,?,?,?)",(identifiers[0],record["sha256"],record["downloaded_at"],json.dumps(record)))
    start=time.perf_counter()
    file_text.read_file(store,identifiers[0],40000,4000)
    measurements["document_cold"]={"ms":round((time.perf_counter()-start)*1000,3)}
    measurements["document_warm"],_=measure(lambda:file_text.read_file(store,identifiers[0],40000,4000))
    job_id="e"*32
    school.write_json(school.job_path(store,job_id),dict(
        job_id=job_id,action="courses",state="complete",created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",result=store.list_items(limit=100)))
    tokens["job_100"]=response_tokens(server.study_school_job(job_id))
    output={"data":"isolated synthetic fixture", "items":3000,"observations":100,"collections":200,
        "timings":measurements,"responses":tokens,"tokenizer":"o200k_base",
        "limitations":"Local CPU and serialized MCP payload only, not campus network latency or actual model billing."}
    Path(args.output).write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps(output))
