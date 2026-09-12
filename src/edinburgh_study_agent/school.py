"""Private persistent school browser and asynchronous, bounded resource jobs.

The browser alone manages its dedicated local profile. No cookies, browser storage,
credentials, screenshots, network traces, or signed URLs are returned to the agent.
"""
from __future__ import annotations

import argparse
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
from .models import now_utc, safe_url, Item, Observation, SOURCE_HOSTS
from .school_dom import (LEARN_HOME, LEARN_HOSTS, COURSE_CARDS, RESOURCE_LINKS, EXPANDERS,
                         COURSE_ID, course_items, resource_items, observation, learn_url)
from .downloads import download_resource, list_downloads, safe_filename

ACTIONS = {"login", "courses", "resources", "download", "myed", "service", "read_resource"}
TERMINAL = {"complete", "partial", "needs_login", "failed", "cancelled"}
JOB_ID = re.compile(r"^[a-f0-9]{32}$")


class LoginRequired(Exception):
    pass


class BrowserBusy(Exception):
    pass


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


def start_job(store: Store, action: str, arguments: dict | None = None) -> dict:
    if action not in ACTIONS:
        raise ValueError("Unsupported school action.")
    arguments = arguments or {}
    active = session_status(store)["active_jobs"]
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
    for key in ("CONTROL_PLANE_API_KEY","EDINBURGH_TUNNEL_KEY","OPENAI_API_KEY"):
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
        raise RuntimeError("Could not start the local school worker.") from None
    return read_job(store, job_id)


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
            context = runtime.chromium.launch_persistent_context(
                str(root / "profile"), channel="chrome",headless=not interactive,
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
            return cards || courseHeading || (outline && exit);
        }"""))
    except Exception:
        return False


def ensure_learn(page):
    deadline = time.monotonic() + 50
    followed_login = False
    while time.monotonic() < deadline:
        if authenticated(page):
            return
        try:
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
                        page.goto(target,wait_until="domcontentloaded")
                        continue
            password = page.locator('input[type="password"]')
            if password.count() and password.first.is_visible():
                raise LoginRequired()
        except LoginRequired:
            raise
        except Exception:
            pass
        time.sleep(0.4)
    raise LoginRequired()


def mark_session(store: Store, connected: bool):
    write_json(school_root(store) / "session.json",
        {"checked_at":now_utc().isoformat(),"authenticated":connected,
         "service":"learn","scope":"dedicated_local_browser","credentials_exported":False})


def goto_learn(page, url: str = LEARN_HOME):
    learn_url(url)
    page.goto(url,wait_until="domcontentloaded")
    ensure_learn(page)
    # Campus SSO may return to Courses instead of retaining the requested deep link.
    if urlsplit(page.url).path != urlsplit(url).path:
        page.goto(url,wait_until="domcontentloaded")
        ensure_learn(page)


def wait_cards(page) -> list[dict]:
    deadline = time.monotonic() + 25
    previous, stable = None, 0
    rows = []
    while time.monotonic() < deadline:
        rows = page.evaluate(COURSE_CARDS)
        slots = page.locator('a[id^="course-link-"]').count()
        placeholder = page.locator('a[id="course-link-"]')
        if placeholder.count():
            # Learn populates off-screen cards only after their row enters the viewport.
            # This semantic scroll costs no visual tokens and does not open a course.
            placeholder.first.scroll_into_view_if_needed(timeout=3000)
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
    results = [store.item(identifier("learn","course",i.native_id)) for i in items
               if not wanted or wanted in i.title.casefold()]
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
    course = resolve_course(store,args["course_id"])
    if course["status"] == "unavailable":
        return {"live":False,"items":[],"coverage":"partial","warning":"Previously observed as unavailable. Refresh courses to verify its current status."}
    open_course(store,page,course)
    max_folders = args.get("max_folders",80)
    if not 1 <= max_folders <= 150:
        raise ValueError("max_folders must be 1..150.")
    deadline=time.monotonic()+30
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
    # A bounded fixed-point expansion visits nested modules as they become visible.
    for _ in range(max_folders):
        candidates = page.evaluate(EXPANDERS)
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
        except Exception:
            failures.append(candidate["title"])
    rows = page.evaluate(RESOURCE_LINKS)
    items = resource_items(rows,course)[:500]
    obs = observation(page.url,course["title"] + " resources",items,
                      "Course outline and " + str(len(expanded)) + " expanded modules/folders; external tools excluded",
                      complete=False)
    receipt = store.capture(obs)
    # Save the real, observed outline URL for subsequent direct navigation.
    course_item = Item(native_id=course["native_id"],kind="course",title=course["title"],url=page.url,
        course_id=course["native_id"],course_title=course["title"],excerpt=course["title"],status="available")
    store.capture(observation(page.url,course["title"],[course_item],"Observed open course outline"))
    wanted = args.get("query","").casefold()
    results = [store.item(identifier("learn",i.kind,i.native_id)) for i in items
               if not wanted or wanted in i.title.casefold()]
    mark_session(store,True)
    return {"live":True,"items":results,"coverage":"partial","observed_at":obs.observed_at.isoformat(),
            "expanded_folders":len(expanded),"folders_not_opened":failures,
            "remaining_collapsed":len(page.evaluate(EXPANDERS)),
            "observation_id":receipt["observation_id"],
            "note":"Observed file, document and assessment links only. External/LTI tools and hidden or virtualised content can require additional adapters."}


def original_file(page, item: dict) -> tuple[str,str | None]:
    if not item.get("url"):
        raise ValueError("Refresh this course's resource list first.")
    goto_learn(page,learn_url(item["url"],item["course_id"]))
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                button = frame.get_by_role("button",name="Download",exact=True)
                if button.count():
                    original = button.first.evaluate("(b) => new URL(b.ownerDocument.URL).searchParams.get('originalUrl')")
                    if original:
                        filename=None
                        candidates=[item["title"]]
                        try:
                            candidates.append(frame.frame_element().get_attribute("title") or "")
                        except Exception:
                            pass
                        for candidate in candidates:
                            try:
                                filename=safe_filename(candidate)
                                break
                            except ValueError:
                                continue
                        return original,filename
            except Exception:
                continue
        time.sleep(0.4)
    raise ValueError("No supported original-file address was observed in the document preview.")


def download_items(store: Store, page, args: dict, progress) -> dict:
    ids = args["item_ids"]
    if not isinstance(ids,list) or not 1 <= len(ids) <= 30 or any(not isinstance(i,str) for i in ids):
        raise ValueError("Choose 1..30 observed resource item ids.")
    saved, failed = [], []
    for index,item_id in enumerate(dict.fromkeys(ids),1):
        item = store.item(item_id)
        if item["kind"] != "resource":
            failed.append({"item_id":item_id,"error":"Only resource items can be downloaded."})
            continue
        progress("Downloading " + str(index) + "/" + str(len(ids)) + ": " + item["title"][:100])
        try:
            url,filename = original_file(page,item)
            result = download_resource(store,item_id,url,filename,
                                       bool(args.get("refresh",True)),100)
            saved.append(result)
            url = None
        except LoginRequired:
            mark_session(store,False)
            return {"saved":saved,"failed":failed,"needs_login":True,
                    "remaining_item_ids":ids[index-1:],"complete":False}
        except Exception as error:
            # Never expose URLs from browser/HTTP exception strings.
            failed.append({"item_id":item_id,"title":item["title"],
                           "error_type":type(error).__name__,
                           "error":"No supported original file could be downloaded and verified."})
    return {"saved":saved,"failed":failed,"complete":not failed}


def read_resource(store: Store,page,args,progress):
    item=store.item(args["item_id"])
    if item["source"]!="learn" or item["kind"] not in {"resource","assignment"}:
        raise ValueError("Choose an observed Learn resource or assessment page.")
    if "/file/" in urlsplit(item.get("url") or "").path:
        from .file_text import read_file
        url,filename=original_file(page,item)
        saved=download_resource(store,item["id"],url,filename,False,100)
        return {"live":True,"download":saved,"content":read_file(store,item["id"],0,12000)}
    goto_learn(page,learn_url(item["url"],item["course_id"]))
    from .portal import wait_page
    wait_page(page)
    text=page.locator("body").inner_text()[:60000]
    if not text.strip() or item["title"].casefold() not in text.casefold():
        raise ValueError("The requested resource content did not finish loading.")
    observed=Item(native_id=item["native_id"],kind=item["kind"],title=item["title"],
        url=page.url,course_id=item["course_id"],course_title=item["course_title"],
        excerpt=item["title"],status="available")
    obs=observation(page.url,item["title"],[observed],"Observed Learn resource page; no forms submitted",extra_text=text)
    receipt=store.capture(obs)
    return {"live":True,"item_id":item["id"],"title":item["title"],"url":page.url,
        "text":text[:18000],"text_truncated":len(text)>18000,"coverage":"partial",
        "observation_id":receipt["observation_id"],"observed_at":obs.observed_at.isoformat(),
        "source_content_is_untrusted":True}


def execute_job(store: Store, job_id: str):
    path = job_path(store,job_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["worker_pid"] = os.getpid()
    def progress(message: str, state: str = "running"):
        record.update(state=state,progress=message,updated_at=now_utc().isoformat())
        write_json(path,record)
    try:
        action, args = record["action"], record["arguments"]
        progress("Waiting for the private school browser.")
        with browser_context(store,interactive=action == "login") as context:
            page = context.new_page()
            if action == "login":
                page.goto(LEARN_HOME,wait_until="domcontentloaded")
                progress("Complete the campus sign-in and MFA in the dedicated Chrome window. It closes after verification.",
                         "waiting_for_login")
                deadline = time.monotonic() + 900
                while time.monotonic() < deadline:
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
        record["result"] = result
        state = "needs_login" if result.get("needs_login") else "partial" if result.get("failed") or result.get("coverage") in {"partial","entry_only","external_provider","unavailable"} else "complete"
        progress("School operation finished.",state)
    except LoginRequired:
        if record["action"] in {"login","courses","resources","download","read_resource"}:
            mark_session(store,False)
        progress("Campus sign-in is required in this plugin's dedicated local browser. Use study_connect_school.","needs_login")
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
