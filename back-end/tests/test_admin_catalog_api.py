"""Quản trị danh mục lưu thật qua repository và ảnh hưởng luồng học đang mở."""

from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio
SUBJECTS = "/api/admin/subjects"
TOPICS = "/api/admin/topics"


@asynccontextmanager
async def catalog_api(role="ADMIN", *, active=True):
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    user = await users.create(name="Quản trị", email="admin@example.com", password_hash="private", role=role)
    users._users[user.id] = replace(user, is_active=active)
    app = create_app(user_repository=users, catalog_repository=catalog, settings=Settings(jwt_secret="catalog-admin-" + "x" * 40))
    token = app.state.token_service.create_access_token(user.id).access_token
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
        yield client, catalog


ROUTES = [(method, path) for path in (SUBJECTS, TOPICS) for method in ("GET", "POST")]
ROUTES += [("PATCH", path + "/1") for path in (SUBJECTS, TOPICS)]


@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize("access,expected", [("guest", 401), ("learner", 403), ("inactive", 403)])
async def test_admin_only_routes_reject_unauthorized_without_writing(method, path, access, expected):
    async with catalog_api("LEARNER" if access == "learner" else "ADMIN", active=access != "inactive") as (client, catalog):
        headers = {"Authorization": ""} if access == "guest" else {}
        response = await client.request(method, path, headers=headers, json={"name": "Không được tạo"})
        assert response.status_code == expected
        assert response.headers["cache-control"] == "no-store"
        assert catalog._subjects == catalog._topics == {}


async def test_create_edit_and_read_subject_with_normalized_fields():
    async with catalog_api() as (client, _):
        created = await client.post(SUBJECTS, json={"name": "  Toán   học  ", "gradeLevel": " THPT "})
        assert created.status_code == 201
        first = created.json()["subject"]
        assert first == {"id": 1, "name": "Toán học", "gradeLevel": "THPT", "isActive": True}
        second = await client.post(SUBJECTS, json={"name": "Toán học", "gradeLevel": "THCS"})
        assert second.status_code == 201  # cùng tên khác cấp học hợp lệ
        assert second.json()["subject"]["id"] > first["id"]
        updated = await client.patch(SUBJECTS + "/1", json={"name": "Toán mới"})
        assert updated.status_code == 200
        assert updated.json()["subject"] == {**first, "name": "Toán mới"}
        listed = await client.get(SUBJECTS)
        assert listed.status_code == 200
        assert listed.headers["cache-control"] == "no-store"
        assert listed.json()["subjects"][0] == updated.json()["subject"]


async def test_topic_create_partial_edit_clear_description_and_move_subject():
    async with catalog_api() as (client, catalog):
        first = catalog.add_subject("Toán", "THPT")
        second = catalog.add_subject("Toán", "THCS", is_active=False)
        response = await client.post(TOPICS, json={"subjectId": first, "chapterName": " Chương   1 ", "name": "  Hàm   số ", "description": "  Dòng 1\nDòng 2  "})
        assert response.status_code == 201
        topic = response.json()["topic"]
        assert topic == {"id": 1, "subjectId": first, "subjectName": "Toán", "gradeLevel": "THPT", "chapterName": "Chương 1", "name": "Hàm số", "description": "Dòng 1\nDòng 2", "isActive": True}
        edited = await client.patch(TOPICS + "/1", json={"name": "Đồ thị"})
        assert edited.json()["topic"] == {**topic, "name": "Đồ thị"}
        for description in (None, "   "):
            cleared = await client.patch(TOPICS + "/1", json={"description": description})
            assert cleared.status_code == 200
            assert cleared.json()["topic"]["description"] is None
        moved = await client.patch(TOPICS + "/1", json={"subjectId": second})
        assert moved.status_code == 200
        assert moved.json()["topic"]["subjectId"] == second
        assert moved.json()["topic"]["gradeLevel"] == "THCS"
        # Môn cha tắt vẫn quản lý được, nhưng người học không mở chủ đề được.
        assert (await client.get("/api/catalog/topics/1")).status_code == 404
        assert (await client.get(TOPICS)).json()["topics"] == [moved.json()["topic"]]


