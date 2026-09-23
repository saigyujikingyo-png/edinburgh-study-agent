"""Offline fixtures for visible embedded originals; never contact the university."""
from html import escape
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest

from test_download_integrity import browser, page, site
from edinburgh_study_agent import school, learn_files, learn_attachments as inline, materials, contracts
from edinburgh_study_agent.downloads import download_resource, list_downloads
from edinburgh_study_agent.file_errors import FileDownloadError
from edinburgh_study_agent.models import Item, LearnAttachment
from edinburgh_study_agent.school_dom import observation
from edinburgh_study_agent.store import Store, identifier

PAGE = "https://www.learn.ed.ac.uk/ultra/courses/_1_1/document/_2_1"
ASSET = "/bbcswebdav/pid-9-dt-content-rid-30_1/xid-30_1"
ALT = "https://alt-5d1b15b77a8ac.blackboard.com"
PDF = b"%PDF-1.7\noriginal synthetic fixture"
PARENT = dict(native_id="_2_1",kind="resource",title="General Information",excerpt="General Information",
              url=PAGE,course_id="_1_1",course_title="Synthetic course",status="available")


def card(asset="_30_1", name="Actual.pdf", label="Lab Manual (PDF)", size=len(PDF), visible=True, **overrides):
    native=asset.lstrip("_")
    data=dict(displayName=label,fileName=name,fileSize=size,mimeType="application/pdf",
              resourceUrl=f"https://www.learn.ed.ac.uk/bbcswebdav/pid-9-dt-content-rid-{native}/xid-{native}")
    data.update(overrides)
    return '<div data-bbtype="attachment" data-bbfile="'+escape(json.dumps(data),quote=True)+'" '+('hidden' if not visible else '')+'><span>'+escape(label)+'</span><a data-ally-file-eid="'+asset+'"></a></div>'


@pytest.fixture
def store(tmp_path):
    store=Store(tmp_path/"private")
    store.capture(observation(PAGE,"Synthetic course",[Item(**PARENT)],"Offline fixture"))
    return store


def parent_id():
    return identifier("learn","resource",PARENT["native_id"])


def loaded(page, html):
    navigate=site(page,"<h1>General Information</h1>"+html)
    navigate(page,PAGE)
    return navigate


class RequestPage:
    """A real offline DOM with a fake browser-authenticated HEAD transport."""
    def __init__(self, page, location=None, status=302):
        self.page=page
        self.requests=[]
        self.location=location
        self.status=status
        self.context=SimpleNamespace(request=SimpleNamespace(head=self.head))
        self.disposed=0
    def __getattr__(self,name):return getattr(self.page,name)
    def head(self,url,**kwargs):
        self.requests.append((url,kwargs))
        location=self.location if self.location is not None else ALT+urlsplit(url).path+"?one_hash=synthetic-secret"
        return SimpleNamespace(status=self.status,headers={"location":location},dispose=self.dispose)
    def dispose(self):self.disposed+=1


def test_discovery_indexes_originals_ignores_hidden_and_preserves_parent(page):
    loaded(page,card()+card("_31_1",name="Actual.docx",label="Lab Manual (Word)")+card("_32_1",visible=False))
    items,coverage=inline.discover(page,PARENT)
    assert len(items)==2 and coverage["skipped"]==0 and coverage["visible_nodes"]==2
    assert {i.attachment.asset_id for i in items}=={"_30_1","_31_1"}
    assert all(i.url==PAGE and i.native_id.startswith("_2_1:attachment:") for i in items)
    assert items[0].attachment.resource_path==ASSET  # pid need not equal document id
    ids=[identifier("learn","resource",i.native_id) for i in items]
    assert len(set(ids))==2 and parent_id() not in ids


@pytest.mark.parametrize("override",[
    {"resourceUrl":"https://attacker.example/file.pdf"},
    {"resourceUrl":"https://www.learn.ed.ac.uk"+ASSET+"?signature=secret"},
    {"resourceUrl":"https://www.learn.ed.ac.uk/bbcswebdav/pid-9-dt-content-rid-99_1/xid-99_1"},
    {"fileName":"../escape.pdf"},{"fileSize":0},{"fileSize":100*1024*1024+1},
])
def test_untrusted_or_inconsistent_attachment_metadata_is_not_indexed(page,override):
    loaded(page,card(**override))
    items,coverage=inline.discover(page,PARENT)
    assert items==[] and coverage["skipped"]==1


def test_conflicts_fail_closed_but_exact_duplicate_dom_nodes_dedupe(page):
    loaded(page,card()+card())
    assert len(inline.discover(page,PARENT)[0])==1
    loaded(page,card()+card(name="Different.pdf"))
    items,coverage=inline.discover(page,PARENT)
    assert not items and coverage["skipped"]==1


def test_wrong_page_cannot_supply_child_binding(page):
    loaded(page,card())
    page.goto(PAGE.replace("_2_1","_3_1"))
    with pytest.raises(FileDownloadError,match="does not match"):
        inline.discover(page,PARENT)


