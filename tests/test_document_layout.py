import json
from datetime import timedelta
from pathlib import Path
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from edinburgh_study_agent import document_layout,workflow_cache
from edinburgh_study_agent.models import now_utc
from edinburgh_study_agent.store import Store


def synthetic_grid(path,rotate=False):
    writer=PdfWriter()
    font=writer._add_object(DictionaryObject({NameObject("/Type"):NameObject("/Font"),
        NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")}))
    borders=[10,80,180,280,380,480,580]
    def page(rows,marker):
        p=writer.add_blank_page(600,800);ops=[]
        p[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):font})})
        for y,label in marker:
            ops.append(f"BT /F1 10 Tf 100 {y} Td ({label}) Tj ET")
        for low,high,cells in rows:
            for x in borders:ops.append(f"{x} {low} 0.5 {high-low} re f")
            for x,values in zip(borders,cells):
                for i,value in enumerate(values):
                    ops.append(f"BT /F1 10 Tf {x+8} {high-18-i*13} Td ({value}) Tj ET")
        stream=DecodedStreamObject();stream.set_data("\n".join(ops).encode())
        p[NameObject("/Contents")]=writer._add_object(stream)
        if rotate:p.rotate(90)
    header=[[],["Mon"],["Tue"],["Wed"],["Thu"],["Fri"]]
    page([(700,740,header),(300,699,[["1"],["09:00-09:50","Algebra"],[],[],[],[]]),
          (1,299,[["2"],[],["Lab begins"],[],[],[]])],[(765,"Schedule - Semester 1")])
    page([(500,780,[[],[],["Lab continues"],[],[],[]]),(430,470,header),
          (150,429,[["1"],["Geometry"],[],[],[],[]]),(50,149,[["2"],[],[],[],[],[]])],
          [(480,"Schedule - Semester 2")])
    writer.write(path)


def test_real_pdf_geometry_preserves_cross_page_and_mid_page_semester_change(tmp_path):
    path=tmp_path/"synthetic.pdf";synthetic_grid(path)
    value=document_layout.extract(path)
    assert [(w["semester"],w["week"]) for w in value["weeks"]]==[(1,1),(1,2),(2,1),(2,2)]
    assert value["weeks"][0]["days"]["Mon"]=="09:00-09:50\nAlgebra"
    assert value["weeks"][1]["days"]["Tue"]=="Lab begins\nLab continues"
    assert value["weeks"][1]["pages"]==[1,2]
    assert value["weeks"][2]["days"]["Mon"]=="Geometry"
    assert value["weeks"][3]["days"]=={}
    assert value["problems"]==[]
    assert "No calendar dates inferred" in value["date_mapping"]


def test_pdf_rotation_does_not_silently_assign_wrong_columns(tmp_path):
    path=tmp_path/"rotated.pdf";synthetic_grid(path,True)
    with pytest.raises(ValueError,match="Rotated"):
        document_layout.extract(path)


def test_pdf_without_grid_keeps_text_scope_explicit(tmp_path):
    writer=PdfWriter();writer.add_blank_page(600,800);path=tmp_path/"empty.pdf";writer.write(path)
    value=document_layout.extract(path)
    assert value["weeks"]==[] and value["tables"]==[]
    assert "not personal" in value["scope"]


def test_workflow_cache_is_bounded_private_and_invalidated(tmp_path,monkeypatch):
    store=Store(tmp_path/"one")
    for i in range(18):workflow_cache.put(store,"test",str(i),{"value":i})
    assert workflow_cache.get(store,"test","0",60) is None
    assert workflow_cache.get(store,"test","17",60)=={"value":17}
    assert workflow_cache.get(Store(tmp_path/"two"),"test","17",60) is None
    assert not workflow_cache.put(store,"test","huge",{"text":"x"*workflow_cache.MAX_BYTES})
    stamp=now_utc()
    monkeypatch.setattr(workflow_cache,"now_utc",lambda:stamp+timedelta(seconds=61))
    assert workflow_cache.get(store,"test","17",60) is None
    workflow_cache.invalidate(store)
    assert workflow_cache.get(store,"test","17",3600) is None
