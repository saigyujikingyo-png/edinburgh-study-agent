"""Direct course-file downloads. Signed URLs remain transient, outside metadata."""
from __future__ import annotations
import hashlib
import json
import os
import re
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import httpx
import logging
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
from .models import now_utc

ALLOWED_HOSTS = frozenset({"www.learn.ed.ac.uk", "learn.ed.ac.uk",
    "prod01-euc1-prod01-xythos.prod.files.blackboard.com"})
EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls",
              ".zip", ".csv", ".txt", ".md", ".ipynb"}
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}

def validate_download_url(url):
    try:
        p = urlsplit(url)
        valid = (p.scheme == "https" and p.hostname in ALLOWED_HOSTS and p.port in (None,443)
                 and not p.username and not p.password and not p.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Use HTTPS on an observed Learn file host, without userinfo or a fragment.")
    return url

def safe_filename(value):
    if not value or len(value)>200 or "/" in value or "\\" in value:
        raise ValueError("Use a filename without a directory, up to 200 characters.")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", value).strip().rstrip(". ")
    if not name or Path(name).suffix.lower() not in EXTENSIONS:
        raise ValueError("Unsupported course-file extension.")
    return "_" + name if name.split(".")[0].upper() in RESERVED else name

def verify_file(path, suffix, content_type):
    with path.open("rb") as stream:
        data = stream.read(1024)
    if not data:
        raise ValueError("The server returned an empty file.")
    if "text/html" in content_type or data.lstrip().lower().startswith((b"<!doctype html",b"<html")):
        raise ValueError("A web/login page was returned instead of a course file.")
    if suffix==".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("The content is not a PDF.")
    if suffix in {".xls",".ppt",".doc"} and not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise ValueError("The content is not the requested Office file type.")
    if suffix in {".xlsx",".pptx",".docx",".zip"}:
        if not zipfile.is_zipfile(path):
            raise ValueError("The content is not a valid Office/ZIP archive.")
        with zipfile.ZipFile(path) as archive:
            info = archive.infolist()
            if len(info)>10000 or sum(i.file_size for i in info)>500*1024*1024:
                raise ValueError("Archive expansion exceeds the verification limit.")
            names = set(archive.namelist())
            expected = {".xlsx":"xl/workbook.xml", ".docx":"word/document.xml", ".pptx":"ppt/presentation.xml"}
            if suffix in expected and (expected[suffix] not in names or "[Content_Types].xml" not in names):
                raise ValueError("The archive is not the requested Office document type.")
            if archive.testzip() is not None:
                raise ValueError("The file failed its integrity check.")

def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()

def list_downloads(store, item_id=None):
    with store.connection() as db:
        query, args = "SELECT payload FROM downloads", ()
        if item_id:
            query += " WHERE item_id=?"
            args = (item_id,)
        rows = db.execute(query+" ORDER BY downloaded_at DESC",args).fetchall()
    files = [json.loads(r["payload"]) for r in rows]
    for entry in files:
        entry["file_exists"] = Path(entry["path"]).is_file()
    return {"files":files, "signed_urls_stored":False}

def verified_copy(store,item_id,max_megabytes=100,filename=None):
    """Find a verified local copy without opening the campus browser."""
    for record in list_downloads(store,item_id)["files"]:
        path=Path(record["path"]).resolve()
        if not path.is_relative_to((store.root/"downloads").resolve()) or not path.is_file():
            continue
        if filename is not None and record["filename"]!=filename:
            continue
        if path.stat().st_size>max_megabytes*1024*1024 or digest_file(path)!=record["sha256"]:
            continue
        return {**record,"reused":True,"verified":True,"remote_freshness_checked":False,
                "signed_urls_stored":False,"save_dialog_required":False}
    return None


def download_resource(store, item_id, download_url, filename, refresh=False, max_megabytes=100, client=None):
    item = store.item(item_id)
    if item["kind"]!="resource":
        raise ValueError("Only an observed course resource can be downloaded.")
    name = safe_filename(filename) if filename is not None else None
    if not 1<=max_megabytes<=500:
        raise ValueError("max_megabytes must be 1..500.")
    url = validate_download_url(download_url)
    if not refresh and name is not None:
        cached=verified_copy(store,item_id,max_megabytes,name)
        if cached:
            return cached
    folder = store.root/"downloads"/re.sub(r"[^A-Za-z0-9_-]","_",item["course_id"] or "uncategorised")
    folder.mkdir(parents=True,exist_ok=True)
    temporary = folder/(".partial-"+uuid.uuid4().hex)
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60,connect=20),follow_redirects=False)
    try:
        for attempt in range(6):
            validate_download_url(url)
            with client.stream("GET",url,headers={"Accept":"*/*"}) as response:
                if response.status_code in {301,302,303,307,308}:
                    location = response.headers.get("location")
                    if not location or attempt==5:
                        raise ValueError("The download redirect chain could not be completed.")
                    url = validate_download_url(urljoin(url,location))
                    continue
                if response.status_code!=200:
                    raise ValueError(f"Download returned HTTP {response.status_code}; obtain a fresh address from the file page.")
                if name is None:
                    from email.message import Message
                    header=Message()
                    header["Content-Disposition"]=response.headers.get("content-disposition","")
                    name=safe_filename(header.get_filename() or "")
                expected = response.headers.get("content-length")
                if expected and int(expected)>max_megabytes*1024*1024:
                    raise ValueError("Course file exceeds the download size limit.")
                size = 0
                with temporary.open("xb") as stream:
                    for block in response.iter_bytes():
                        size += len(block)
                        if size>max_megabytes*1024*1024:
                            raise ValueError("Course file exceeds the download size limit.")
                        stream.write(block)
                if expected and not response.headers.get("content-encoding") and size!=int(expected):
                    raise ValueError("The file was incomplete; no partial file was retained.")
                verify_file(temporary,Path(name).suffix.lower(),response.headers.get("content-type",""))
                checksum = digest_file(temporary)
                destination = folder/(checksum[:16]+"-"+name)
                if destination.exists():
                    if digest_file(destination)!=checksum:
                        raise ValueError("An existing file differs and was preserved.")
                    temporary.unlink()
                else:
                    os.replace(temporary,destination)
                source = store.evidence(item["observation_id"])["observation"]["source_url"]
                record = {"item_id":item_id,"title":item["title"],"filename":name,"path":str(destination),
                    "size_bytes":size,"sha256":checksum,"source_page_url":source,
                    "downloaded_at":now_utc().isoformat()}
                with store.connection() as db:
                    db.execute("INSERT OR REPLACE INTO downloads VALUES(?,?,?,?)",
                        (item_id,checksum,record["downloaded_at"],json.dumps(record,ensure_ascii=False)))
                    store.audit(db,"download_resource",item_id)
                return {**record,"reused":False,"verified":True,"signed_urls_stored":False,"save_dialog_required":False}
        raise ValueError("Download redirect limit reached.")
    except httpx.HTTPError:
        raise ValueError("Course-file transfer failed; no partial file was retained. Refresh the source page and retry.") from None
    except (zipfile.BadZipFile,OSError):
        raise ValueError("The file could not be saved or verified; check local storage and retry.") from None
    finally:
        if temporary.exists():
            temporary.unlink()
        if own_client:
            client.close()