def test_scoped_resolution_ignores_other_same_named_originals(page):
    navigate=loaded(page,card()+card("_31_1")+card("_32_1",visible=False))
    item=inline.discover(page,PARENT)[0][0].model_dump(mode="json")
    proxy=RequestPage(page)
    url,name,binding=learn_files.resolve_original(proxy,item,navigate)
    assert url==ALT+ASSET+"?one_hash=synthetic-secret" and name=="Actual.pdf"
    assert binding["asset_id"]=="_30_1" and binding["content_id"]=="_2_1"
    assert binding["method"]=="observed_inline_attachment" and proxy.disposed==1
    assert proxy.requests[0][1]=={"max_redirects":0,"timeout":15000}
    assert "synthetic-secret" not in json.dumps(binding)


@pytest.mark.parametrize("location,status,code",[
    ("https://attacker.example"+ASSET,302,"ATTACHMENT_MISMATCH"),
    (ALT+ASSET.replace("30_1","99_1"),302,"ATTACHMENT_MISMATCH"),
    ("https://www.learn.ed.ac.uk/login",302,"ATTACHMENT_MISMATCH"),
    ("",401,"DOWNLOAD_HTTP_ERROR"),
])
def test_bad_transfer_redirect_rejected_without_bytes(page,location,status,code):
    nav=loaded(page,card());item=inline.discover(page,PARENT)[0][0].model_dump(mode="json")
    proxy=RequestPage(page,location,status)
    with pytest.raises(FileDownloadError) as error:learn_files.resolve_original(proxy,item,nav)
    assert error.value.code==code and proxy.disposed==1


def test_changed_metadata_requires_fresh_parent_observation(page):
    nav=loaded(page,card());item=inline.discover(page,PARENT)[0][0].model_dump(mode="json")
    page.set_content(card(size=999))
    proxy=RequestPage(page)
    with pytest.raises(FileDownloadError):learn_files.resolve_original(proxy,item,nav)
    assert not proxy.requests


def test_page_read_and_batch_download_use_child_ids_and_validate_bytes(page,store,monkeypatch):
    nav=loaded(page,card()+card("_31_1",label="Second manual",name="Second.pdf"))
    proxy=RequestPage(page)
    monkeypatch.setattr(school,"goto_learn",nav)
    monkeypatch.setattr("edinburgh_study_agent.portal.wait_page",lambda _:None)
    value=school.read_resource(store,proxy,{"item_id":parent_id()},lambda _:None)
    contracts._check(contracts._job_validator("read_resource"),value)
    assert len(value["attachments"])==2
    from edinburgh_study_agent.responses import compact
    compacted=compact(value)
    contracts._check(contracts._job_validator("read_resource"),compacted)
    assert compacted["attachments"][0]["attachment"]==value["attachments"][0]["attachment"]
    def respond(request):
        if urlsplit(str(request.url)).path.endswith("/original.pdf"):
            return httpx.Response(200,content=PDF)
        return httpx.Response(302,headers={"Location":"/original.pdf"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(school,"download_resource",lambda *a,**kw:download_resource(*a,**kw,client=client))
        result=school.download_items(store,proxy,{"item_ids":[parent_id()],"refresh":True},lambda _:None)
    contracts._check(contracts._job_validator("download"),result)
    assert result["complete"] and len(result["saved"])==2 and not result["failed"]
    assert parent_id() not in {r["item_id"] for r in result["saved"]}
    assert {r["filename"] for r in result["saved"]}=={"Actual.pdf","Second.pdf"}
    assert all(r["size_bytes"]==len(PDF) and r["verified"] and not r["save_dialog_required"] for r in result["saved"])
    with store.connection() as db:assert "synthetic-secret" not in "\n".join(db.iterdump())
    # A repeated file download verifies the existing bytes without campus access.
    monkeypatch.setattr(school,"original_file",lambda *_:pytest.fail("No campus resolution on cache hit"))
    cached=school.download_items(store,None,{"item_ids":[r["item_id"] for r in result["saved"]],"refresh":False},lambda _:None)
    assert all(r["reused"] for r in cached["saved"])


def test_dom_size_mismatch_leaves_no_download_receipt(page,store):
    nav=loaded(page,card());child=inline.discover(page,PARENT)[0][0]
    store.capture(observation(PAGE,"Synthetic",[child],"Offline"))
    key=identifier("learn","resource",child.native_id)
    url,name,binding=learn_files.resolve_original(RequestPage(page),child.model_dump(mode="json"),nav)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=PDF+b"extra"))) as client:
        with pytest.raises(FileDownloadError) as error:download_resource(store,key,url,name,client=client,binding=binding)
    assert error.value.code=="FILE_VERIFICATION_FAILED" and not list_downloads(store)["files"]
    assert not list(store.root.rglob(".partial-*"))