async def test_toggles_hide_from_public_catalog_without_deleting_or_changing_child_status():
    async with catalog_api() as (client, catalog):
        subject = catalog.add_subject("Toán", "THPT")
        topic = catalog.add_topic(subject, "Chương 1", "Hàm số")
        assert (await client.get("/api/catalog/subjects")).json()["subjects"]
        assert (await client.patch(SUBJECTS + f"/{subject}", json={"isActive": False})).status_code == 200
        assert (await client.get("/api/catalog/subjects")).json() == {"subjects": []}
        assert (await client.get("/api/catalog/topics/1")).status_code == 404
        assert (await client.get(TOPICS)).json()["topics"][0]["isActive"] is True
        subjects = (await client.get(SUBJECTS)).json()["subjects"]
        assert subjects[0]["id"] == subject and subjects[0]["isActive"] is False
        await client.patch(SUBJECTS + f"/{subject}", json={"isActive": True})
        assert (await client.get("/api/catalog/topics/1")).status_code == 200
        await client.patch(TOPICS + f"/{topic}", json={"isActive": False})
        assert (await client.get("/api/catalog/subjects")).json() == {"subjects": []}
        await client.patch(TOPICS + f"/{topic}", json={"isActive": True})
        assert (await client.get("/api/catalog/subjects")).json()["subjects"][0]["chapters"][0]["topics"][0]["id"] == topic


async def test_admin_lists_include_empty_subjects_and_inactive_topics():
    async with catalog_api() as (client, catalog):
        empty = catalog.add_subject("Chưa có chủ đề", "THPT", is_active=False)
        other = catalog.add_subject("Toán", "THPT")
        topic = catalog.add_topic(other, "Chương 1", "Hàm số", is_active=False)
        assert {s["id"] for s in (await client.get(SUBJECTS)).json()["subjects"]} == {empty, other}
        assert (await client.get(TOPICS)).json()["topics"][0]["id"] == topic


async def test_unique_composites_return_conflict_and_failed_updates_do_not_change_records():
    async with catalog_api() as (client, catalog):
        subject = catalog.add_subject("Toán", "THPT")
        other = catalog.add_subject("Lý", "THPT")
        catalog.add_topic(subject, "Chương 1", "Cùng tên")
        topic = catalog.add_topic(subject, "Chương 1", "Tên khác")
        cases = [
            ("POST", SUBJECTS, {"name": " Toán ", "gradeLevel": "THPT"}, "SUBJECT_ALREADY_EXISTS"),
            ("PATCH", SUBJECTS + f"/{other}", {"name": "Toán", "isActive": False}, "SUBJECT_ALREADY_EXISTS"),
            ("POST", TOPICS, {"subjectId": subject, "chapterName": "Chương 1", "name": "Cùng tên"}, "TOPIC_ALREADY_EXISTS"),
            ("PATCH", TOPICS + f"/{topic}", {"name": "Cùng tên", "isActive": False}, "TOPIC_ALREADY_EXISTS"),
        ]
        for method, path, payload, code in cases:
            response = await client.request(method, path, json=payload)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == code
            assert "name" in response.json()["error"]["fields"]
        assert catalog._subjects[other]["name"] == "Lý" and catalog._subjects[other]["is_active"] is True
        assert catalog._topics[topic]["name"] == "Tên khác" and catalog._topics[topic]["is_active"] is True
        # Tên chủ đề giống nhau ở chương khác không trùng khóa.
        assert (await client.post(TOPICS, json={"subjectId": subject, "chapterName": "Chương 2", "name": "Cùng tên"})).status_code == 201
        assert (await client.patch(TOPICS + "/1", json={"name": "Cùng tên"})).status_code == 200


@pytest.mark.parametrize("path,payload,code", [
    (SUBJECTS + "/999", {"name": "Không có"}, "SUBJECT_NOT_FOUND"),
    (TOPICS + "/999", {"name": "Không có"}, "TOPIC_NOT_FOUND"),
    (TOPICS + "/1", {"subjectId": 999}, "SUBJECT_NOT_FOUND"),
])
async def test_missing_records_and_parent_are_404_without_mutation(path, payload, code):
    async with catalog_api() as (client, catalog):
        subject = catalog.add_subject("Toán", "THPT")
        catalog.add_topic(subject, "Chương 1", "Hàm số")
        response = await client.patch(path, json=payload)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == code
        assert catalog._topics[1]["subject_id"] == subject
        assert len(catalog._topics) == len(catalog._subjects) == 1


