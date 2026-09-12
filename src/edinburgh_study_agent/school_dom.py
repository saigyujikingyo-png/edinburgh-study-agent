"""DOM-only Learn adapter. No page application stores, credentials or screenshots."""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from .models import Item, Observation, now_utc, safe_url

LEARN_HOME = "https://www.learn.ed.ac.uk/ultra/course"
LEARN_HOSTS = {"learn.ed.ac.uk", "www.learn.ed.ac.uk"}
COURSE_ID = re.compile(r"^_\d+_\d+$")
CONTENT_PATH = re.compile(r"^/ultra/courses/(_\d+_\d+)/(file|document|assessment)/(_\d+_\d+)")
COURSE_CARDS = """() => [...document.querySelectorAll('a[id^="course-link-_"]')]
  .filter(a => /^course-link-_\\d+_\\d+$/.test(a.id) && a.innerText.trim())
  .map(a => ({native_id:a.id.slice(12),title:a.innerText.trim(),
    href:a.getAttribute('href'),details:a.parentElement.innerText.slice(0,2500),status:a.parentElement.querySelector('.course-status')?.innerText || ''}))"""
# One DOM operation gives a consistent row/slot snapshot and reveals a lazy row.
# Native instant scrolling does not wait for visual layout stability/animation frames.
COURSE_SCAN = """() => {
  const cards = [...document.querySelectorAll('a[id^="course-link-"]')];
  const pending = cards.find(a => a.id === 'course-link-');
  if (pending) pending.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
  return {rows:(""" + COURSE_CARDS + """)(), slots:cards.length};
}"""
RESOURCE_LINKS = """() => [...document.querySelectorAll('a[href]')]
  .filter(a => /\\/ultra\\/courses\\/_\\d+_\\d+\\/(file|document|assessment)\\/_\\d+_\\d+/.test(a.href) && a.innerText.trim())
  .map(a => ({title:a.innerText.trim(),url:a.href}))"""
EXPANDERS = """() => [...document.querySelectorAll('button[aria-expanded="false"][id]')]
  .filter(b => /^(learning-module-title-|folder-title-)_\\d+_\\d+$/.test(b.id) && b.getClientRects().length)
  .map(b => ({id:b.id,title:b.innerText.trim()}))"""


def learn_url(url: str, course_id: str | None = None) -> str:
    safe_url(url)
    parsed = urlsplit(url)
    if parsed.hostname not in LEARN_HOSTS:
        raise ValueError("Only observed Learn content pages are supported.")
    if course_id and not parsed.path.startswith("/ultra/courses/" + course_id + "/"):
        raise ValueError("Content must belong to the requested course.")
    return url


def course_items(rows: list[dict]) -> list[Item]:
    items = {}
    for row in rows:
        native_id, title = row.get("native_id", ""), row.get("title", "").strip()
        if not COURSE_ID.fullmatch(native_id) or not title:
            continue
        details = row.get("status", "") + " " + row.get("details", "")
        status = "unknown"
        if re.search(r"when your instructor opens|\bclosed\b|not available", details, re.I):
            status = "unavailable"
        elif re.search(r"\bopen\b", details, re.I):
            status = "available"
        href = row.get("href") or ""
        try:
            url = learn_url(href, native_id) if href.startswith("https://") else None
        except ValueError:
            url = None
        items[native_id] = Item(native_id=native_id, kind="course", title=title[:500],
            url=url, course_id=native_id, course_title=title[:500], excerpt=title[:500], status=status)
    return list(items.values())


def resource_items(rows: list[dict], course: dict) -> list[Item]:
    items = {}
    for row in rows:
        try:
            url = learn_url(row["url"], course["native_id"])
            match = CONTENT_PATH.match(urlsplit(url).path)
            title = row["title"].strip()
            if not match or not title:
                continue
            kind = "assignment" if match[2] == "assessment" else "resource"
            item = Item(native_id=match[3],kind=kind,title=title[:500],url=url,
                        course_id=course["native_id"],course_title=course["title"],
                        excerpt=title[:500],status="available")
            items[(kind,item.native_id)] = item
        except (ValueError, KeyError):
            continue
    return list(items.values())


def observation(page_url: str, title: str, items: list[Item], scope: str,
                complete: bool = False, extra_text: str = "") -> Observation:
    # Every excerpt is actual DOM text. Combining visible reads records an explicit traversal scope.
    text = "\n".join([title, extra_text] + [i.excerpt for i in items]).strip()
    return Observation(source="learn",source_url=learn_url(page_url),title=title[:500],
        observed_at=now_utc(),scope=scope[:500],
        coverage="complete_visible_scope" if complete else "partial",
        authentication="authenticated",text=text[:100000],items=items)