def test_materials_discovers_bounded_documents_and_then_uses_index(page,store,monkeypatch):
    nav=loaded(page,card())
    monkeypatch.setattr(school,"goto_learn",nav)
    monkeypatch.setattr("edinburgh_study_agent.portal.wait_page",lambda _:None)
    store.capture(observation(PAGE,"Synthetic",[Item(native_id="_1_1",kind="course",title="Synthetic course",
        excerpt="Synthetic course",course_id="_1_1",status="available")],"Offline"))
    calls=[]
    monkeypatch.setattr(school,"list_resources",lambda *a,**kw:calls.append(1) or {"items":[store.item(parent_id())],"live":True})
    args={"course":"_1_1","query":"Lab Manual","operation":"list"}
    result=materials.read(store,page,args,lambda _:None)
    contracts._check(contracts._job_validator("materials"),result)
    assert result["items"][0]["attachment"]["filename"]=="Actual.pdf" and result["document_discovery"]["pages_read"]==1
    assert materials.cached(store,args)["items"][0]["id"]==result["items"][0]["id"]
    assert len(calls)==1
    # A parent-specific list must discover files, not return the cached container.
    assert materials.cached(store,{"item_id":parent_id(),"operation":"list"}) is None


def test_nullable_attachment_model_remains_portable():
    from edinburgh_study_agent.protocol import portable_schema
    schema=portable_schema(Item.model_json_schema())
    assert "oneOf" in schema["properties"]["attachment"] and "$ref" not in json.dumps(schema)
    invalid=dict(parent_native_id="_2_1",asset_id="_30_1",resource_path=ASSET,
                 filename="Actual.pdf",size_bytes=10,media_type="application/pdf")
    with pytest.raises(ValueError):Item(**PARENT,attachment=LearnAttachment(**invalid))


@pytest.mark.parametrize("style",["display:none","visibility:hidden","opacity:0"])
def test_hidden_ancestor_attachments_are_not_observed(page,style):
    loaded(page,card()+f'<section style="{style}">'+card("_31_1")+'</section>')
    items,coverage=inline.discover(page,PARENT)
    assert len(items)==1 and items[0].attachment.asset_id=="_30_1"


def test_parent_keyword_download_selects_only_matching_child(page,store,monkeypatch):
    nav=loaded(page,card()+card("_31_1",name="Lecture.pdf",label="Unrelated lecture"))
    monkeypatch.setattr(school,"goto_learn",nav)
    monkeypatch.setattr("edinburgh_study_agent.portal.wait_page",lambda _:None)
    calls=[]
    monkeypatch.setattr(school,"download_items",lambda st,p,args,progress:calls.append(args) or {"saved":[],"failed":[]})
    materials.read(store,page,{"item_id":parent_id(),"query":"Lab Manual","operation":"download"},lambda _:None)
    assert len(calls)==1 and len(calls[0]["item_ids"])==1
    assert store.item(calls[0]["item_ids"][0])["title"]=="Lab Manual (PDF)"


def test_search_stops_after_three_documents_with_honest_remaining_scope(store,monkeypatch):
    course=Item(native_id="_1_1",kind="course",title="Synthetic course",excerpt="Synthetic course",
                course_id="_1_1",status="available")
    parents=[Item(**{**PARENT,"native_id":f"_{n}_1","url":PAGE.replace("_2_1",f"_{n}_1")}) for n in range(3,8)]
    store.capture(observation(PAGE,"Synthetic",[course,*parents],"Offline"))
    calls=[]
    monkeypatch.setattr(school,"list_resources",lambda *a,**kw:{"items":[],"live":True})
    monkeypatch.setattr(school,"read_resource",lambda st,p,args,progress:calls.append(args) or {"attachments":[]})
    result=materials.read(store,None,{"course":"_1_1","query":"not present","operation":"list"},lambda _:None)
    contracts._check(contracts._job_validator("materials"),result)
    assert len(calls)==3 and result["document_discovery"]["remaining_pages"]==3
    assert result["suggested_observed_files"] and result["coverage"]=="partial"


def test_partial_discovery_does_not_report_complete_parent_download(page,store,monkeypatch):
    nav=loaded(page,card()+card("_31_1",fileName="unsupported.exe"))
    monkeypatch.setattr(school,"goto_learn",nav)
    monkeypatch.setattr("edinburgh_study_agent.portal.wait_page",lambda _:None)
    monkeypatch.setattr(school,"download_resource",lambda *a,**kw:pytest.fail("Incomplete parent inventory"))
    result=school.download_items(store,page,{"item_ids":[parent_id()],"refresh":True},lambda _:None)
    contracts._check(contracts._job_validator("download"),result)
    assert not result["complete"] and not result["saved"]
    assert result["failed"][0]["code"]=="ATTACHMENT_DISCOVERY_INCOMPLETE"


def test_parent_expansion_above_batch_limit_never_silently_truncates(page,store,monkeypatch):
    nav=loaded(page,''.join(card(f"_{n}_1") for n in range(30,61)))
    monkeypatch.setattr(school,"goto_learn",nav)
    monkeypatch.setattr("edinburgh_study_agent.portal.wait_page",lambda _:None)
    result=school.download_items(store,page,{"item_ids":[parent_id()]},lambda _:None)
    contracts._check(contracts._job_validator("download"),result)
    assert not result["saved"] and not result["complete"]
    assert result["failed"][0]["code"]=="ATTACHMENT_AMBIGUOUS"
