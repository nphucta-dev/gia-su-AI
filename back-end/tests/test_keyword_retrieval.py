"""TK-044: exact keyword ranking across all eligible chunks before applying limit."""

from dataclasses import replace
import unicodedata

import pytest

from app.repositories.document_repository import InMemoryDocumentRepository, SubjectRecord, TopicRecord
from app.services.document_retrieval import DocumentRetrievalService
from app.utils.errors import AppError
from app.utils.keywords import fold_text, literal_contains_pattern, parse_query


def make_repository():
    return InMemoryDocumentRepository(
        subjects=[SubjectRecord(1, "Toán", "THPT")],
        topics=[TopicRecord(1, 1, "Hàm số"), TopicRecord(2, 1, "Hình học")],
    )


async def add_source(repository, contents, *, topic_id=1, title="Nguồn", status="ready", active=True):
    document = await repository.create(topic_id=topic_id, title=title, file_path="private-server-path.txt")
    if status == "ready":
        await repository.finish_processing(document.id, chunks=contents)
    else:
        repository._chunks[document.id] = tuple(contents)
    repository._documents[document.id] = replace(
        repository._documents[document.id], status=status, is_active=active, chunk_count=len(contents),
    )
    return document.id


@pytest.mark.parametrize("value,expected", [
    ("HÀM SỐ", "ham so"),
    (unicodedata.normalize("NFD", "Đạo hàm"), "dao ham"),
    ("Straße", "strasse"),
    ("ＨＡＭ", "ham"),
])
def test_folding_is_case_accent_and_unicode_normalization_independent(value, expected):
    assert fold_text(value) == expected


def test_query_parser_deduplicates_keywords_and_escapes_sql_patterns():
    assert parse_query("  HÀM\n hàm SỐ  ") == ("HÀM hàm SỐ", ("ham", "so"))
    assert literal_contains_pattern("100%_!") == "%100!%!_!!%"


@pytest.mark.parametrize("query", [None, 4, "", " \n\t ", "%_!", "\u200b", "\u034f", "text\x00", "\ud800", "x" * 401, " ".join(f"term{i}" for i in range(21))])
def test_invalid_query_is_rejected_without_repairing_or_truncating_it(query):
    with pytest.raises(ValueError):
        parse_query(query)


@pytest.mark.anyio
async def test_rank_matches_whole_terms_then_frequency_and_limit_after_matching():
    repository = make_repository()
    first = await add_source(repository, ["Tham số", "HÀM số", "Hàm hàm số số", "Hàm"])
    second = await add_source(repository, ["Hàm số"], title="Nguồn thứ hai")
    service = DocumentRetrievalService(repository)
    result = await service.search(1, "ham so", limit=3)
    assert [(item.chunk.document_id, item.chunk.chunk_index, item.score) for item in result.matches] == [
        (first, 2, 2), (first, 1, 2), (second, 0, 2),
    ]
    # A word embedded inside another word is not a match.
    only_ham = await service.search(1, "ham", limit=20)
    assert all(item.chunk.content != "Tham số" for item in only_ham.matches)
    assert (await service.search(1, "khôngtồntại")).matches == ()


@pytest.mark.anyio
async def test_retrieval_does_not_cap_before_filtering_and_keeps_topic_isolation():
    repository = make_repository()
    await add_source(repository, ["Đoạn không liên quan"] * 501 + ["Biệt thức Delta"])
    await add_source(repository, ["Biệt thức Delta"], topic_id=2)
    result = await DocumentRetrievalService(repository).search(1, "biet thuc", limit=1)
    assert len(result.matches) == 1
    assert result.matches[0].chunk.chunk_index == 501
    assert result.matches[0].chunk.topic_id == 1


@pytest.mark.anyio
async def test_only_ready_active_sources_are_used_and_no_sources_is_a_valid_empty_result():
    repository = make_repository()
    expected = await add_source(repository, ["Hàm số hợp lệ"])
    for status, active in (("ready", False), ("pending", True), ("error", True)):
        await add_source(repository, ["Hàm số bị loại"], status=status, active=active)
    result = await DocumentRetrievalService(repository).search(1, "ham so", limit=20)
    assert [match.chunk.document_id for match in result.matches] == [expected]
    assert (await DocumentRetrievalService(repository).search(2, "ham so")).matches == ()


@pytest.mark.anyio
@pytest.mark.parametrize("closed", ["topic", "subject", "missing"])
async def test_closed_or_missing_topic_cannot_start_new_retrieval(closed):
    repository = make_repository()
    await add_source(repository, ["Hàm số"])
    topic_id = 1
    if closed == "topic":
        repository._topics[1] = replace(repository._topics[1], is_active=False)
    elif closed == "subject":
        repository._subjects[1] = replace(repository._subjects[1], is_active=False)
    else:
        topic_id = 999
    with pytest.raises(AppError) as caught:
        await DocumentRetrievalService(repository).search(topic_id, "ham")
    assert caught.value.status_code == 404 and caught.value.code == "TOPIC_NOT_FOUND"


@pytest.mark.anyio
@pytest.mark.parametrize("topic_id,limit", [(True, 5), (0, 5), (2**31, 5), (1, True), (1, 0), (1, 21)])
async def test_internal_search_also_validates_topic_and_limit(topic_id, limit):
    with pytest.raises(AppError) as caught:
        await DocumentRetrievalService(make_repository()).search(topic_id, "ham", limit=limit)
    assert caught.value.status_code == 422
