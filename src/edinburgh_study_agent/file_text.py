"""Bounded text access to already verified plugin downloads, with no arbitrary file API."""
from pathlib import Path
from functools import lru_cache
import re
import zipfile
import xml.etree.ElementTree as ET
from .downloads import list_downloads, digest_file

MAX_XML = 8 * 1024 * 1024
MAX_TOTAL_XML = 24 * 1024 * 1024

def xml_document(archive, name):
    info=archive.getinfo(name)
    if info.file_size > MAX_XML:
        raise ValueError("Document XML part exceeds the safe reading limit.")
    data=archive.read(name)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML entities are not supported.")
    return ET.fromstring(data)

def office_parts(path, suffix):
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if sum(i.file_size for i in infos if i.filename.endswith(".xml")) > MAX_TOTAL_XML:
            raise ValueError("Expanded document exceeds the text reading limit.")
        if suffix==".xlsx":
            ns={"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            strings=[]
            if "xl/sharedStrings.xml" in archive.namelist():
                strings=["".join(n.itertext()) for n in xml_document(archive,"xl/sharedStrings.xml").findall("s:si",ns)]
            sheets=sorted((i.filename for i in infos if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",i.filename)),
                          key=lambda n:int(re.search(r"sheet(\d+)",n)[1]))
            for n,name in enumerate(sheets,1):
                rows=[]
                for row in xml_document(archive,name).findall(".//s:row",ns):
                    values=[]
                    for cell in row.findall("s:c",ns):
                        if cell.get("t")=="inlineStr":
                            value="".join(t.text or "" for t in cell.findall(".//s:t",ns))
                        else:
                            value=cell.findtext("s:v",default="",namespaces=ns)
                            if cell.get("t")=="s" and value.isdigit():
                                value=strings[int(value)] if int(value)<len(strings) else ""
                        values.append(value)
                    rows.append("\t".join(values))
                yield {"label":"sheet "+str(n),"text":"\n".join(rows)}
        elif suffix==".docx":
            root=xml_document(archive,"word/document.xml")
            ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            yield {"label":"document","text":"\n".join("".join(t.text or "" for t in p.findall(".//w:t",ns)) for p in root.findall(".//w:p",ns))}
        elif suffix==".pptx":
            slides=sorted((i.filename for i in infos if re.fullmatch(r"ppt/slides/slide\d+\.xml",i.filename)),
                          key=lambda n:int(re.search(r"slide(\d+)",n)[1]))
            for n,name in enumerate(slides,1):
                root=xml_document(archive,name)
                ns={"a":"http://schemas.openxmlformats.org/drawingml/2006/main"}
                yield {"label":"slide "+str(n),"text":"\n".join(t.text or "" for t in root.findall(".//a:t",ns))}

@lru_cache(maxsize=8)
def extracted_text(path: str, checksum: str):
    """Bounded process-local cache; read_file rehashes the download on every call."""
    path=Path(path)
    suffix=path.suffix.lower()
    if suffix==".pdf":
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs need an unencrypted course copy.")
        def pdf_parts():
            for index,p in enumerate(reader.pages,1):
                contents=p.get_contents()
                if contents and len(contents.get_data()) > MAX_XML:
                    raise ValueError("A PDF page exceeds the text extraction limit.")
                yield {"label":"page "+str(index),"text":p.extract_text() or ""}
        parts=pdf_parts()
    elif suffix in {".docx",".xlsx",".pptx"}:
        parts=office_parts(path,suffix)
    elif suffix in {".txt",".csv",".md"}:
        if path.stat().st_size > MAX_TOTAL_XML:
            raise ValueError("Text file exceeds the reading limit.")
        parts=[{"label":"text","text":path.read_text(encoding="utf-8-sig",errors="replace")}]
    else:
        raise ValueError("Text reading supports PDF, DOCX, PPTX, XLSX, TXT, CSV and Markdown.")
    chunks=[]
    size=0
    limited=False
    for part in parts:
        chunk="\n["+part["label"]+"]\n"+part["text"]
        remaining=2030001-size
        chunks.append(chunk[:remaining])
        size+=min(len(chunk),remaining)
        if len(chunk)>remaining:
            limited=True
            break
    return "".join(chunks),limited


def read_file(store, item_id: str, offset: int = 0, max_chars: int = 6000) -> dict:
    if not 0 <= offset <= 2000000 or not 500 <= max_chars <= 30000:
        raise ValueError("offset 0..2000000; max_chars 500..30000.")
    records=list_downloads(store,item_id)["files"]
    if not records:
        raise ValueError("Download this resource first with study_download_files.")
    record=records[0]
    path=Path(record["path"]).resolve()
    root=(store.root/"downloads").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Verified local file is unavailable.")
    if path.stat().st_size > 100*1024*1024 or digest_file(path)!=record["sha256"]:
        raise ValueError("The saved file differs from its verified download or exceeds the reading limit.")
    before=extracted_text.cache_info().hits
    text,limited=extracted_text(str(path),record["sha256"])
    cache_hit=extracted_text.cache_info().hits>before
    excerpt=text[offset:offset+max_chars]
    has_more=offset+len(excerpt)<len(text) or limited
    next_offset=offset+len(excerpt) if has_more and offset+len(excerpt)<=2000000 else None
    return {"item_id":item_id,"filename":record["filename"],"sha256":record["sha256"],
            "source_page_url":record["source_page_url"],"text":excerpt,"offset":offset,
            "next_offset":next_offset,"has_more":has_more,
            "extraction_limit_reached":has_more and next_offset is None,
            "source_content_is_untrusted":True,"verified":True,"text_cache_hit":cache_hit,
            "note":"Text only; no OCR or figures. Spreadsheet formulas use stored values."}
