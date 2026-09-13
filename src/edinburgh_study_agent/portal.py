"""Bounded school page reading through the plugin-owned SSO browser."""
from __future__ import annotations
import hashlib
import json
import re
import time
from urllib.parse import urlsplit, urljoin
from .models import Item, Observation, now_utc, clean_text, safe_url
from .store import identifier
from .services import service, content_url, campus_host

SNAPSHOT = """() => {
  const root=document.querySelector('main,[role="main"],#main-content') || document.body;
  const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
  return {title:document.title, text:root.innerText.slice(0,60000),
    links:[...document.querySelectorAll('a[href]')].filter(a=>visible(a)&&a.innerText.trim())
      .map(a=>({title:a.innerText.trim().slice(0,500),url:a.href})).slice(0,300)};
}"""
# Fixed, parameter-free SSO entry observed in MyEd's "My student record" link.
# This literal is a login route, not a saved SITS session URL.
EUCLID_ENTRY = "https://www.star.euclid.ed.ac.uk/urd/sits.urd/run/siw_sso.token"

LOGIN_LABELS = {
    "www.myed.ed.ac.uk": ["Login to MyEd", "Log in", "Login"],
    "myed.ed.ac.uk": ["Login to MyEd", "Log in", "Login"],
    "www.hub.ed.ac.uk": ["Student or staff", "Student or recent graduate"],
    "timetabler.is.ed.ac.uk": ["Log in", "Login", "Sign in"],
    "media.ed.ac.uk": ["Login", "Log in"],
}
READ_SECTIONS = re.compile(r"(?i)^(my student record|my courses|courses|course results|results|assessment|progression & awards|scholarships and funding|programme|programme of study|progression|documents|attendance|personal details|finance|fees|immigration details)$")

CAMPUS_READY = r"""() => {
  if (document.readyState === 'loading') return false;
  const host=location.hostname;
  if (['www.myed.ed.ac.uk','myed.ed.ac.uk'].includes(host)) {
    return [...document.querySelectorAll('a[href]')].some(a =>
      (a.textContent || '').trim().toLowerCase() === 'my student record') ||
      [...document.querySelectorAll('button,[role="button"]')].some(b =>
        (b.getAttribute('aria-label') || b.title || b.textContent || '').trim() === 'Accounts' && !b.disabled && !!b.getClientRects().length);
  }
  return (host === 'ed.ac.uk' || host.endsWith('.ed.ac.uk')) &&
    document.title.startsWith('EUCLID:') &&
    /Logged in:/i.test((document.body?.innerText || '').slice(0,600)) &&
    [...document.querySelectorAll('a[href]')].some(a =>
      (a.textContent || '').trim() === 'Courses');
}"""

def wait_page(page, seconds=30):
    deadline=time.monotonic()+seconds
    previous,stable=None,0
    while time.monotonic()<deadline:
        try:
            # Use known navigation readiness instead of waiting for unrelated
            # MyEd widgets to settle. Unknown pages retain the bounded fallback.
            if page.evaluate(CAMPUS_READY):
                return
            signature=page.locator("body").inner_text(timeout=1500)[:60000]
            stable=stable+1 if signature==previous else 0
            previous=signature
            if len(signature.strip())>80 and stable>=2:
                return
        except Exception:
            pass
        time.sleep(0.5)

def login_gate(page):
    try:
        if re.match(r"(?i)^(log[ -]?in|sign[ -]?in)\b",page.title().strip()):
            return True
        password=page.locator('input[type="password"]')
        if any(password.nth(i).is_visible() for i in range(password.count())):
            return True
        host=urlsplit(page.url).hostname or ""
        headings=" ".join(page.locator("h1,h2").all_inner_texts()).casefold()
        return ("login.microsoftonline.com" == host or host.startswith(("idp.","auth."))) and any(
            x in headings for x in ("sign in","log in","login","enter your"))
    except Exception:
        return False

