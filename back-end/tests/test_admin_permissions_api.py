"""TK-071: every registered admin operation checks the current server-side role."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import httpx
import jwt
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.document_repository import InMemoryDocumentRepository, SubjectRecord, TopicRecord
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio
SECRET = "admin-permissions-tests-" + "x" * 40

# Every GET/POST/PATCH operation in the admin namespace, including file upload.
ADMIN_OPERATIONS = [
    ("GET", "/api/admin/access"),
    ("GET", "/api/admin/subjects"), ("POST", "/api/admin/subjects"),
    ("PATCH", "/api/admin/subjects/{subject_id}"),
    ("GET", "/api/admin/topics"), ("POST", "/api/admin/topics"),
    ("PATCH", "/api/admin/topics/{topic_id}"),
    ("GET", "/api/admin/documents/options"),
    ("GET", "/api/admin/documents"), ("POST", "/api/admin/documents"),
    ("PATCH", "/api/admin/documents/{document_id}"),
    ("POST", "/api/admin/documents/{document_id}/process"),
]


def request_data(method, path, *, subject_id, topic_id):
    if method == "POST" and path == "/api/admin/documents":
        return {"data": {"topic_id": str(topic_id), "title": "Tài liệu mới"},
                "files": {"file": ("lesson.txt", "Nội dung học tập".encode(), "text/plain")}}
    if method == "POST" and path == "/api/admin/subjects":
        return {"json": {"name": "Môn học mới", "gradeLevel": "THCS"}}
    if method == "POST" and path == "/api/admin/topics":
        return {"json": {"subjectId": subject_id, "chapterName": "Chương mới", "name": "Chủ đề mới"}}
    if method == "PATCH":
        return {"json": {"isActive": True}}
    return {}


class NoBusinessAccess:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        self.calls.append(name)
        raise AssertionError("Rejected requests must not access admin services or document storage")


@asynccontextmanager
async def api(tmp_path):
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    admin = await users.create(name="Quản trị", email="admin@example.com", password_hash="private-admin-hash", role="ADMIN")
    learner = await users.create(name="Người học", email="learner@example.com", password_hash="private-learner-hash", role="LEARNER")
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình")
    documents = InMemoryDocumentRepository(subjects=[SubjectRecord(subject_id, "Toán", "THPT")],
                                           topics=[TopicRecord(topic_id, subject_id, "Phương trình")])
    storage = tmp_path / "private-documents"
    storage.mkdir()
    private_file = storage / "private-original.txt"
    private_file.write_text("Nội dung gốc cần giữ", encoding="utf-8")
    document = await documents.create(topic_id=topic_id, title="Tài liệu gốc", file_path=private_file.name)
    await documents.finish_processing(document.id, chunks=["Nội dung gốc cần giữ"])
    app = create_app(user_repository=users, catalog_repository=catalog, document_repository=documents,
                     upload_dir=storage, password_hasher=lambda raw: "test-only-hash",
                     settings=Settings(jwt_secret=SECRET))
    def headers(person, **kwargs):
        token = app.state.token_service.create_access_token(person.id, **kwargs).access_token
        return {"Authorization": "Bearer " + token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        yield SimpleNamespace(client=client, app=app, users=users, catalog=catalog, documents=documents,
                              admin=admin, learner=learner, headers=headers, storage=storage,
                              private_file=private_file, subject_id=subject_id, topic_id=topic_id, document_id=document.id)


async def send(state, method, path, headers):
    data = request_data(method, path, subject_id=state.subject_id, topic_id=state.topic_id)
    resolved = path.format(subject_id=state.subject_id, topic_id=state.topic_id, document_id=state.document_id)
    return await state.client.request(method, resolved, headers=headers, **data)


def block_business(state):
    forbidden = NoBusinessAccess()
    state.app.state.admin_catalog_service = forbidden
    state.app.state.document_repository = forbidden
    return forbidden


def assert_denied(response, expected):
    assert response.status_code == expected, response.text
    assert response.json()["error"]["code"] == ("FORBIDDEN" if expected == 403 else "NOT_AUTHENTICATED")
    assert response.headers["cache-control"] == "no-store"
    assert all(secret not in response.text for secret in ("@example.com", "private-admin-hash", "private-learner-hash"))


@pytest.mark.parametrize("method,path", ADMIN_OPERATIONS)
@pytest.mark.parametrize("access,expected", [("guest", 401), ("learner", 403), ("inactive_admin", 403)])
async def test_every_admin_operation_rejects_without_business_reads_or_writes(tmp_path, method, path, access, expected):
    async with api(tmp_path) as state:
        if access == "guest":
            headers = {}
        elif access == "learner":
            headers = state.headers(state.learner)
        else:
            headers = state.headers(state.admin)
            state.users._users[state.admin.id] = replace(state.admin, is_active=False)
        forbidden = block_business(state)
        before = (dict(state.catalog._subjects), dict(state.catalog._topics), dict(state.documents._documents))
        response = await send(state, method, path, headers)
        assert_denied(response, expected)
        assert forbidden.calls == []
        assert before == (state.catalog._subjects, state.catalog._topics, state.documents._documents)
        assert list(state.storage.iterdir()) == [state.private_file]
        assert state.private_file.read_text(encoding="utf-8") == "Nội dung gốc cần giữ"


@pytest.mark.parametrize("method,path", ADMIN_OPERATIONS)
async def test_active_admin_can_use_every_registered_admin_operation(tmp_path, method, path):
    async with api(tmp_path) as state:
        response = await send(state, method, path, state.headers(state.admin))
        expected = 201 if method == "POST" and not path.endswith("/process") else 200
        assert response.status_code == expected, response.text
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("method,path", ADMIN_OPERATIONS)
async def test_demoting_admin_revokes_existing_token_on_every_admin_operation(tmp_path, method, path):
    async with api(tmp_path) as state:
        headers = state.headers(state.admin)
        assert (await state.client.get("/api/admin/access", headers=headers)).status_code == 200
        state.users._users[state.admin.id] = replace(state.admin, role="LEARNER")
        forbidden = block_business(state)
        assert_denied(await send(state, method, path, headers), 403)
        assert forbidden.calls == []


async def test_operation_matrix_covers_all_registered_admin_api_routes(tmp_path):
    async with api(tmp_path) as state:
        actual = {(method.upper(), path) for path, methods in state.app.openapi()["paths"].items()
                  if path.startswith("/api/admin/") for method in methods if method in {"get", "post", "patch", "put", "delete"}}
        assert actual == set(ADMIN_OPERATIONS)


@pytest.mark.parametrize("forgery", ["jwt_role_claim", "headers_query_body"])
async def test_client_role_claims_cannot_override_database_learner_role(tmp_path, forgery):
    async with api(tmp_path) as state:
        headers = state.headers(state.learner)
        if forgery == "jwt_role_claim":
            claims = jwt.decode(headers["Authorization"][7:], SECRET, algorithms=["HS256"], issuer="gia-su-ai")
            claims.update({"role": "ADMIN", "is_active": True})
            headers = {"Authorization": "Bearer " + jwt.encode(claims, SECRET, algorithm="HS256")}
        else:
            headers.update({"X-Role": "ADMIN", "X-User-Id": str(state.admin.id)})
        forbidden = block_business(state)
        response = await state.client.post("/api/admin/subjects", headers=headers,
                                           params={"role": "ADMIN", "userId": state.admin.id},
                                           json={"name": "Môn giả", "gradeLevel": "THPT", "role": "ADMIN"})
        assert_denied(response, 403)
        assert forbidden.calls == [] and state.users._users[state.learner.id].role == "LEARNER"


@pytest.mark.parametrize("access,code", [("expired", "TOKEN_EXPIRED"), ("invalid", "INVALID_TOKEN"), ("deleted", "INVALID_TOKEN")])
async def test_invalid_credentials_never_grant_admin_access(tmp_path, access, code):
    async with api(tmp_path) as state:
        headers = state.headers(state.admin, expires_delta=timedelta(seconds=-30)) if access == "expired" else state.headers(state.admin)
        if access == "invalid":
            headers = {"Authorization": "Bearer not-a-jwt"}
        elif access == "deleted":
            del state.users._users[state.admin.id]
        response = await state.client.get("/api/admin/access", headers=headers)
        assert response.status_code == 401 and response.json()["error"]["code"] == code
        assert "Bearer" in response.headers["www-authenticate"]


async def test_register_and_profile_cannot_promote_learner_and_public_learning_apis_still_work(tmp_path):
    async with api(tmp_path) as state:
        registered = await state.client.post("/api/auth/register", json={
            "name": "Người mới", "email": "new@example.com", "password": "ExamplePassword123!",
            "confirmPassword": "ExamplePassword123!", "consent": True, "role": "ADMIN",
        })
        assert registered.status_code == 201 and registered.json()["user"]["role"] == "LEARNER"
        user = await state.users.find_by_id(registered.json()["user"]["id"])
        headers = state.headers(user)
        assert_denied(await state.client.get("/api/admin/access", headers=headers), 403)
        changed = await state.client.patch("/api/profile", headers=headers, json={"role": "ADMIN"})
        assert changed.status_code == 422 and (await state.users.find_by_id(user.id)).role == "LEARNER"
        assert (await state.client.get("/api/profile", headers=headers)).status_code == 200
        assert (await state.client.get("/api/catalog/subjects", headers=headers)).status_code == 200
