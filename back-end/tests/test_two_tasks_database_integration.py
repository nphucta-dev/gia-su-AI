"""TK-044/TK-059 against the existing isolated, randomly named MySQL fixture."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
import unicodedata
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.models import Document, DocumentChunk, LearningProgress, Quiz, QuizAnswer, QuizQuestion, Subject, Topic, User
from test_database_integration import database, make_catalog
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


async def make_state(sessions):
    with sessions.begin() as db:
        owner, subject, topic = make_catalog(db)
        owner_id, subject_id, topic_id = owner.id, subject.id, topic.id
    app = create_app(session_factory=sessions, settings=Settings(jwt_secret="grading-search-test-" + "x" * 40))
    owner = await app.state.user_repository.find_by_id(owner_id)

    def headers(user_id):
        return {"Authorization": "Bearer " + app.state.token_service.create_access_token(user_id).access_token}

    return SimpleNamespace(app=app, owner=owner, owner_id=owner_id, subject_id=subject_id, topic_id=topic_id, headers=headers)


def client_for(state, user_id=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=state.app, raise_app_exceptions=False), base_url="http://test",
        headers=state.headers(state.owner_id if user_id is None else user_id),
    )


async def make_quiz(state):
    result = await state.app.state.quiz_service.save_generated_quiz(state.owner, state.topic_id, "medium", valid_payload())
    return result.quiz


def answers_for(quiz, correct_count=5):
    return {"answers": [
        {"questionId": question.id, "userAnswer": "B" if index < correct_count else "A"}
        for index, question in enumerate(quiz.questions)
    ]}


def saved_state(sessions, quiz_id, owner_id, topic_id):
    with sessions() as db:
        quiz = db.get(Quiz, quiz_id)
        answers = list(db.scalars(
            select(QuizAnswer).join(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.position)
        ))
        progress = db.scalar(select(LearningProgress).where(
            LearningProgress.user_id == owner_id, LearningProgress.topic_id == topic_id,
        ))
        return {
            "status": quiz.status, "score": quiz.score, "completed_at": quiz.completed_at,
            "answers": [(answer.question_id, answer.user_answer, answer.is_correct) for answer in answers],
            "progress": None if progress is None else (
                progress.total_quizzes, progress.correct_count, progress.total_count,
                progress.mastery_percent, progress.last_studied_at,
            ),
        }


async def seed_legacy_answers(sessions, quiz, correct_count):
    with sessions.begin() as db:
        # Simulate already accepted TK-058 rows; grading must derive correctness again.
        db.add_all([
            QuizAnswer(question_id=question.id, user_answer="B" if index < correct_count else "A", is_correct=False)
            for index, question in enumerate(quiz.questions)
        ])


async def test_mysql_submit_persists_score_completion_answers_and_progress_together(database):
    _, sessions = database
    state = await make_state(sessions)
    quiz = await make_quiz(state)
    async with client_for(state) as client:
        response = await client.post(f"/api/quizzes/{quiz.id}/submit", json=answers_for(quiz, 3))
        assert response.status_code == 200, response.text
        submission = response.json()["submission"]
        assert submission["status"] == "accepted"  # Existing frontend contract remains valid.
        assert submission["quizStatus"] == "completed" and submission["score"] == 60
        assert submission["correctCount"] == 3 and submission["totalCount"] == 5
        assert submission["savedCount"] == 5 and submission["completedAt"]
        assert response.headers["cache-control"] == "no-store"
        assert "correct_answer" not in response.text and "explanation" not in response.text
        stored = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)
        assert stored["status"] == "completed" and stored["score"] == Decimal("60.00")
        assert [item[2] for item in stored["answers"]] == [True, True, True, False, False]
        assert stored["completed_at"] is not None
        assert stored["progress"] == (1, 3, 5, Decimal("60.00"), stored["completed_at"])
        progress = await client.get("/api/progress")
        assert progress.status_code == 200
        assert progress.json()["progress"][0]["masteryPercent"] == 60
        assert (await client.post(f"/api/quizzes/{quiz.id}/submit", json=answers_for(quiz, 5))).status_code == 409
        assert (await client.post(f"/api/quizzes/{quiz.id}/grade")).status_code == 409
    assert saved_state(sessions, quiz.id, state.owner_id, state.topic_id) == stored


async def test_mysql_legacy_grading_keeps_saved_choices_and_recomputes_correctness(database):
    _, sessions = database
    state = await make_state(sessions)
    quiz = await make_quiz(state)
    await seed_legacy_answers(sessions, quiz, 4)
    before = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)
    assert before["score"] is None and before["progress"] is None
    async with client_for(state) as client:
        response = await client.post(f"/api/quizzes/{quiz.id}/grade")
        assert response.status_code == 200, response.text
        assert response.json()["submission"]["score"] == 80
        assert (await client.post(f"/api/quizzes/{quiz.id}/submit", json=answers_for(quiz, 5))).status_code == 409
    after = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)
    assert [(qid, choice) for qid, choice, _ in after["answers"]] == [(qid, choice) for qid, choice, _ in before["answers"]]
    assert [correct for _, _, correct in after["answers"]] == [True, True, True, True, False]
    assert after["status"] == "completed" and after["score"] == Decimal("80.00")
    assert after["progress"][:4] == (1, 4, 5, Decimal("80.00"))


@pytest.mark.parametrize("legacy", [False, True], ids=["new-submission", "legacy-grading"])
@pytest.mark.parametrize("phase", ["progress-write", "commit"])
async def test_mysql_late_grading_failure_rolls_back_every_change_and_can_retry(database, legacy, phase):
    engine, sessions = database
    state = await make_state(sessions)
    quiz = await make_quiz(state)
    if legacy:
        await seed_legacy_answers(sessions, quiz, 4)
    before = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)

    def reject_progress(connection, cursor, statement, parameters, context, executemany):
        sql = statement.lower().lstrip().replace("`", "")
        if sql.startswith(("insert into learning_progress", "update learning_progress")):
            raise SQLAlchemyError("Injected failure while persisting progress")

    def reject_commit(db):
        raise SQLAlchemyError("Injected final commit failure")

    target, hook, callback = (engine, "before_cursor_execute", reject_progress) if phase == "progress-write" else (sessions, "before_commit", reject_commit)
    event.listen(target, hook, callback)
    endpoint = f"/api/quizzes/{quiz.id}/{'grade' if legacy else 'submit'}"
    options = {} if legacy else {"json": answers_for(quiz, 3)}
    try:
        async with client_for(state) as client:
            response = await client.post(endpoint, **options)
            assert response.status_code == 503, response.text
            assert "Injected" not in response.text
    finally:
        event.remove(target, hook, callback)
    assert saved_state(sessions, quiz.id, state.owner_id, state.topic_id) == before
    async with client_for(state) as client:
        response = await client.post(endpoint, **options)
        assert response.status_code == 200, response.text
    after = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)
    assert len(after["answers"]) == 5 and after["progress"][0] == 1


async def test_mysql_concurrent_same_quiz_completes_once_and_counts_once(database):
    _, sessions = database
    state = await make_state(sessions)
    quiz = await make_quiz(state)
    async with client_for(state) as client:
        results = await asyncio.gather(*[
            client.post(f"/api/quizzes/{quiz.id}/submit", json=answers_for(quiz, 3)) for _ in range(2)
        ])
    assert sorted(response.status_code for response in results) == [200, 409], [response.text for response in results]
    stored = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)
    assert len(stored["answers"]) == 5 and stored["progress"][:4] == (1, 3, 5, Decimal("60.00"))


async def test_mysql_concurrent_different_quizzes_do_not_lose_shared_topic_progress(database):
    _, sessions = database
    state = await make_state(sessions)
    first, second = await make_quiz(state), await make_quiz(state)
    async with client_for(state) as client:
        results = await asyncio.gather(
            client.post(f"/api/quizzes/{first.id}/submit", json=answers_for(first, 3)),
            client.post(f"/api/quizzes/{second.id}/submit", json=answers_for(second, 4)),
        )
    assert [response.status_code for response in results] == [200, 200], [response.text for response in results]
    first_state = saved_state(sessions, first.id, state.owner_id, state.topic_id)
    second_state = saved_state(sessions, second.id, state.owner_id, state.topic_id)
    assert first_state["score"] == Decimal("60.00") and second_state["score"] == Decimal("80.00")
    assert first_state["progress"][:4] == (2, 7, 10, Decimal("70.00"))
    assert first_state["progress"][4] == max(first_state["completed_at"], second_state["completed_at"])


async def test_mysql_grade_and_submit_preserve_owner_scope_and_reject_wrong_question_ids(database):
    _, sessions = database
    state = await make_state(sessions)
    own = await make_quiz(state)
    second = await make_quiz(state)
    with sessions.begin() as db:
        outsiders = [User(email=f"{uuid4().hex}@example.com", full_name="Người khác", password_hash="test-only", role=role) for role in ("LEARNER", "ADMIN")]
        db.add_all(outsiders)
        db.flush()
        outsider_ids = [user.id for user in outsiders]
    before = saved_state(sessions, own.id, state.owner_id, state.topic_id)
    async with client_for(state) as client:
        for outsider_id in outsider_ids:
            headers = state.headers(outsider_id)
            for action in ("submit", "grade"):
                options = {"json": answers_for(own, 5)} if action == "submit" else {}
                foreign = await client.post(f"/api/quizzes/{own.id}/{action}?user_id={state.owner_id}", headers=headers, **options)
                missing = await client.post(f"/api/quizzes/{2**31 - 1}/{action}", headers=headers, **options)
                assert foreign.status_code == missing.status_code == 404
                assert foreign.json() == missing.json()
        assert (await client.post(f"/api/quizzes/{own.id}/submit", json=answers_for(second, 5))).status_code == 422
    assert saved_state(sessions, own.id, state.owner_id, state.topic_id) == before


async def test_mysql_grade_does_not_finalize_incomplete_legacy_answers(database):
    _, sessions = database
    state = await make_state(sessions)
    quiz = await make_quiz(state)
    with sessions.begin() as db:
        db.add(QuizAnswer(question_id=quiz.questions[0].id, user_answer="B", is_correct=False))
    before = saved_state(sessions, quiz.id, state.owner_id, state.topic_id)
    async with client_for(state) as client:
        response = await client.post(f"/api/quizzes/{quiz.id}/grade")
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "ANSWERS_REQUIRED"
    assert saved_state(sessions, quiz.id, state.owner_id, state.topic_id) == before


def add_document(db, topic_id, contents, *, active=True, status="ready", title="Tài liệu nguồn"):
    document = Document(topic_id=topic_id, title=title, file_path=f"test-only-{uuid4().hex}.txt", status=status, is_active=active)
    db.add(document)
    db.flush()
    chunks = [DocumentChunk(document_id=document.id, chunk_index=index, content=content) for index, content in enumerate(contents)]
    db.add_all(chunks)
    db.flush()
    return [chunk.id for chunk in chunks]


@pytest.mark.parametrize("content,query", [
    ("Đạo hàm bậc hai", "DAO HAM"),
    (unicodedata.normalize("NFD", "Hàm số"), "ham so"),
    ("Straße", "STRASSE"),
    ("ｈａｍ", "ham"),
    ("đạo", "dao"),
    ("dao ham", unicodedata.normalize("NFD", "ĐẠO HÀM")),
], ids=["vietnamese-case", "nfd-content", "casefold-expansion", "fullwidth", "crossed-d", "nfd-query"])
async def test_mysql_keyword_candidates_match_python_unicode_normalization(database, content, query):
    _, sessions = database
    state = await make_state(sessions)
    with sessions.begin() as db:
        [chunk_id] = add_document(db, state.topic_id, [content])
    async with client_for(state) as client:
        response = await client.get(f"/api/catalog/topics/{state.topic_id}/chunks", params={"q": query})
        assert response.status_code == 200, response.text
        assert [chunk["id"] for chunk in response.json()["chunks"]] == [chunk_id]


async def test_mysql_keyword_filtering_precedes_ranking_and_limit(database):
    _, sessions = database
    state = await make_state(sessions)
    with sessions.begin() as db:
        ids = add_document(db, state.topic_id, ["Diện tích tam giác"] * 24 + ["ham ham ham", "ham"])
    async with client_for(state) as client:
        response = await client.get(f"/api/catalog/topics/{state.topic_id}/chunks", params={"q": "ham", "limit": 1})
        assert response.status_code == 200, response.text
        assert [chunk["id"] for chunk in response.json()["chunks"]] == [ids[-2]]
        assert response.json()["chunks"][0]["score"] == 1
        no_match = await client.get(f"/api/catalog/topics/{state.topic_id}/chunks", params={"q": "khongcoketqua"})
        assert no_match.status_code == 200 and no_match.json()["chunks"] == []


async def test_mysql_search_only_reads_ready_active_sources_in_the_selected_open_catalog(database):
    _, sessions = database
    state = await make_state(sessions)
    keyword = "nguonduocchon"
    with sessions.begin() as db:
        [valid_id] = add_document(db, state.topic_id, [keyword], title="Nguồn hợp lệ")
        add_document(db, state.topic_id, [keyword], active=False)
        add_document(db, state.topic_id, [keyword], status="pending")
        add_document(db, state.topic_id, [keyword], status="error")
        other_topic = Topic(subject_id=state.subject_id, chapter_name="Chương khác", name="Chủ đề khác")
        db.add(other_topic)
        db.flush()
        add_document(db, other_topic.id, [keyword])
    path = f"/api/catalog/topics/{state.topic_id}/chunks"
    async with client_for(state) as client:
        result = await client.get(path, params={"q": keyword})
        assert result.status_code == 200, result.text
        assert [chunk["id"] for chunk in result.json()["chunks"]] == [valid_id]
        assert "file_path" not in result.text and "test-only-" not in result.text
        with sessions.begin() as db:
            db.get(Topic, state.topic_id).is_active = False
        assert (await client.get(path, params={"q": keyword})).status_code == 404
        with sessions.begin() as db:
            db.get(Topic, state.topic_id).is_active = True
            db.get(Subject, state.subject_id).is_active = False
        assert (await client.get(path, params={"q": keyword})).status_code == 404
