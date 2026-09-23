"""Private persistent school browser and asynchronous, bounded resource jobs.

The browser alone manages its dedicated local profile. No cookies, browser storage,
credentials, screenshots, network traces, or signed URLs are returned to the agent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .store import Store, identifier
from .file_errors import FileDownloadError
from .models import now_utc, safe_url, Item, Observation, SOURCE_HOSTS
from .school_dom import (LEARN_HOME, LEARN_HOSTS, COURSE_CARDS, COURSE_SCAN, RESOURCE_LINKS, EXPANDERS,
                         COURSE_ID, course_items, resource_items, observation, learn_url)
from .downloads import download_resource, list_downloads, safe_filename, verified_copy
from .school_errors import (LoginRequired, CourseUnavailable, SchoolPageNotReady,
                            SchoolNetworkError, BrowserBusy, NETWORK_CODES)

ACTIONS = {"login", "courses", "resources", "download", "myed", "service", "read_resource", "results", "timetable", "materials", "messages"}
TERMINAL = {"complete", "partial", "needs_login", "failed", "cancelled"}
JOB_ID = re.compile(r"^[a-f0-9]{32}$")


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temporary, path)


def school_root(store: Store) -> Path:
    return store.root / "school"


def job_path(store: Store, job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Use the job_id returned by a school tool.")
    return school_root(store) / "jobs" / (job_id + ".json")


def worker_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            code = ctypes.c_uint32()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_job(store: Store, job_id: str) -> dict:
    path = job_path(store, job_id)
    if not path.is_file():
        raise ValueError("Unknown school job.")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Dispatch inputs are local, bounded ids/queries, not authentication material.
    data.pop("arguments", None)
    if data["state"] not in TERMINAL:
        age = (now_utc() - datetime.fromisoformat(data["updated_at"])).total_seconds()
        dead = data.get("worker_pid") and not worker_running(data["worker_pid"])
        if (age > 10 and dead) or (age > 120 and not data.get("worker_pid")):
            data.update(state="failed", progress="The school worker ended before returning a result.",
                        reconciled_dead_worker=True)
    data["source_content_is_untrusted"] = True
    data["poll_after_seconds"] = 3 if data["state"] not in TERMINAL else 0
    return data


def wait_job(store: Store,job_id: str,wait_seconds: float = 20,if_updated_at: str | None = None) -> dict:
    if not 0<=wait_seconds<=25:
        raise ValueError("wait_seconds must be 0..25.")
    deadline=time.monotonic()+wait_seconds
    value=read_job(store,job_id)
    while value["state"] not in TERMINAL and time.monotonic()<deadline:
        time.sleep(min(0.2,max(0,deadline-time.monotonic())))
        value=read_job(store,job_id)
    if if_updated_at and value["updated_at"]==if_updated_at and value["state"] not in TERMINAL:
        return {k:value[k] for k in ("job_id","state","updated_at","poll_after_seconds")} | {"unchanged":True}
    return value


def cached_operation(store: Store,action: str,args: dict):
    if action == "materials":
        from .materials import scope_choice
        choice = scope_choice(store, args)
        if choice is not None:
            return choice
    if args.get("refresh",action=="download"):
        return None
    if action in {"timetable","materials","messages"}:
        from importlib import import_module
        name="learn_updates" if action=="messages" else action
        return import_module("."+name,__package__).cached(store,args)
    if action=="results":
        from .results import cached_results
        return cached_results(store,args.get("academic_year","all"))
    if action=="download":
        saved=[verified_copy(store,key) for key in dict.fromkeys(args["item_ids"])]
        if all(saved):
            return {"saved":saved,"failed":[],"complete":True,"live":False,
                    "remote_freshness_checked":False}
    if action=="read_resource":
        item=store.item(args["item_id"])
        if item["source"]!="learn" or item["kind"] not in {"resource","assignment"}:
            return None
        saved=verified_copy(store,item["id"])
        if saved:
            from .file_text import read_file
            return {"live":False,"remote_freshness_checked":False,"download":saved,
                    "content":read_file(store,item["id"],0,6000)}
    return None


def session_status(store: Store) -> dict:
    path = school_root(store) / "session.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    active = []
    jobs_root = school_root(store) / "jobs"
    if jobs_root.exists():
        for path in sorted(jobs_root.glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)[:30]:
            entry = read_job(store, path.stem)
            if entry["state"] not in TERMINAL:
                active.append({k:entry.get(k) for k in ("job_id","action","state","updated_at")})
    return {"browser_owner":"edinburgh_plugin","profile_location":str(school_root(store) / "profile"),
            "previous_check":previous,"live_connection_checked":False,"active_jobs":active,
            "login_method":"One-time interactive campus login on this computer; later jobs use the dedicated profile.",
            "session_expiry":"Campus policy can require reauthentication or MFA.",
            "host_browser_required":False,"credentials_exposed_to_agent":False}


def result_state(value):
    return "needs_login" if value.get("needs_login") else "partial" if value.get("failed") or value.get("coverage") in {"partial","entry_only","external_provider","unavailable"} else "complete"


def recent_connection_failure(store: Store, action: str, arguments: dict):
    """Share one short outage cooldown across Learn reads, never across services."""
    if action not in {"courses", "resources", "materials", "messages", "download", "read_resource"}:
        return None
    root = school_root(store) / "jobs"
    if not root.exists():
        return None
    for path in sorted(root.glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)[:30]:
        prior = json.loads(path.read_text(encoding="utf-8"))
        failure = prior.get("failure", {})
        if prior.get("blocked_by_job_id") or prior.get("state") not in {"failed","partial"} or failure.get("code") not in NETWORK_CODES:
            continue
        if failure["code"] == "HTTP_ERROR" and failure.get("http_status",0) < 500:
            continue  # A single forbidden/missing course is not a service-wide outage.
        age = (now_utc()-datetime.fromisoformat(prior["updated_at"])).total_seconds()
        if not 0 <= age < 60:
            continue
        identity = json.dumps(["connection_backoff",prior["job_id"],action,arguments],sort_keys=True)
        key = hashlib.sha256(identity.encode()).hexdigest()[:32]
        stamp = now_utc().isoformat()
        if not job_path(store,key).exists():
            write_json(job_path(store,key),{
                "job_id":key,"action":action,"state":"failed","created_at":stamp,"updated_at":stamp,
                "progress":"A recent Learn connection failure is still in its short cooldown. Check the connection before retrying; cached files remain available.",
                "failure":failure,"blocked_by_job_id":prior["job_id"],"browser_started":False})
        return read_job(store,key) | {"retry_after_seconds":max(1,60-int(age)),"reused_failed_job":True}
    return None


def start_job(store: Store, action: str, arguments: dict | None = None) -> dict:
    if action not in ACTIONS:
        raise ValueError("Unsupported school action.")
    arguments = arguments or {}
    cached=cached_operation(store,action,arguments)
    if cached is not None:
        # Repeated cached queries share an immutable receipt instead of writing
        # another job file each time. Source freshness remains in the result.
        identity=json.dumps([action,arguments,cached],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        key=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        if job_path(store,key).is_file():
            return read_job(store,key) | {"reused_cached_job":True}
        stamp=now_utc().isoformat()
        write_json(job_path(store,key),{"job_id":key,"action":action,"state":result_state(cached),
            "created_at":stamp,"updated_at":stamp,"progress":"Dated local result ready.",
            "result":cached,"browser_started":False})
        return read_job(store,key)
    blocked = recent_connection_failure(store, action, arguments)
    if blocked is not None:
        return blocked
    active = session_status(store)["active_jobs"]
    if action in {"results","timetable","materials","messages"}:
        for prior in active:
            if prior["action"] == action:
                record=json.loads(job_path(store,prior["job_id"]).read_text(encoding="utf-8"))
                if record.get("arguments")==arguments:
                    return read_job(store,prior["job_id"]) | {"reused_active_job":True}
    if action == "login":
        prior = next((j for j in active if j["action"] == "login"), None)
        if prior:
            return read_job(store, prior["job_id"])
    if len(active) >= 4:
        raise ValueError("Wait for an existing school job before starting another.")
    job_id = uuid.uuid4().hex
    stamp = now_utc().isoformat()
    record = {"job_id":job_id,"action":action,"arguments":arguments,"state":"queued",
              "created_at":stamp,"updated_at":stamp,"progress":"Starting the dedicated school browser."}
    path = job_path(store, job_id)
    write_json(path, record)
    python = Path(sys.executable)
    if os.name == "nt" and python.with_name("pythonw.exe").is_file():
        python = python.with_name("pythonw.exe")
    environment = dict(os.environ, EDINBURGH_STUDY_HOME=str(store.root.resolve()), PYTHONUTF8="1")
    # Connection keys are unnecessary in the school browser process.
    for key in list(environment):
        if not re.search(r"(?i)(api_?key|token|secret|password|credential|tunnel_key)", key):
            continue
        environment.pop(key,None)
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    try:
        child = subprocess.Popen([str(python),"-m","edinburgh_study_agent.school","--job",job_id],
            env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=flags,start_new_session=os.name != "nt")
        # The child owns subsequent record updates, avoiding a parent/worker write race.
    except Exception:
        record.update(state="failed",progress="Could not start the local school worker.")
        write_json(path, record)
        # A failed launch is still a persisted job. Return its receipt so the
        # caller can inspect it without repeating the attempted operation.
        return read_job(store, job_id)
    value=read_job(store, job_id)
    if action=="myed" or (action=="service" and arguments.get("service_id") in {"myed","euclid"}):
        from .results import workflow_hint
        value.update(workflow_hint())
    return value


@contextmanager
def profile_lock(root: Path, timeout: float = 120):
    root.mkdir(parents=True,exist_ok=True)
    path = root / "profile.lock"
    handle = path.open("a+b")
    handle.seek(0,2)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while not acquired:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise BrowserBusy()
                time.sleep(0.5)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()


@contextmanager
def browser_context(store: Store, interactive: bool = False):
    from playwright.sync_api import sync_playwright
    root = school_root(store)
    with profile_lock(root):
        with sync_playwright() as runtime:
            from .browsers import channel
            context = runtime.chromium.launch_persistent_context(
                str(root / "profile"), channel=channel(),headless=not interactive,
                chromium_sandbox=True,accept_downloads=False,
                args=["--restore-last-session"],viewport={"width":1280,"height":900})
            try:
                fresh = context.new_page()
                for restored in list(context.pages):
                    if restored != fresh:
                        restored.close()
                context.set_default_timeout(15000)
                context.set_default_navigation_timeout(45000)
                if not interactive:
                    context.route("**/*", lambda route: route.abort()
                                  if route.request.resource_type in {"image","media","font"}
                                  else route.continue_())
                yield context
            finally:
                context.close()


def authenticated(page) -> bool:
    try:
        return bool(page.evaluate("""() => {
            if (!['learn.ed.ac.uk','www.learn.ed.ac.uk'].includes(location.hostname)) return false;
            const cards = [...document.querySelectorAll('a[id^="course-link-_"]')].some(a => a.innerText.trim());
            const courseHeading = [...document.querySelectorAll('h1,h2')].some(e => e.innerText.trim()==='Course Content');
            const outline = [...document.querySelectorAll('a[href]')].some(a => /\\/ultra\\/courses\\/_\\d+_\\d+\\/outline$/.test(a.href));
            const exit = [...document.querySelectorAll('button')].some(b => (b.innerText.trim() || b.getAttribute('aria-label'))==='Exit');
            const password=document.querySelector('input[type="password"]');
            if (password && password.getClientRects().length) return false;
            const nav=[...document.querySelectorAll('a[href]')];
            const profile=nav.some(a=>/\\/ultra\\/profile$/.test(a.href));
            const surfaces=['/ultra/course','/ultra/stream','/ultra/messages'];
            const shell=profile && surfaces.filter(p=>nav.some(a=>a.href.endsWith(p))).length>=2;
            return cards || courseHeading || (outline && exit) || shell;
        }"""))
    except Exception:
        return False


def ensure_learn(page):
    from .school_navigation import observe
    navigation = observe(page)
    deadline = time.monotonic() + 20
    followed_login = False
    while time.monotonic() < deadline:
        navigation.check()
        if authenticated(page):
            return
        try:
            if urlsplit(page.url).hostname in LEARN_HOSTS:
                blocked=page.get_by_text("This course is currently unavailable.",exact=False)
                if blocked.count() and blocked.first.is_visible():
                    raise CourseUnavailable()
            from .portal import login_gate
            if login_gate(page):
                raise LoginRequired(**navigation.context())
            # Learn can show its welcome page even while the campus SSO session is valid.
            # Follow the real same-origin login link once; never supply credentials.
            if not followed_login and urlsplit(page.url).hostname in LEARN_HOSTS:
                login = page.get_by_role("link",name="Login to Learn",exact=True)
                if login.count() and login.first.is_visible():
                    href = login.first.get_attribute("href")
                    from urllib.parse import urljoin
                    target = urljoin(page.url,href or "")
                    parsed = urlsplit(target)
                    if parsed.scheme == "https" and parsed.hostname in LEARN_HOSTS and not parsed.username:
                        followed_login = True
                        navigation.navigate(target)
                        continue
            password = page.locator('input[type="password"]')
            if password.count() and password.first.is_visible():
                raise LoginRequired(**navigation.context())
        except (LoginRequired,CourseUnavailable,SchoolNetworkError,SchoolPageNotReady):
            raise
        except Exception:
            pass
        time.sleep(0.4)
    navigation.check()
    raise SchoolPageNotReady(**navigation.context())


def mark_session(store: Store, connected: bool):
    write_json(school_root(store) / "session.json",
        {"checked_at":now_utc().isoformat(),"authenticated":connected,
         "service":"learn","scope":"dedicated_local_browser","credentials_exported":False})


def goto_learn(page, url: str = LEARN_HOME):
    from .school_navigation import observe
    learn_url(url)
    navigation = observe(page)
    navigation.navigate(url)
    ensure_learn(page)
    # Campus SSO may return to Courses instead of retaining the requested deep link.
    if urlsplit(page.url).path != urlsplit(url).path:
        navigation.navigate(url)
        ensure_learn(page)


def wait_cards(page) -> list[dict]:
    deadline = time.monotonic() + 25
    previous, stable = None, 0
    rows = []
    while time.monotonic() < deadline:
        scan = page.evaluate(COURSE_SCAN)
        rows, slots = scan["rows"], scan["slots"]
        signature = tuple((r["native_id"],r["title"]) for r in rows)
        stable = stable + 1 if signature == previous else 0
        previous = signature
        if rows and len(rows) == slots and stable >= 2:
            return rows
        time.sleep(0.3)
    return rows


def list_courses(store: Store, page, args: dict, progress) -> dict:
    goto_learn(page)
    rows, pages, complete, seen = [], 0, False, set()
    fully_loaded = True
    terms = page.get_by_role("combobox",name="Terms",exact=True)
    filter_name = terms.inner_text() if terms.count() else "displayed filter unknown"
    limit = args.get("max_pages",10)
    if not 1 <= limit <= 20:
        raise ValueError("max_pages must be 1..20.")
    for number in range(limit):
        batch = wait_cards(page)
        fully_loaded = fully_loaded and len(batch) == page.locator('a[id^="course-link-"]').count()
        signature = tuple(r["native_id"] for r in batch)
        if not batch or signature in seen:
            break
        seen.add(signature)
        rows.extend(batch)
        pages += 1
        progress("Reading course-list page " + str(pages))
        next_button = page.get_by_role("button",name="Next Page",exact=True)
        if not next_button.count() or not next_button.is_enabled():
            complete = fully_loaded
            break
        if number + 1 == limit:
            break
        next_button.click()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = page.evaluate(COURSE_CARDS)
            if current and tuple(r["native_id"] for r in current) != signature:
                break
            time.sleep(0.3)
    items = course_items(rows)
    if not items:
        return {"live":True,"items":[],"coverage":"partial","warning":"No loaded course cards were observed; this is not proof of no enrolments."}
    obs = observation(page.url,"Learn courses",items,
        filter_name[:150] + "; traversed " + str(pages) + " course-list page(s)",complete)
    receipt = store.capture(obs)
    wanted = args.get("query","").casefold()
    results = store.items_by_ids(identifier("learn","course",i.native_id) for i in items
               if not wanted or wanted in i.title.casefold())
    mark_session(store,True)
    return {"live":True,"items":results,"observed_at":obs.observed_at.isoformat(),
            "coverage":obs.coverage,"pages":pages,"observation_id":receipt["observation_id"]}


def resolve_course(store: Store, course_id: str) -> dict:
    courses = store.list_items(kind="course",limit=500)["items"]
    for course in courses:
        if course_id in {course["id"],course["native_id"]}:
            if not course.get("url"):
                with store.connection() as db:
                    previous = db.execute("SELECT payload FROM observations WHERE source='learn' ORDER BY observed_at DESC LIMIT 200").fetchall()
                for row in previous:
                    obs = json.loads(row["payload"])
                    expected = "/ultra/courses/" + course["native_id"] + "/outline"
                    if urlsplit(obs["source_url"]).path == expected:
                        course["url"] = obs["source_url"]
                        break
            return course
    raise ValueError("List courses first and use one returned course id.")


def open_course(store: Store, page, course: dict):
    native_id=course["native_id"]
    if not COURSE_ID.fullmatch(native_id):
        raise ValueError("Use a native id from the observed course list.")
    # The Learn outline route is validated by real course pages. Only observed course ids enter it.
    target=course.get("url") or "https://www.learn.ed.ac.uk/ultra/courses/" + native_id + "/outline"
    goto_learn(page,learn_url(target,native_id))
    page.get_by_role("heading",name="Course Content",exact=True).wait_for(state="visible",timeout=20000)


def list_resources(store: Store, page, args: dict, progress) -> dict:
    search_deadline=time.monotonic()+args.get("budget_seconds",600)
    course = resolve_course(store,args["course_id"])
    if course["status"] == "unavailable" and not args.get("probe_unavailable"):
        return {"live":False,"items":[],"coverage":"partial","warning":"Previously observed as unavailable. Refresh courses to verify its current status."}
    open_course(store,page,course)
    max_folders = args.get("max_folders",80)
    if not 1 <= max_folders <= 150:
        raise ValueError("max_folders must be 1..150.")
    deadline=min(time.monotonic()+30,search_deadline)
    previous,stable=None,0
    while time.monotonic()<deadline:
        content=page.evaluate(RESOURCE_LINKS)
        controls=page.evaluate(EXPANDERS)
        signature=tuple(r["url"] for r in content)+tuple(r["id"] for r in controls)
        stable=stable+1 if signature==previous else 0
        previous=signature
        if signature and stable>=3:
            break
        time.sleep(0.5)
    expanded, failures = set(), []
    folder_context={}
    search_terms=[t.casefold() for t in args.get("search_terms",[]) if t]
    # A bounded fixed-point expansion visits nested modules as they become visible.
    for _ in range(max_folders):
        if time.monotonic()>=search_deadline:break
        if args.get("stop_after_matches") and any(any(t in (r["title"]+" "+folder_context.get(r["url"],"")).casefold() for t in search_terms) for r in page.evaluate(RESOURCE_LINKS)):
            break
        candidates = page.evaluate(EXPANDERS)
        candidates.sort(key=lambda r:not any(t in r["title"].casefold() for t in search_terms))
        candidate = next((x for x in candidates if x["id"] not in expanded),None)
        if not candidate:
            break
        expanded.add(candidate["id"])
        progress("Reading course folder: " + candidate["title"][:120])
        button = page.locator('[id="' + candidate["id"] + '"]')
        try:
            button.click()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and button.get_attribute("aria-expanded") != "true":
                time.sleep(0.2)
            if button.get_attribute("aria-expanded") != "true":
                failures.append(candidate["title"])
            # Wait for this documented control's content region, not a visual screenshot.
            controlled = button.get_attribute("aria-controls")
            if controlled:
                page.locator('[id="' + controlled.replace('"','') + '"]').wait_for(state="attached",timeout=10000)
            # Expanded regions attach before their asynchronously fetched links.
            last,settled=None,0
            for _ in range(20):
                signature=(len(page.evaluate(RESOURCE_LINKS)),len(page.evaluate(EXPANDERS)))
                settled=settled+1 if signature==last else 0
                last=signature
                if settled>=4:
                    break
                time.sleep(0.3)
            if controlled:
                links=page.locator('[id="'+controlled.replace('"','')+'"]').locator("a[href]").evaluate_all(
                    "(aa)=>aa.map(a=>a.href)")
                for url in links:
                    folder_context[url]=(folder_context.get(url,"")+" "+candidate["title"]).strip()[:1000]
        except Exception:
            failures.append(candidate["title"])
    rows = page.evaluate(RESOURCE_LINKS)
    items = resource_items(rows,course)[:500]
    for item in items:
        if folder_context.get(item.url):
            item.excerpt=item.title+"\n"+folder_context[item.url]
    obs = observation(page.url,course["title"] + " resources",items,
                      "Course outline and " + str(len(expanded)) + " expanded modules/folders; external tools excluded",
                      complete=False)
    receipt = store.capture(obs)
    # Save the real, observed outline URL for subsequent direct navigation.
    course_item = Item(native_id=course["native_id"],kind="course",title=course["title"],url=page.url,
        course_id=course["native_id"],course_title=course["title"],excerpt=course["title"],status="available")
    store.capture(observation(page.url,course["title"],[course_item],"Observed open course outline"))
    wanted = args.get("query","").casefold()
    results = store.items_by_ids(identifier("learn",i.kind,i.native_id) for i in items
               if not wanted or wanted in i.title.casefold())
    mark_session(store,True)
    return {"live":True,"items":results,"coverage":"partial","observed_at":obs.observed_at.isoformat(),
            "expanded_folders":len(expanded),"folders_not_opened":failures,
            "remaining_collapsed":len(page.evaluate(EXPANDERS)),
            "observation_id":receipt["observation_id"],
            "note":"Course outline links only. Use study_materials with a document page item_id to discover/download its embedded originals. Missing outline files are not proof of absence. External/LTI and hidden content remain outside this scan."}


def original_file(page, item: dict) -> tuple[str, str | None, dict]:
    from .learn_files import resolve_original
    return resolve_original(page, item, goto_learn)


def download_items(store: Store, page, args: dict, progress) -> dict:
    ids = args["item_ids"]
    if not isinstance(ids,list) or not 1 <= len(ids) <= 30 or any(not isinstance(i,str) for i in ids):
        raise ValueError("Choose 1..30 observed resource item ids.")
    saved, failed = [], []
    ids = list(dict.fromkeys(ids))
    index = 0
    while index < len(ids):
        item_id = ids[index]
        index += 1
        item = store.item(item_id)
        if item["kind"] != "resource":
            failed.append({"item_id":item_id,"error":"Only resource items can be downloaded."})
            continue
        progress("Downloading " + str(index) + "/" + str(len(ids)) + ": " + item["title"][:100])
        try:
            cached=verified_copy(store,item_id) if not args.get("refresh",True) else None
            if cached:
                saved.append(cached)
                continue
            from .learn_attachments import document
            if document(item):
                content = read_resource(store,page,{"item_id":item_id},progress)
                children = content.get("attachments",[])
                if content.get("attachment_discovery",{}).get("skipped"):
                    raise FileDownloadError("ATTACHMENT_DISCOVERY_INCOMPLETE")
                if not children:
                    raise FileDownloadError("UNSUPPORTED_CONTAINER")
                child_ids = [c["id"] for c in children if c["id"] not in ids]
                if len(ids) - 1 + len(child_ids) > 30:
                    raise FileDownloadError("ATTACHMENT_AMBIGUOUS",
                        candidates=[c["attachment"]["filename"] for c in children][:5])
                # Replace the container, never assign its identity to file bytes.
                ids[index-1:index] = child_ids
                index -= 1
                continue
            url,filename,binding = original_file(page,item)
            result = download_resource(store,item_id,url,filename,
                                       bool(args.get("refresh",True)),100,binding=binding)
            saved.append(result)
            url = None
        except LoginRequired:
            mark_session(store,False)
            return {"saved":saved,"failed":failed,"needs_login":True,
                    "remaining_item_ids":ids[index-1:],"complete":False}
        except Exception as error:
            if isinstance(error, FileDownloadError):
                fields = error.fields()
            elif isinstance(error, SchoolNetworkError):
                fields = {"code": error.failure["code"], "error": str(error),
                          "recovery_action": "check_connection", "automatic_retry": False}
            elif isinstance(error, SchoolPageNotReady):
                fields = FileDownloadError("PREVIEW_NOT_READY").fields()
            else:
                fields = FileDownloadError("DOWNLOAD_FAILED").fields()
            failed.append({"item_id":item_id,"title":item["title"],
                           "error_type":type(error).__name__, **fields})
            if isinstance(error, SchoolNetworkError):
                return {"saved":saved,"failed":failed,"complete":False,
                        "remaining_item_ids":ids[index:]}
    return {"saved":saved,"failed":failed,"complete":not failed}


def read_resource(store: Store,page,args,progress):
    item=store.item(args["item_id"])
    if item["source"]!="learn" or item["kind"] not in {"resource","assignment"}:
        raise ValueError("Choose an observed Learn resource or assessment page.")
    if item.get("attachment") or "/file/" in urlsplit(item.get("url") or "").path:
        from .file_text import read_file
        url,filename,binding=original_file(page,item)
        saved=download_resource(store,item["id"],url,filename,args.get("refresh",False),100,binding=binding)
        return {"live":True,"download":saved,"content":read_file(store,item["id"],0,6000)}
    goto_learn(page,learn_url(item["url"],item["course_id"]))
    from .portal import wait_page
    wait_page(page)
    text=page.locator("body").inner_text()[:60000]
    if not text.strip() or item["title"].casefold() not in text.casefold():
        raise ValueError("The requested resource content did not finish loading.")
    observed=Item(native_id=item["native_id"],kind=item["kind"],title=item["title"],
        url=page.url,course_id=item["course_id"],course_title=item["course_title"],
        excerpt=item["title"],status="available")
    from .learn_attachments import document, discover
    attachments, discovery = discover(page,item) if document(item) else ([], None)
    obs=observation(page.url,item["title"],[observed,*attachments],
        "Observed Learn resource page and visible inline attachment metadata; no forms submitted",extra_text=text)
    receipt=store.capture(obs)
    return {"live":True,"item_id":item["id"],"title":item["title"],"url":page.url,
        "text":text[:18000],"text_truncated":len(text)>18000,"coverage":"partial",
        "observation_id":receipt["observation_id"],"observed_at":obs.observed_at.isoformat(),
        "source_content_is_untrusted":True,
        "attachments":store.items_by_ids(identifier("learn",i.kind,i.native_id) for i in attachments),
        **({"attachment_discovery":discovery} if discovery else {})}


def execute_job(store: Store, job_id: str):
    path = job_path(store,job_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["worker_pid"] = os.getpid()
    started=time.monotonic()
    record["timings_ms"]={}
    try:
        record["timings_ms"]["worker_start_delay"]=round((now_utc()-datetime.fromisoformat(record["created_at"])).total_seconds()*1000)
    except (KeyError, ValueError, TypeError):
        pass  # Optional telemetry must not prevent an older job from reporting errors.
    def progress(message: str, state: str = "running"):
        record.update(state=state,progress=message,updated_at=now_utc().isoformat())
        write_json(path,record)
    try:
        action, args = record["action"], record["arguments"]
        progress("Waiting for the private school browser.")
        with browser_context(store,interactive=action == "login") as context:
            record["timings_ms"]["browser_ready"]=round((time.monotonic()-started)*1000)
            page = context.pages[0] if context.pages else context.new_page()
            if action == "login":
                from .results import invalidate_cache
                invalidate_cache(store)
                from .workflow_cache import invalidate
                invalidate(store)
                from .school_navigation import observe
                navigation = observe(page)
                navigation.navigate(LEARN_HOME)
                progress("Complete the campus sign-in and MFA in the dedicated Chrome window. It closes after verification.",
                         "waiting_for_login")
                deadline = time.monotonic() + 900
                while time.monotonic() < deadline:
                    navigation.check()
                    if not context.pages:
                        raise LoginRequired()
                    if any(authenticated(candidate) for candidate in context.pages if not candidate.is_closed()):
                        mark_session(store,True)
                        result = {"authenticated":True,"service":"learn",
                                  "next_step":"Use live course/resource tools; the agent does not need a host browser."}
                        break
                    time.sleep(1)
                else:
                    raise LoginRequired()
            elif action == "results":
                from .portal import read_service
                result = read_service(store,page,{"service_id":"euclid","section":"Courses",
                    "max_pages":1,"results_only":True,**args},progress)
            elif action in {"timetable","materials","messages"}:
                from . import timetable, materials, learn_updates
                result={"timetable":timetable,"materials":materials,"messages":learn_updates}[action].read(store,page,args,progress)
            elif action == "courses":
                result = list_courses(store,page,args,progress)
            elif action == "resources":
                result = list_resources(store,page,args,progress)
            elif action == "read_resource":
                result = read_resource(store,page,args,progress)
            elif action == "download":
                result = download_items(store,page,args,progress)
            elif action in {"myed", "service", "read_resource"}:
                from .portal import read_service
                result = read_service(store,page,{"service_id":"myed",**args},progress)
            else:
                raise ValueError("Unsupported school action.")
            record["timings_ms"]["read_complete"]=round((time.monotonic()-started)*1000)
        record["timings_ms"]["worker_total"]=round((time.monotonic()-started)*1000)
        record["result"] = result
        if result.get("failure"):
            record["failure"] = result["failure"]
            if result.get("needs_login") and action in {"materials","messages"}:
                mark_session(store,False)
        state = result_state(result)
        progress("School operation finished.",state)
    except LoginRequired as error:
        record["failure"] = error.failure
        if record["action"] in {"login","courses","resources","download","read_resource","materials","messages"}:
            mark_session(store,False)
        progress("Campus sign-in is required in this plugin's dedicated local browser. Use study_connect_school.","needs_login")
    except CourseUnavailable:
        record["result"]={"coverage":"unavailable","items":[],
            "warning":"The school says this course is currently unavailable. Its instructor controls access; this is not evidence of an expired campus login.",
            "next_step":"Use another accessible course/resource or wait for the instructor to open it. Do not repeat login or browser attempts for this closed course."}
        progress("The requested course is currently unavailable at Learn.","partial")
    except SchoolNetworkError as error:
        record["failure"] = error.failure
        record["timings_ms"]["worker_total"] = round((time.monotonic()-started)*1000)
        progress("The school connection failed while loading Learn or restoring campus sign-in. Check the reported host/network; keep saved login information. Retry once after connectivity returns. Do not request a new password or loop over other Learn tools.","failed")
    except SchoolPageNotReady as error:
        record["failure"] = error.failure
        progress("The school page did not expose supported content. No network or login failure was confirmed. Retry once later; this alone does not mean campus login expired.","failed")
    except FileDownloadError as error:
        record["error_type"] = error.code
        record["file_failure"] = error.fields()
        progress(str(error), "failed")
    except BrowserBusy:
        progress("The private browser is busy. Finish the existing login or job, then retry.","failed")
    except Exception as error:
        record["error_type"] = type(error).__name__
        progress("The school operation could not be completed. No credentials or browser exception details were logged.","failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job",required=True)
    args = parser.parse_args()
    execute_job(Store(),args.job)

if __name__ == "__main__":
    main()