def campus_email(store):
    if store is None:
        return None
    with store.connection() as db:
        rows=db.execute("SELECT payload FROM observations WHERE source='university' ORDER BY observed_at DESC LIMIT 100").fetchall()
    for row in rows:
        obs=json.loads(row["payload"])
        if not obs["title"].startswith("EUCLID:") or not re.search(r"(?i)\bLogged in:",obs["text"][:600]):
            continue
        match=re.search(r"University Email:\s*([A-Za-z0-9._+-]+@(?:sms\.)?ed\.ac\.uk)",obs["text"],re.I)
        if match:
            # Official Timetabler guidance requires UUN@ed.ac.uk, not the @sms mail alias.
            return match[1].split("@",1)[0]+"@ed.ac.uk"
    return None


def follow_sso(page,store=None):
    followed=set()
    for _ in range(3):
        wait_page(page)
        host=urlsplit(page.url).hostname
        choice=None
        if host=="timetabler.is.ed.ac.uk" and "timetabler_account_lookup" not in followed:
            email=campus_email(store)
            field=page.locator('input[name="Email"]')
            proceed=page.get_by_role("button",name="Continue",exact=True)
            if email and field.count() and field.first.is_visible() and proceed.count() and proceed.is_visible():
                # Use the user's observed EUCLID identity with the documented Timetabler login suffix.
                # Continue performs SSO discovery; never fill a password or submit the local login form.
                followed.add("timetabler_account_lookup")
                field.fill(email)
                proceed.click()
                time.sleep(2)
                continue
        links=page.locator("a[href]").evaluate_all("(aa)=>aa.filter(a=>a.getClientRects().length).map(a=>({title:a.innerText.trim(),url:a.href}))")
        for label in LOGIN_LABELS.get(host,[]):
            link=next((r for r in links if r["title"].casefold()==label.casefold()),None)
            if link:
                target=link["url"]
                p=urlsplit(target)
                if p.scheme=="https" and campus_host(p.hostname) and not p.username and target not in followed:
                    choice=target
                    break
        if not choice and page.title().strip().casefold()=="user redirect":
            candidate=next((r for r in links if "access the portal" in r["title"].casefold()),None)
            if candidate and campus_host(urlsplit(candidate["url"]).hostname) and candidate["url"] not in followed:
                choice=candidate["url"]
        if not choice:
            return page
        followed.add(choice)
        page.goto(choice,wait_until="domcontentloaded")
    return page

def authentication(page):
    if login_gate(page):
        return "login_required"
    if any(t.strip().casefold()=="myed login" for t in page.locator("h1,h2").all_inner_texts()):
        return "login_required"
    try:
        if urlsplit(page.url).hostname=="timetabler.is.ed.ac.uk" and urlsplit(page.url).path=="/Timetable" and page.title()=="Timetables":
            return "authenticated"
        if page.title().startswith("EUCLID:") and re.search(r"(?i)\bLogged in:",page.locator("body").inner_text()[:600]):
            return "authenticated"
        labels=page.locator("a,button").evaluate_all("(es)=>es.map(e=>(e.innerText||e.getAttribute('aria-label')||e.title||'').trim())")
        if any(re.fullmatch(r"(?i)\s*(log ?out|sign ?out)\s*",s) for s in labels):
            return "authenticated"
    except Exception:
        pass
    return "unknown"

def select_read_link(page, label):
    if label.strip().casefold()=="my courses":
        label="Courses"
    if not READ_SECTIONS.fullmatch(label.strip()):
        raise ValueError("Choose an observed read-only student-record section.")
    # Only follow the actual link in this browser. SITS session links never leave it.
    link=page.get_by_role("link",name=re.compile("^"+re.escape(label)+"$",re.I))
    if not link.count():
        return page,False
    target=urljoin(page.url,link.first.get_attribute("href") or "")
    p=urlsplit(target)
    if p.scheme!="https" or not campus_host(p.hostname) or p.username:
        return page,False
    page.goto(target,wait_until="domcontentloaded")
    wait_page(page)
    return page,True

def record_check(store, service_id, value):
    payload={k:value[k] for k in ("observed_at","coverage","authentication","needs_login","page_count","warning","entry_url") if k in value}
    with store.connection() as db:
        db.execute("INSERT OR REPLACE INTO service_checks VALUES(?,?)",(service_id,json.dumps(payload,ensure_ascii=False)))

