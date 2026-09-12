from io import BytesIO
from pathlib import Path
import json
import zipfile
import httpx
import pytest
from edinburgh_study_agent.downloads import download_resource, list_downloads
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.store import Store

URL = "https://prod01-euc1-prod01-xythos.prod.files.blackboard.com/example?X-Amz-Signature=DO_NOT_PERSIST"

@pytest.fixture
def resource(tmp_path):
    store = Store(tmp_path/"data")
    obs = Observation(source="learn",source_url="https://www.learn.ed.ac.uk/ultra/course",
        title="Fixture",observed_at=now_utc(),scope="synthetic",text="Lecture handout",
        items=[Item(native_id="r",kind="resource",title="Lecture handout",excerpt="Lecture handout",course_id="c")])
    key = store.capture(obs)["inserted"][0]
    return store,key

def client(body, status=200, headers=None):
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status,content=body,headers=headers or {})))

def test_pdf_download_has_no_dialog_and_no_secret_in_index(resource):
    store,key=resource
    with client(b"%PDF-1.7\nsynthetic fixture") as http:
        output=download_resource(store,key,URL,"lecture.pdf",client=http)
    assert output["verified"] and not output["save_dialog_required"]
    assert Path(output["path"]).read_bytes().startswith(b"%PDF-")
    assert "DO_NOT_PERSIST" not in json.dumps(list_downloads(store))
    with store.connection() as db:
        assert "DO_NOT_PERSIST" not in "\n".join(db.iterdump())

def test_existing_download_reused_without_network(resource):
    store,key=resource
    with client(b"%PDF-1.7\nfixture") as http:
        first=download_resource(store,key,URL,"lecture.pdf",client=http)
    def unexpected(request):
        raise AssertionError("A repeated request should not download an already verified file.")
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as http:
        repeated=download_resource(store,key,URL,"lecture.pdf",client=http)
    assert repeated["reused"] and repeated["path"]==first["path"]

@pytest.mark.parametrize("url",["http://www.learn.ed.ac.uk/file","https://127.0.0.1/file",
    "https://prod01-euc1-prod01-xythos.prod.files.blackboard.com.evil.example/file"])
def test_wrong_origin_rejected(resource,url):
    store,key=resource
    with pytest.raises(ValueError):
        download_resource(store,key,url,"lecture.pdf")

def test_redirect_cannot_escape_allowed_file_hosts(resource):
    store,key=resource
    seen=[]
    def respond(request):
        seen.append(str(request.url.host))
        return httpx.Response(302,headers={"location":"https://attacker.example/file"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ValueError):
            download_resource(store,key,URL,"lecture.pdf",client=http)
    assert len(seen)==1 and not list_downloads(store)["files"]

def test_html_rejected_and_partial_removed(resource):
    store,key=resource
    with client(b"<html>Login required</html>",headers={"content-type":"text/html"}) as http:
        with pytest.raises(ValueError,match="web/login"):
            download_resource(store,key,URL,"lecture.pdf",client=http)
    assert not list((store.root/"downloads").rglob(".partial-*"))

def test_oversized_file_and_path_traversal_rejected(resource):
    store,key=resource
    with pytest.raises(ValueError):
        download_resource(store,key,URL,"../../lecture.pdf")
    with client(b"x",headers={"content-length":"999999999"}) as http:
        with pytest.raises(ValueError,match="size limit"):
            download_resource(store,key,URL,"lecture.pdf",client=http)

def test_real_office_structure_and_integrity_checked(resource):
    store,key=resource
    content=BytesIO()
    with zipfile.ZipFile(content,"w") as archive:
        archive.writestr("[Content_Types].xml","<Types/>")
        archive.writestr("xl/workbook.xml","<workbook/>")
    with client(content.getvalue()) as http:
        output=download_resource(store,key,URL,"handout.xlsx",client=http)
    with zipfile.ZipFile(output["path"]) as archive:
        assert archive.testzip() is None
    with client(content.getvalue()) as http:
        with pytest.raises(ValueError,match="document type"):
            download_resource(store,key,URL,"handout.docx",client=http)

def test_network_error_does_not_echo_signed_url(resource):
    store,key=resource
    def fail(request):
        raise httpx.ConnectError("failed "+URL)
    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        with pytest.raises(ValueError) as error:
            download_resource(store,key,URL,"lecture.pdf",client=http)
    assert "DO_NOT_PERSIST" not in str(error.value)

def test_filename_from_download_response_is_validated(resource):
    store,key=resource
    with client(b"%PDF-1.7\nfixture",headers={"content-disposition":'attachment; filename="source.pdf"'}) as http:
        output=download_resource(store,key,URL,None,client=http)
    assert output["filename"]=="source.pdf"
    with client(b"%PDF-1.7\nfixture",headers={"content-disposition":'attachment; filename="../../source.pdf"'}) as http:
        with pytest.raises(ValueError):
            download_resource(store,key,URL,None,client=http)
