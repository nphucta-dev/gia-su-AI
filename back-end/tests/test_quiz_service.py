"""Save the full set, keep answer keys private and leave no quiz on invalid output."""

from dataclasses import replace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.quiz_repository import InMemoryQuizRepository, QuizOwnerUnavailableError
from app.repositories.user_repository import InMemoryUserRepository, User
from app.services.quiz_service import QuizService
from app.utils.errors import AppError
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


def quiz_service():
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phép cộng")
    repository = InMemoryQuizRepository(catalog)
    user = User(7, "Người học", "learner@example.com", "private-hash", "LEARNER", "2026-11-18T00:00:00Z")
    return QuizService(repository), repository, catalog, subject_id, topic_id, user


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
async def test_save_stores_five_questions_with_server_owner_and_safe_view(difficulty):
    service, repository, _, _, topic_id, user = quiz_service()
    result = await service.save_generated_quiz(user, topic_id, difficulty, valid_payload())
    saved = repository._quizzes[result.quiz.id]
    assert saved.user_id == user.id and saved.topic_id == topic_id
    assert saved.difficulty == difficulty and saved.status == "in_progress"
    assert [item.position for item in saved.questions] == [1, 2, 3, 4, 5]
    assert all(item.correct_answer == "B" and item.explanation for item in saved.questions)
    assert len({item.id for item in saved.questions}) == 5
    body = result.model_dump(by_alias=True)
    assert body["quiz"]["topicId"] == topic_id
    for question in body["quiz"]["questions"]:
        assert set(question) == {"id", "position", "questionText", "options"}
        assert set(question["options"]) == {"A", "B", "C", "D"}
    assert "correct_answer" not in body and "explanation" not in result.model_dump_json()


async def test_quiz_and_question_ids_increase_for_separate_users():
    service, repository, _, _, topic_id, user = quiz_service()
    first = await service.save_generated_quiz(user, topic_id, "easy", valid_payload())
    second = await service.save_generated_quiz(replace(user, id=8), topic_id, "hard", valid_payload())
    assert first.quiz.id < second.quiz.id
    assert first.quiz.questions[-1].id < second.quiz.questions[0].id
    assert [quiz.user_id for quiz in repository._quizzes.values()] == [7, 8]


async def test_validation_completes_before_repository_is_called():
    class UntouchedRepository:
        async def create_quiz(self, *args):
            pytest.fail("Invalid quiz must never reach a write transaction")
    _, _, _, _, topic_id, user = quiz_service()
    payload = valid_payload()
    payload["questions"][4]["explanation"] = " "
    with pytest.raises(AppError) as caught:
        await QuizService(UntouchedRepository()).save_generated_quiz(user, topic_id, "easy", payload)
    assert caught.value.code == "QUIZ_INVALID_RESPONSE"


@pytest.mark.parametrize("closed", ["topic", "subject", "missing"])
async def test_closed_or_missing_catalog_saves_nothing(closed):
    service, repository, catalog, subject_id, topic_id, user = quiz_service()
    if closed == "topic":
        catalog._topics[topic_id]["is_active"] = False
    elif closed == "subject":
        catalog._subjects[subject_id]["is_active"] = False
    else:
        topic_id = 999
    with pytest.raises(AppError) as caught:
        await service.save_generated_quiz(user, topic_id, "easy", valid_payload())
    assert caught.value.code == "TOPIC_NOT_FOUND"
    assert repository._quizzes == {}


@pytest.mark.parametrize("topic_id,difficulty", [(True, "easy"), (0, "easy"), (2**31, "easy"), ("1", "easy"), (1, "Easy"), (1, None), (1, {}), (1, [])])
async def test_bad_metadata_saves_nothing(topic_id, difficulty):
    service, repository, _, _, _, user = quiz_service()
    with pytest.raises(AppError) as caught:
        await service.save_generated_quiz(user, topic_id, difficulty, valid_payload())
    assert caught.value.status_code == 422
    assert repository._quizzes == {}


async def test_inactive_account_cannot_save():
    service, repository, _, _, topic_id, user = quiz_service()
    with pytest.raises(AppError) as caught:
        await service.save_generated_quiz(replace(user, is_active=False), topic_id, "easy", valid_payload())
    assert caught.value.status_code == 401
    assert repository._quizzes == {}


@pytest.mark.parametrize("error,code,status", [(SQLAlchemyError("provider output private details"), "QUIZ_SAVE_FAILED", 503), (QuizOwnerUnavailableError(), "ACCOUNT_INACTIVE", 401)])
async def test_storage_failures_have_safe_messages(error, code, status):
    class FailedRepository:
        async def create_quiz(self, *args):
            raise error
    _, _, _, _, topic_id, user = quiz_service()
    with pytest.raises(AppError) as caught:
        await QuizService(FailedRepository()).save_generated_quiz(user, topic_id, "medium", valid_payload())
    assert caught.value.status_code == status and caught.value.code == code
    assert "private details" not in caught.value.message


async def test_app_uses_shared_catalog_and_explicit_repository_injection():
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phép cộng")
    users = InMemoryUserRepository()
    user = await users.create(name="Người học", email="learner@example.com", password_hash="hash", role="LEARNER")
    settings = Settings(jwt_secret="quiz-test-secret-" + "x" * 40)
    app = create_app(user_repository=users, catalog_repository=catalog, settings=settings)
    result = await app.state.quiz_service.save_generated_quiz(user, topic_id, "easy", valid_payload())
    assert result.quiz.topic_id == topic_id and len(result.quiz.questions) == 5
    catalog._subjects[subject_id]["is_active"] = False
    with pytest.raises(AppError) as caught:
        await app.state.quiz_service.save_generated_quiz(user, topic_id, "easy", valid_payload())
    assert caught.value.code == "TOPIC_NOT_FOUND"
    catalog._subjects[subject_id]["is_active"] = True
    repository = InMemoryQuizRepository(catalog)
    app = create_app(user_repository=users, catalog_repository=catalog, settings=settings, quiz_repository=repository)
    result = await app.state.quiz_service.save_generated_quiz(user, topic_id, "hard", valid_payload())
    assert repository._quizzes[result.quiz.id].user_id == user.id
