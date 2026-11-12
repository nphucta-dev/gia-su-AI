from contextlib import asynccontextmanager

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio
SECRET = "khoa-kiem-thu-danh-muc-" + "x" * 40
SUBJECTS = "/api/catalog/subjects"


@asynccontextmanager
async def api(role="LEARNER"):
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    app = create_app(user_repository=users, catalog_repository=catalog, settings=Settings(jwt_secret=SECRET))
    user = await users.create(name="An", email="an@example.com", password_hash="x", role=role)
    token = app.state.token_service.create_access_token(user.id).access_token
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as client:
        yield client, catalog


def seed(catalog):
    toan = catalog.add_subject("Toán", "THPT")
    ly = catalog.add_subject("Vật lí", "THPT")
    hidden = catalog.add_subject("Ẩn", "THPT", is_active=False)
    catalog.add_subject("Trống", "THPT")  # không có chủ đề active -> bị ẩn
    ids = {
        "pt": catalog.add_topic(toan, "Chương 1", "Phương trình bậc hai", "Biệt thức"),
        "hs": catalog.add_topic(toan, "Chương 1", "Hàm số"),
        "dh": catalog.add_topic(toan, "Chương 2", "Đạo hàm", is_active=False),
        "gh": catalog.add_topic(toan, "Chương 2", "Giới hạn"),
        "cm": catalog.add_topic(ly, "Cơ học", "Chuyển động thẳng đều"),
        "an": catalog.add_topic(hidden, "Chương 1", "Chủ đề của môn ẩn"),
    }
    return ids


async def test_requires_authentication():
    async with api() as (client, _):
        response = await client.get(SUBJECTS, headers={"Authorization": ""})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_lists_only_active_subjects_and_topics_grouped_by_chapter():
    async with api() as (client, catalog):
        ids = seed(catalog)
        response = await client.get(SUBJECTS)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        subjects = response.json()["subjects"]
        assert [s["name"] for s in subjects] == ["Toán", "Vật lí"]
        toan = subjects[0]
        assert toan["gradeLevel"] == "THPT"
        assert [(c["name"], [t["name"] for t in c["topics"]]) for c in toan["chapters"]] == [
            ("Chương 1", ["Phương trình bậc hai", "Hàm số"]),
            ("Chương 2", ["Giới hạn"]),
        ]
        first = toan["chapters"][0]["topics"][0]
        assert first == {"id": ids["pt"], "name": "Phương trình bậc hai", "description": "Biệt thức"}


async def test_empty_catalog_returns_empty_list():
    async with api() as (client, _):
        response = await client.get(SUBJECTS)
        assert response.status_code == 200
        assert response.json() == {"subjects": []}


async def test_admin_can_also_read_catalog():
    async with api(role="ADMIN") as (client, catalog):
        seed(catalog)
        assert (await client.get(SUBJECTS)).status_code == 200


async def test_open_topic_returns_subject_context():
    async with api() as (client, catalog):
        ids = seed(catalog)
        response = await client.get(f"/api/catalog/topics/{ids['pt']}")
        assert response.status_code == 200
        assert response.json()["topic"] == {
            "id": ids["pt"], "name": "Phương trình bậc hai", "description": "Biệt thức",
            "chapterName": "Chương 1", "subjectId": 1, "subjectName": "Toán", "gradeLevel": "THPT",
        }


@pytest.mark.parametrize("key", ["dh", "an"])  # chủ đề đã tắt / thuộc môn đã tắt
async def test_inactive_topic_or_subject_cannot_open_learning_flow(key):
    async with api() as (client, catalog):
        ids = seed(catalog)
        response = await client.get(f"/api/catalog/topics/{ids[key]}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TOPIC_NOT_FOUND"


async def test_unknown_or_invalid_topic_id():
    async with api() as (client, catalog):
        seed(catalog)
        assert (await client.get("/api/catalog/topics/9999")).status_code == 404
        assert (await client.get("/api/catalog/topics/abc")).status_code == 422
        assert (await client.get("/api/catalog/topics/0")).status_code == 422
