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


@pytest.mark.parametrize("query", ["", "?gradeLevel=THCS"])
async def test_requires_authentication(query):
    async with api() as (client, _):
        response = await client.get(SUBJECTS + query, headers={"Authorization": ""})
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


def seed_multiple_grade_levels(catalog):
    seed(catalog)
    basic = catalog.add_subject("Toán", "THCS")
    catalog.add_topic(basic, "Đại số", "Hằng đẳng thức")
    hidden = catalog.add_subject("Môn đã tắt", "THCS", is_active=False)
    catalog.add_topic(hidden, "Đại số", "Chủ đề không được hiển thị")
    no_open_topic = catalog.add_subject("Chủ đề đã tắt", "THCS")
    catalog.add_topic(no_open_topic, "Đại số", "Chủ đề đã tắt", is_active=False)
    catalog.add_subject("Môn chưa có chủ đề", "THCS")


@pytest.mark.parametrize("role", ["LEARNER", "ADMIN"])
@pytest.mark.parametrize("grade, expected_count", [("THCS", 1), ("THPT", 2)])
async def test_filters_active_subjects_and_topics_by_grade_level(role, grade, expected_count):
    async with api(role=role) as (client, catalog):
        seed_multiple_grade_levels(catalog)
        response = await client.get(SUBJECTS, params={"gradeLevel": grade})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        subjects = response.json()["subjects"]
        assert len(subjects) == expected_count
        assert {subject["gradeLevel"] for subject in subjects} == {grade}
        if grade == "THCS":
            assert subjects[0]["name"] == "Toán"
            assert subjects[0]["chapters"][0]["topics"][0]["name"] == "Hằng đẳng thức"


@pytest.mark.parametrize("grade", [None, "", "   "])
async def test_omitted_or_blank_grade_returns_all_open_subjects(grade):
    async with api() as (client, catalog):
        seed_multiple_grade_levels(catalog)
        params = {} if grade is None else {"gradeLevel": grade}
        response = await client.get(SUBJECTS, params=params)
        assert response.status_code == 200
        subjects = response.json()["subjects"]
        assert len(subjects) == 3
        assert {subject["gradeLevel"] for subject in subjects} == {"THCS", "THPT"}


async def test_grade_filter_trims_surrounding_whitespace():
    async with api() as (client, catalog):
        seed_multiple_grade_levels(catalog)
        response = await client.get(SUBJECTS, params={"gradeLevel": "  THCS  "})
        assert response.status_code == 200
        assert [subject["gradeLevel"] for subject in response.json()["subjects"]] == ["THCS"]


@pytest.mark.parametrize("grade", ["Không tồn tại", "TH", "thcs", "x" * 50])
async def test_unknown_or_non_matching_grade_returns_empty_catalog(grade):
    async with api() as (client, catalog):
        seed_multiple_grade_levels(catalog)
        response = await client.get(SUBJECTS, params={"gradeLevel": grade})
        assert response.status_code == 200
        assert response.json() == {"subjects": []}


async def test_grade_filter_rejects_value_longer_than_database_column():
    async with api() as (client, catalog):
        seed_multiple_grade_levels(catalog)
        response = await client.get(SUBJECTS, params={"gradeLevel": "x" * 51})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_swagger_documents_grade_filter():
    async with api() as (client, _):
        schema = (await client.get("/openapi.json")).json()
        parameters = schema["paths"][SUBJECTS]["get"]["parameters"]
        grade = next(parameter for parameter in parameters if parameter["name"] == "gradeLevel")
        assert grade["in"] == "query" and grade["required"] is False


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