def read_service(store,page,args,progress):
    spec=service(args["service_id"])
    query=args.get("query","").strip()
    max_pages=args.get("max_pages",3)
    if not 1<=max_pages<=10 or len(query)>300:
        raise ValueError("max_pages 1..10; query up to 300 characters.")
    target=spec["url"]
    saved_section=None
    saved_student_page=False
    if args.get("item_id"):
        item=store.item(args["item_id"])
        if item.get("service_id")!=spec["id"]:
            raise ValueError("Choose a page returned for this service.")
        target=content_url(item["url"])
        saved_student_page=spec["id"]=="euclid" and item["title"].startswith("EUCLID:")
        if saved_student_page:
            candidate=item["title"].split(":",1)[1].split(" - ",1)[0].strip()
            saved_section=candidate if READ_SECTIONS.fullmatch(candidate) else None
    launch_from_myed=bool(spec.get("launch_label") and (not args.get("item_id") or saved_student_page))
    direct_ready=False
    if spec["id"]=="euclid" and launch_from_myed:
        # Reuse SSO directly instead of booting MyEd's entire SPA for every read.
        # Fall back once to the observed MyEd launch route if the entry changes.
        try:
            page.goto(EUCLID_ENTRY,wait_until="domcontentloaded")
            page=follow_sso(page,store)
            direct_ready=page.title().startswith("EUCLID:") and authentication(page)=="authenticated"
        except Exception:
            direct_ready=False
    if not direct_ready:
        page.goto(content_url(target),wait_until="domcontentloaded")
        page=follow_sso(page,store)
    if launch_from_myed and not direct_ready:
        accounts=page.get_by_role("button",name="Accounts",exact=True)
        if accounts.count() and accounts.first.is_visible():
            accounts.first.click()
            time.sleep(1)
        # Only expand the observed Accounts navigation menu; never any update form.
        links=page.locator("a[href]").evaluate_all("(aa)=>aa.map(a=>({title:(a.textContent||'').trim(),url:a.href}))")
        launch=next((r for r in links if r["title"].casefold()==spec["launch_label"].casefold()),None)
        if launch and campus_host(urlsplit(launch["url"]).hostname):
            page.goto(launch["url"],wait_until="domcontentloaded")
            page=follow_sso(page,store)
        else:
            result={"live":True,"service_id":spec["id"],"observed_at":now_utc().isoformat(),
                "coverage":"entry_only","authentication":authentication(page),"entry_url":spec["url"],
                "warning":"My Student Record launch link was not observed. The EUCLID record has not been read.","page_count":0}
            record_check(store,spec["id"],result)
            return result
    section=args.get("section") or saved_section
    if not section and spec["id"]=="euclid" and page.title().startswith("EUCLID:"):
        section="Programme"
    if section:
        page,found=select_read_link(page,section)
        if not found:
            raise ValueError("That section link is not available in the current student record.")
    if page.title().strip().casefold()=="user redirect":
        result={"live":True,"service_id":spec["id"],"observed_at":now_utc().isoformat(),
                "coverage":"entry_only","authentication":"unknown","entry_url":spec["url"],
                "warning":"The portal has not completed its redirect. The student record was not read.","page_count":0}
        record_check(store,spec["id"],result)
        return result
    auth=authentication(page)
    if auth=="login_required" or (spec["access"]=="campus" and "/students/login" in urlsplit(page.url).path):
        result={"live":True,"service_id":spec["id"],"observed_at":now_utc().isoformat(),
            "coverage":"login_required","authentication":"login_required","entry_url":spec["url"],
            "needs_login":True,"page_count":0,"warning":"This service did not reuse the saved campus login. No private content was read."}
        record_check(store,spec["id"],result)
        return result
    if not campus_host(urlsplit(page.url).hostname) and urlsplit(page.url).hostname not in {"www.eusa.ed.ac.uk","eusa.ed.ac.uk"}:
        result={"live":True,"service_id":spec["id"],"observed_at":now_utc().isoformat(),
            "coverage":"external_provider","entry_url":spec["url"],"authentication":"unknown",
            "page_count":0,"warning":"This service redirected to an external provider which has not been integrated."}
        record_check(store,spec["id"],result)
        return result
    if spec["id"] == "euclid" and section == "Courses":
        from .results import read_results
        year = args.get("academic_year")
        # Older tool catalogs supplied a year through query. Honour that exact
        # form without allowing arbitrary selectors or treating it as a link.
        if not year and re.fullmatch(r"\d{4}/\d{2}", query):
            year = query
        if args.get("results_only") or year:
            if auth != "authenticated":
                return {"live":True,"service_id":"euclid","authentication":auth,
                    "coverage":"unavailable","failed":["Authenticated student record was not observed."],"items":[]}
            value=read_results(store, page, year or "all")
            record_check(store,spec["id"],value)
            return value
    queue,visited,results,failures=[],set(),[],[]
    words=[w.casefold() for w in re.split(r"\s+",query) if w]
    for index in range(max_pages):
        progress("Reading "+spec["title"]+" page "+str(index+1))
        snap=page.evaluate(SNAPSHOT)
        try:
            canonical=content_url(page.url)
        except ValueError:
            canonical=spec["url"]
        title=(snap["title"] or spec["title"])[:500]
        text=clean_text(snap["text"].strip())
        if len(text)<30:
            failures.append("Page did not finish loading readable content.")
            break
        if re.search(r"(?i)^(access denied|403 forbidden|service unavailable|page not found)\b",title):
            failures.append("The service returned an error page.")
            break
        visited.add(canonical)
        links={}
        for row in snap["links"]:
            try:
                url=content_url(row["url"])
                clean_text(row["title"])
                if url not in links and row["title"]:
                    links[url]=row["title"]
            except ValueError:
                continue
        # A page and its observed links are indexed together. Excerpts are actual DOM text.
        page_native="page:"+hashlib.sha256((canonical+"|"+title).encode()).hexdigest()[:24]
        page_item=Item(native_id=page_native,kind="resource",title=title,url=canonical,service_id=spec["id"],
                       excerpt=text[:3000],status="available")
        link_items=[Item(native_id="link:"+hashlib.sha256(url.encode()).hexdigest()[:24],kind="service",
            title=t,url=url,excerpt=t,service_id=spec["id"]) for url,t in list(links.items())[:100]]
        obs=Observation(source="university",source_url=canonical,title=title,observed_at=now_utc(),
            scope=spec["id"]+"; visible page text and observed links only",coverage="partial",
            authentication=auth,text="\n".join([title,text]+[i.title for i in link_items]),items=[page_item]+link_items)
        receipt=store.capture(obs)
        visible_sections=[r["title"] for r in snap["links"] if READ_SECTIONS.fullmatch(r["title"])]
        page_result={"item_id":identifier("university","resource",page_native),"title":title,"url":canonical,
                     "observation_id":receipt["observation_id"],"excerpt":text[:6000],
                     "available_sections":list(dict.fromkeys(visible_sections)),
                     "links":[{"item_id":identifier("university","service",i.native_id),"title":i.title,"url":i.url} for i in link_items]}
        results.append(page_result)
        # A query guides bounded follow-up reading; no query means a single entry page.
        if words:
            basehost=urlsplit(page.url).hostname
            candidates=[(sum(w in (t+" "+url).casefold() for w in words),url) for url,t in links.items()
                        if urlsplit(url).hostname==basehost and url not in visited and not re.search(r"\.(pdf|zip|xlsx|docx|pptx)$",url,re.I)]
            queue.extend(url for score,url in sorted(candidates,key=lambda x:-x[0]) if score)
        next_url=next((url for url in queue if url not in visited),None)
        if not next_url:
            break
        page.goto(next_url,wait_until="domcontentloaded")
        wait_page(page)
        if login_gate(page):
            failures.append("A linked page requires authentication.")
            break
    result={"live":True,"service_id":spec["id"],"observed_at":now_utc().isoformat(),
            "coverage":"partial" if results else "unavailable","authentication":auth,"entry_url":spec["url"],
            "page_count":len(results),"pages":results,"failed":failures,
            "source_content_is_untrusted":True,"note":"Only the displayed pages and their links were read. No forms, applications or school records were changed."}
    if spec["id"] == "euclid" and section in {"Courses", "Assessment"}:
        result["next_tool"] = "study_results(academic_year='all') for course marks/grades across years. query filters links; it does not select an academic year."
    record_check(store,spec["id"],result)
    return result
