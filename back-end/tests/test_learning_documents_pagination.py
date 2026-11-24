"""Pagination filters published documents before slicing, including Vietnamese search."""

from dataclasses import replace
from datetime import datetime

import pytest

from app.models import Document
from app.repositories.document_repository import SqlAlchemyDocumentRepository
from test_database_integration import database, make_catalog
from test_learning_documents_api import ROOT, api, seed_document

pytestmark = pytest.mark.anyio


async def test_document_pages_have_stable_order_no_hidden_rows_and_correct_metadata(tmp_path):
    async with api(tmp_path) as state:
        visible_ids = [state.doc_txt.id, state.doc_pdf.id]
        for index in range(23):
            doc = await seed_document(
                state.repository, state.storage, topic_id=1, title=f"Bài học {index}",
                filename=f"lesson-{index}.txt", file_bytes=b"lesson", chunks=["Nội dung"],
            )
            visible_ids.append(doc.id)
        # Shared timestamps must still give a deterministic order across pages.
        for doc_id, doc in state.repository._documents.items():
            state.repository._documents[doc_id] = replace(doc, created_at="2026-11-24T08:00:00.000Z")
        expected = sorted(visible_ids, reverse=True)

        first = (await state.client.get(ROOT)).json()
        assert (first["limit"], first["offset"], first["hasMore"]) == (20, 0, True)
        assert [doc["id"] for doc in first["documents"]] == expected[:20]

        last = (await state.client.get(ROOT, params={"limit": 20, "offset": 20})).json()
        assert (last["limit"], last["offset"], last["hasMore"]) == (20, 20, False)
        assert [doc["id"] for doc in last["documents"]] == expected[20:]

        empty = (await state.client.get(ROOT, params={"limit": 20, "offset": 40})).json()
        assert empty == {"documents": [], "limit": 20, "offset": 40, "hasMore": False}


async def test_document_filters_and_vietnamese_search_apply_before_pagination(tmp_path):
    async with api(tmp_path) as state:
        matched = []
        for index in range(4):
            doc = await seed_document(
                state.repository, state.storage, topic_id=1, title=f"Chuyên biệt {index}",
                filename=f"matched-{index}.txt", file_bytes=b"matched", chunks=["Nội dung"],
            )
            matched.append(doc.id)
        await seed_document(
            state.repository, state.storage, topic_id=3, title="Chuyên biệt môn khác",
            filename="other-subject.txt", file_bytes=b"other", chunks=["Nội dung"],
        )
        await seed_document(
            state.repository, state.storage, topic_id=1, title="Không khớp từ khóa",
            filename="unmatched.txt", file_bytes=b"unmatched", chunks=["Nội dung"],
        )
        params = {"subjectId": 1, "topicId": 1, "gradeLevel": "THPT", "q": "CHUYEN BIET", "limit": 2, "offset": 1}
        response = await state.client.get(ROOT, params=params)
        assert response.status_code == 200, response.text
        result = response.json()
        assert [doc["id"] for doc in result["documents"]] == sorted(matched, reverse=True)[1:3]
        assert result["hasMore"] is True
        params["offset"] = 3
        last = (await state.client.get(ROOT, params=params)).json()
        assert [doc["id"] for doc in last["documents"]] == [matched[0]]
        assert last["hasMore"] is False


async def test_topic_document_endpoint_uses_same_pagination_contract(tmp_path):
    async with api(tmp_path, role="ADMIN") as state:
        response = await state.client.get("/api/catalog/topics/1/documents", params={"limit": 1, "offset": 0})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["topicId"] == 1
        assert [doc["id"] for doc in result["documents"]] == [state.doc_txt.id]
        assert (result["limit"], result["offset"], result["hasMore"]) == (1, 0, False)
        empty = (await state.client.get("/api/catalog/topics/1/documents", params={"limit": 1, "offset": 1})).json()
        assert empty["documents"] == [] and empty["hasMore"] is False


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": -1}, {"limit": 101}, {"limit": "1.5"}, {"limit": "abc"},
    {"offset": -1}, {"offset": 100001}, {"offset": "1.5"}, {"offset": "abc"},
])
async def test_invalid_pagination_is_rejected_on_both_document_lists(tmp_path, params):
    async with api(tmp_path) as state:
        for path in (ROOT, "/api/catalog/topics/1/documents"):
            response = await state.client.get(path, params=params)
            assert response.status_code == 422, response.text
            assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("query", [None, "DAC BIET"])
async def test_mysql_document_pagination_filters_before_offset_and_preserves_unicode_search(database, query):
    # The shared fixture only creates and drops its own random test database.
    _, sessions = database
    with sessions.begin() as db:
        _, _, topic = make_catalog(db)
        topic_id = topic.id
        created_at = datetime(2026, 11, 24, 8)
        documents = [Document(
            topic_id=topic_id, title=f"Đặc biệt {index}", file_path=f"page-{index}.txt",
            status="ready", is_active=True, created_at=created_at,
        ) for index in range(5)]
        hidden = Document(
            topic_id=topic_id, title="Đặc biệt chưa bật", file_path="hidden.txt",
            status="ready", is_active=False, created_at=created_at,
        )
        unmatched = Document(
            topic_id=topic_id, title="Ngoài phạm vi tìm kiếm", file_path="unmatched.txt",
            status="ready", is_active=True, created_at=created_at,
        )
        db.add_all([*documents, hidden, unmatched])
        db.flush()
        visible = documents if query else [*documents, unmatched]
        expected = sorted((doc.id for doc in visible), reverse=True)
    repository = SqlAlchemyDocumentRepository(sessions)
    page = await repository.list_learning_documents(topic_id=topic_id, query=query, limit=2, offset=1)
    assert [doc.id for doc in page] == expected[1:3]
    last = await repository.list_learning_documents(topic_id=topic_id, query=query, limit=2, offset=4)
    assert [doc.id for doc in last] == expected[4:]
    assert await repository.list_learning_documents(topic_id=topic_id, query=query, limit=2, offset=20) == []
    assert await repository.list_learning_documents(topic_id=topic_id, query="%_", limit=2, offset=0) == []