async def test_create_topic_rejects_missing_parent():
    async with catalog_api() as (client, catalog):
        response = await client.post(TOPICS, json={"subjectId": 999, "chapterName": "Chương 1", "name": "Hàm số"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SUBJECT_NOT_FOUND"
        assert not catalog._topics


@pytest.mark.parametrize("path,payload,field", [
    (SUBJECTS, {}, "body"),
    (SUBJECTS, [], "body"),
    (SUBJECTS, {"name": "Toán"}, "gradeLevel"),
    (SUBJECTS, {"name": "   ", "gradeLevel": "THPT"}, "name"),
    (SUBJECTS, {"name": "a" * 121, "gradeLevel": "THPT"}, "name"),
    (SUBJECTS, {"name": 123, "gradeLevel": "THPT"}, "name"),
    (SUBJECTS, {"name": "Toán", "gradeLevel": "a" * 51}, "gradeLevel"),
    (SUBJECTS, {"name": "Toán", "gradeLevel": "THPT", "id": 7}, "id"),
    (SUBJECTS, {"name": "Toán", "gradeLevel": "THPT", "isActive": False}, "isActive"),
    (TOPICS, {"subjectId": True, "chapterName": "C1", "name": "Tên"}, "subjectId"),
    (TOPICS, {"subjectId": "1", "chapterName": "C1", "name": "Tên"}, "subjectId"),
    (TOPICS, {"subjectId": 0, "chapterName": "C1", "name": "Tên"}, "subjectId"),
    (TOPICS, {"subjectId": 2**31, "chapterName": "C1", "name": "Tên"}, "subjectId"),
    (TOPICS, {"subjectId": 1, "chapterName": "a" * 151, "name": "Tên"}, "chapterName"),
    (TOPICS, {"subjectId": 1, "chapterName": "C1", "name": "a" * 181}, "name"),
    (TOPICS, {"subjectId": 1, "chapterName": "C1", "name": "Tên", "description": 123}, "description"),
    (TOPICS, {"subjectId": 1, "chapterName": "C1", "name": "Tên", "description": "\x00"}, "description"),
])
async def test_create_validates_types_lengths_and_allowed_fields(path, payload, field):
    async with catalog_api() as (client, catalog):
        response = await client.post(path, json=payload)
        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert not catalog._subjects and not catalog._topics


@pytest.mark.parametrize("payload,field", [({}, "body"), ({"name": None}, "name"), ({"isActive": 0}, "isActive"), ({"isActive": "false"}, "isActive"), ({"role": "ADMIN"}, "role")])
@pytest.mark.parametrize("path", [SUBJECTS, TOPICS])
async def test_patch_is_strict_and_rejects_empty_or_extra_fields(path, payload, field):
    async with catalog_api() as (client, catalog):
        subject = catalog.add_subject("Toán", "THPT")
        catalog.add_topic(subject, "Chương 1", "Hàm số")
        response = await client.patch(path + "/1", json=payload)
        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert catalog._subjects[1]["is_active"] is catalog._topics[1]["is_active"] is True


@pytest.mark.parametrize("path", [SUBJECTS, TOPICS])
async def test_write_requires_json_and_invalid_json_is_400(path):
    async with catalog_api() as (client, _):
        response = await client.post(path, content="name=x", headers={"Content-Type": "text/plain"})
        assert response.status_code == 415
        malformed = await client.post(path, content="{", headers={"Content-Type": "application/json"})
        assert malformed.status_code == 400
        assert malformed.json()["error"]["code"] == "INVALID_JSON"


@pytest.mark.parametrize("path,payload,field", [
    (SUBJECTS, '{"name":"\\ud800","gradeLevel":"THPT"}', "name"),
    (TOPICS, '{"name":"Topic","chapterName":"C1","subjectId":1,"description":"\\udfff"}', "description"),
])
async def test_rejects_unpaired_unicode_surrogates_without_server_error(path, payload, field):
    async with catalog_api() as (client, _):
        response = await client.post(path, content=payload, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
