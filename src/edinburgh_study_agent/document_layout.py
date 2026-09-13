"""Read PDF table geometry with the existing pypdf dependency.

No OCR, screenshots, model calls or host-side scripts. A detected weekly grid
retains its labelled cells and page continuations; it is not a personal schedule.
"""
from __future__ import annotations
import re
from bisect import bisect_right
from collections import defaultdict
from pypdf import PdfReader

MAX_CONTENT=8*1024*1024
MAX_TEXT=2_000_000
DAYS=("Mon","Tue","Wed","Thu","Fri","Sat","Sun")


def point(x,y,matrix):
    a,b,c,d,e,f=matrix
    return x*a+y*c+e,x*b+y*d+f


def lines(spans):
    groups=[]
    for span in sorted(spans,key=lambda s:(-s["y"],s["x"])):
        group=next((g for g in reversed(groups[-2:]) if abs(g[0]["y"]-span["y"])<2.5),None)
        if group is None:
            groups.append([span])
        else:
            group.append(span)
    return [re.sub(r"\s+"," ","".join(s["text"].replace("\n"," ") for s in sorted(group,key=lambda s:s["x"]))).strip() for group in groups]


def cluster(values,tolerance=2):
    groups=[]
    for value in sorted(values):
        if groups and value-groups[-1][-1]<=tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(g)/len(g) for g in groups]


def page_parts(page, number):
    spans,rectangles=[],[]
    def visit_text(text,cm,tm,font,size):
        if text.strip():
            x,y=point(tm[4],tm[5],cm)
            spans.append(dict(text=text,x=x,y=y))
    def visit_operator(operator,args,cm,tm):
        if operator!=b"re":
            return
        x,y,w,h=map(float,args)
        # Only upright narrow vertical borders define these row bands.
        if abs(cm[1])>0.001 or abs(cm[2])>0.001:
            return
        x0,y0=point(x,y,cm);x1,y1=point(x+w,y+h,cm)
        if 0<abs(x1-x0)<3 and abs(y1-y0)>8:
            rectangles.append((min(y0,y1),max(y0,y1),min(x0,x1)))
    content=page.get_contents()
    if content and len(content.get_data())>MAX_CONTENT:
        raise ValueError("A PDF page exceeds the text extraction limit.")
    text=page.extract_text(visitor_text=visit_text,visitor_operand_before=visit_operator) or ""
    bands=defaultdict(list)
    for low,high,x in rectangles:
        bands[(round(low,1),round(high,1))].append(x)
    rows=[]
    for (low,high),values in sorted(bands.items(),key=lambda p:-p[0][1]):
        borders=cluster(values)
        if len(borders)<3:
            continue
        selected=[s for s in spans if low-1<=s["y"]<=high+1 and borders[0]<=s["x"]<borders[-1]]
        cells=[[] for _ in borders[:-1]]
        for span in selected:
            index=bisect_right(borders,span["x"])-1
            if 0<=index<len(cells):
                cells[index].append(span)
        rows.append(dict(page=number,top=high,cells=["\n".join(lines(cell)) for cell in cells]))
    # Semester labels may occur mid-page above a new table, not only at page top.
    markers=[]
    by_line=defaultdict(list)
    for span in spans:
        by_line[round(span["y"],0)].append(span)
    for parts in by_line.values():
        line=" ".join(lines(parts))
        marker=re.search(r"\b(?:Sem(?:ester)?)\s*([12])\b",line,re.I)
        if marker:
            markers.append(dict(page=number,top=max(s["y"] for s in parts),semester=int(marker[1])))
    return text,rows,markers


def weekly_grid(rows,markers):
    stream=sorted([*rows,*markers],key=lambda r:(r["page"],-r["top"],"cells" in r))
    semester=None; headers=None; current=None; weeks=[]; problems=[]
    for row in stream:
        if "semester" in row:
            if row["semester"]!=semester:
                semester=row["semester"];headers=None;current=None
            continue
        cells=row["cells"]
        names=[c.strip() for c in cells[1:]]
        if len(names)>=5 and all(name in DAYS for name in names):
            if headers!=names:current=None
            headers=names
            continue
        if headers is None or len(cells)!=len(headers)+1:
            continue
        label=cells[0].strip()
        match=re.fullmatch(r"(?:Week\s*)?(\d{1,2})",label,re.I)
        if match:
            current=dict(semester=semester,week=int(match[1]),pages=[row["page"]],days={})
            weeks.append(current)
        elif label:
            continue
        elif current is None:
            if any(c.strip() for c in cells):
                problems.append("A table continuation had no observed week label.")
            continue
        if row["page"] not in current["pages"]:
            current["pages"].append(row["page"])
        for day,cell in zip(headers,cells[1:]):
            if cell:
                prior=current["days"].get(day,"")
                current["days"][day]=(prior+"\n"+cell).strip()
    return weeks,problems


def extract(path):
    reader=PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs need an unencrypted course copy.")
    if len(reader.pages)>150:
        raise ValueError("PDF table reading supports up to 150 pages.")
    rows=[];markers=[];pages=[];size=0
    for number,page in enumerate(reader.pages,1):
        if int(page.get("/Rotate",0))%360:
            raise ValueError("Rotated PDF table pages are not yet supported; use text/layout reading.")
        text,table_rows,page_markers=page_parts(page,number)
        size+=len(text)
        if size>MAX_TEXT:
            raise ValueError("Document exceeds the structured text limit.")
        pages.append(dict(page=number,text=text))
        rows.extend(table_rows);markers.extend(page_markers)
    weeks,problems=weekly_grid(rows,markers)
    return dict(pages=pages,tables=[{k:r[k] for k in ("page","cells")} for r in rows],
        weeks=weeks,problems=problems,coverage="labelled_pdf_cells",
        scope="Course document, not personal group allocations or a live timetable. Empty cells do not prove no classes.",
        date_mapping="No calendar dates inferred from week numbers.")
