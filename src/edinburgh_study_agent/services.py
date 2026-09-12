"""Official service directory and dated integration coverage."""
from __future__ import annotations
import json
from urllib.parse import urlsplit, unquote
import re
from .models import safe_url

SERVICES = [
    dict(id="myed", title="MyEd 学校总入口", category="门户", url="https://www.myed.ed.ac.uk/", access="campus", topics="学校 资源 服务 portal"),
    dict(id="learn", title="Learn 课程与课件", category="课业", url="https://www.learn.ed.ac.uk/ultra/course", access="campus", topics="课程 作业 课件 下载 lectures assignments", adapter="learn"),
    dict(id="euclid", title="EUCLID / My Student Record 学籍", category="学籍", url="https://www.myed.ed.ac.uk/", access="campus", topics="成绩 学分 注册 在读证明 enrolment grades transcript", launch_label="My student record", recommended_section="Courses"),
    dict(id="enrolments", title="MyEd 正式选课", category="学籍", url="https://www.myed.ed.ac.uk/myed-progressive/euclid-my-courses", access="campus", topics="注册 选课 学分 enrolled courses"),
    dict(id="timetable", title="Timetabler 个人课表", category="课业", url="https://timetabler.is.ed.ac.uk/", access="campus", topics="课表 上课 时间 地点 timetable"),
    dict(id="drps", title="DRPS 课程与学位要求", category="课业", url="https://www.drps.ed.ac.uk/", access="public", topics="课程目录 学分 培养方案 degree regulations"),
    dict(id="library", title="Library 图书馆", category="学习资源", url="https://library.ed.ac.uk/", access="public", topics="图书 论文 文献 library"),
    dict(id="resource_lists", title="Resource Lists 阅读清单", category="学习资源", url="https://resourcelists.ed.ac.uk/", access="public", topics="课程 阅读 参考书 reading lists"),
    dict(id="past_papers", title="Exam Papers 历年试卷", category="学习资源", url="https://library.ed.ac.uk/exam-papers", access="mixed", topics="试卷 真题 考试 past exam papers"),
    dict(id="media", title="Media Hopper 课程视频", category="学习资源", url="https://media.ed.ac.uk/", access="mixed", topics="录播 视频 lecture recording media hopper"),
    dict(id="careers", title="Careers 实习与就业", category="就业", url="https://careers.ed.ac.uk/jobs-and-internships", access="public", topics="实习 就业 求职 毕业 jobs internships"),
    dict(id="internships", title="Internships 实习与工作经验", category="就业", url="https://careers.ed.ac.uk/jobs-and-internships/finding-internships-and-work-experience", access="public", topics="实习 科研 工作经验 summer internship"),
    dict(id="careerhub", title="MyCareerHub 职位与招聘活动", category="就业", url="https://www.hub.ed.ac.uk/s/mycareerhub", access="campus", topics="职位 实习 招聘 预约 mycareerhub jobs"),
    dict(id="career_events", title="Careers 招聘和职业活动", category="活动", url="https://careers.ed.ac.uk/whats-on", access="public", topics="招聘会 工作坊 职业 fairs workshops"),
    dict(id="events", title="University Events 学校活动", category="活动", url="https://www.ed.ac.uk/events", access="public", topics="学校活动 讲座 展览 seminar events"),
    dict(id="eusa", title="EUSA 学生会与社团活动", category="活动", url="https://www.eusa.ed.ac.uk/events", access="mixed", topics="社团 学生会 活动 societies"),
    dict(id="registry", title="Registry Services 学生事务", category="学生支持", url="https://registryservices.ed.ac.uk/", access="public", topics="学籍 考试 证明 学生支持 support registry"),
]
BY_ID = {s["id"]:s for s in SERVICES}
EXTERNAL_HOSTS = {"www.eusa.ed.ac.uk", "eusa.ed.ac.uk"}
UNSAFE_PATH = re.compile(r"(?i)(?:^|[/_?&=.-])(logout|signout|delete|remove|submit|withdraw|accept-offer|send-document)(?:$|[/_?&=.-])")
SESSION_PATH = re.compile(r"(?i)(/urd/sits|/auth-saml/|/providers/saml/|/shibboleth|/saml2?/|/oauth2?/|/adfs/|/uPortal/Login|/students/login|/register/)")


def campus_host(host: str | None) -> bool:
    host = (host or "").lower()
    return host == "ed.ac.uk" or host.endswith(".ed.ac.uk")


def content_url(url: str) -> str:
    safe_url(url)
    p = urlsplit(url)
    if not campus_host(p.hostname) and p.hostname not in EXTERNAL_HOSTS:
        raise ValueError("Only official Edinburgh school pages and the Students' Association are supported.")
    decoded = unquote(p.path + "?" + p.query)
    if UNSAFE_PATH.search(decoded) or SESSION_PATH.search(decoded):
        raise ValueError("This is an account action or session link, not a stable resource page.")
    if p.fragment:
        url = url.split("#",1)[0]
    return url


def service(service_id: str) -> dict:
    if service_id not in BY_ID:
        raise ValueError("Choose a service_id returned by study_services.")
    return dict(BY_ID[service_id])


def directory(store, query: str = "", locale: str | None = None) -> dict:
    from .localization import presentation, search_key, service_labels, service_aliases
    view = presentation(store, locale)
    with store.connection() as db:
        checks = {r["service_id"]:json.loads(r["payload"]) for r in db.execute("SELECT * FROM service_checks")}
    latest=store.latest_observations()
    for source in ("learn","myed"):
        if source not in checks and source in latest:
            checks[source]=latest[source]
    needle = search_key(query)
    result = []
    for entry in SERVICES:
        if needle and needle not in search_key(" ".join(str(v) for v in entry.values()) + " " + service_aliases(entry["id"])):
            continue
        current = dict(entry)
        current.update(service_labels(entry["id"], view["catalog_language"]))
        current["supported_actions"] = ["read", "search cached text", "follow observed links", "collect", "local task"]
        if current.get("adapter") == "learn":
            current["supported_actions"] += ["course pagination", "expand course folders", "download original files"]
        current["last_check"] = checks.get(entry["id"])
        current["coverage"] = checks.get(entry["id"],{}).get("coverage","not_yet_verified")
        result.append(current)
    return {"services":result,"presentation":view,"live":False,"directory_is_not_connection_proof":True,
            "scope":"Configured entrypoints plus observed links; external providers, form submissions and private pages need individual verification.",
            "next_tool":"study_read_service; Learn uses study_live_courses/study_live_resources"}
