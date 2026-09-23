from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LONDON = ZoneInfo("Europe/London")
Kind = Literal["course", "resource", "assignment", "event", "announcement", "service"]
Source = Literal["learn", "myed", "timetable", "library", "university"]
SENSITIVE_KEYS = re.compile(r"(token|secret|password|saml|assertion|session|signature|api.?key|authcode)", re.I)
SECRET_TEXT = re.compile(r"(?i)(authorization\s*:\s*bearer\s+\S+|(?:password|access_token|refresh_token|cookie)\s*[:=]\s*\S+)")
PRIMARY_HOSTS = {
    "learn": {"learn.ed.ac.uk", "www.learn.ed.ac.uk"},
    "myed": {"myed.ed.ac.uk", "www.myed.ed.ac.uk"},
}
SOURCE_HOSTS = {
    **PRIMARY_HOSTS,
    "timetable": {"myed.ed.ac.uk", "www.myed.ed.ac.uk", "outlook.office.com",
                  "outlook.office365.com", "browser.ted.is.ed.ac.uk", "timetabling.ed.ac.uk", "timetabler.is.ed.ac.uk"},
    "library": {"library.ed.ac.uk", "discovered.ed.ac.uk", "resourcelists.ed.ac.uk"},
}

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def normal(text: str) -> str:
    return " ".join(text.split()).casefold()

def clean_text(text: str) -> str:
    if SECRET_TEXT.search(text):
        raise ValueError("Credential-like text rejected. Capture only course/resource excerpts.")
    return text

def safe_url(value: str) -> str:
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Use an HTTPS content URL without credentials.")
    if any(SENSITIVE_KEYS.search(k) or k.lower() in {"code", "ticket"} for k, _ in parse_qsl(p.query)):
        raise ValueError("Authentication/session URLs must not be saved; use the content page URL.")
    if "/auth-saml/" in p.path or re.search(r"(?i)(token|access_token|samlresponse)=", p.fragment):
        raise ValueError("Authentication URLs must not be saved.")
    return value

def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp needs an explicit timezone offset; use Europe/London when reading Learn.")
    return value

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class LearnAttachment(StrictModel):
    """Stable DOM identity only; temporary transfer addresses never enter records."""
    parent_native_id: str = Field(pattern=r"^_\d+_\d+$", max_length=100)
    asset_id: str = Field(pattern=r"^_\d+_\d+$", max_length=100)
    resource_path: str = Field(pattern=r"^/bbcswebdav/pid-\d+-dt-content-rid-\d+_\d+/xid-\d+_\d+$", max_length=300)
    filename: str = Field(min_length=1, max_length=201)
    size_bytes: int = Field(gt=0, le=100*1024*1024)
    media_type: str = Field(min_length=1, max_length=150)

    @model_validator(mode="after")
    def identity(self):
        asset = self.asset_id.lstrip("_")
        if not self.resource_path.endswith("/xid-" + asset) or "-rid-" + asset + "/" not in self.resource_path:
            raise ValueError("Attachment asset identifiers disagree.")
        return self


class Item(StrictModel):
    native_id: str = Field(min_length=1, max_length=300)
    kind: Kind
    title: str = Field(min_length=1, max_length=500)
    url: str | None = None
    course_id: str | None = Field(default=None, max_length=300)
    course_title: str | None = Field(default=None, max_length=500)
    service_id: str | None = Field(default=None, max_length=100)
    attachment: LearnAttachment | None = None
    excerpt: str = Field(min_length=1, max_length=3000)
    due_at: datetime | None = None
    due_date: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: Literal["unknown", "available", "unavailable", "submitted", "graded", "cancelled"] = "unknown"

    @field_validator("url")
    @classmethod
    def url_check(cls, v):
        return safe_url(v) if v else v

    @field_validator("title", "excerpt")
    @classmethod
    def text_check(cls, v):
        return clean_text(v)

    @field_validator("due_at", "starts_at", "ends_at")
    @classmethod
    def time_check(cls, v):
        return aware(v) if v else v

    @field_validator("due_date")
    @classmethod
    def date_check(cls, v):
        if v is not None:
            from datetime import date
            if date.fromisoformat(v).isoformat() != v:
                raise ValueError("Use YYYY-MM-DD.")
        return v

    @model_validator(mode="after")
    def consistent(self):
        if self.attachment:
            parent = self.attachment.parent_native_id
            expected_path = f"/ultra/courses/{self.course_id}/document/{parent}"
            if (self.kind != "resource" or not self.url or urlsplit(self.url).path != expected_path
                    or self.native_id != parent + ":attachment:" + self.attachment.asset_id):
                raise ValueError("Attachment must retain its observed parent document and identity.")
        if self.due_at and self.due_date:
            raise ValueError("Use due_at for an exact time OR due_date when only the day is known.")
        if self.ends_at and (not self.starts_at or self.ends_at <= self.starts_at):
            raise ValueError("ends_at must follow starts_at.")
        return self

class Observation(StrictModel):
    source: Source
    source_url: str
    title: str = Field(min_length=1, max_length=500)
    observed_at: datetime
    scope: str = Field(min_length=1, max_length=500)
    coverage: Literal["partial", "complete_visible_scope"] = "partial"
    authentication: Literal["authenticated", "login_required", "unknown"] = "unknown"
    text: str = Field(min_length=1, max_length=100000)
    items: list[Item] = Field(default_factory=list, max_length=500)

    @field_validator("source_url")
    @classmethod
    def url_check(cls, v):
        return safe_url(v)

    @field_validator("observed_at")
    @classmethod
    def time_check(cls, v):
        aware(v)
        if v > now_utc() + timedelta(minutes=5):
            raise ValueError("Observation cannot be in the future.")
        return v

    @field_validator("text", "title", "scope")
    @classmethod
    def text_check(cls, v):
        return clean_text(v)

    @model_validator(mode="after")
    def evidence_check(self):
        from .services import content_url
        if self.source == "university":
            content_url(self.source_url)
        elif urlsplit(self.source_url).hostname not in SOURCE_HOSTS[self.source]:
            raise ValueError("The observation source must match a known Edinburgh service host.")
        if self.authentication == "login_required" and self.items:
            raise ValueError("A login page cannot prove course data or an empty account.")
        identifiers = [(i.kind, i.native_id) for i in self.items]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Duplicate item identity in one observation.")
        for item in self.items:
            if normal(item.excerpt) not in normal(self.text):
                raise ValueError("Each item excerpt must occur in the captured visible text.")
            if normal(item.title) not in normal(self.text):
                raise ValueError("Each item title must occur in the captured visible text.")
        return self
