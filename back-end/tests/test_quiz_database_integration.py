"""TK-052 MySQL persistence/rollback; uses only the existing random test DB fixture."""

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import LearningProgress, Quiz, QuizQuestion, Subject, Topic, User
from app.main import create_app
from app.repositories.sqlalchemy_quiz_repository import SqlAlchemyQuizRepository
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.services.quiz_service import QuizService
from app.utils.errors import AppError
from test_database_integration import database, make_catalog
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


async def make_service(sessions):
    with sessions.begin() as db:
        user, subject, topic = make_catalog(db)
        user_id, subject_id, topic_id = user.id, subject.id, topic.id
    user_record = await SqlAlchemyUserRepository(sessions).find_by_id(user_id)
    return QuizService(SqlAlchemyQuizRepository(sessions)), user_record, subject_id, topic_id


def counts(sessions, user_id):
    with sessions() as db:
        return (
            db.scalar(select(func.count()).select_from(Quiz).where(Quiz.user_id == user_id)),
            db.scalar(select(func.count()).select_from(QuizQuestion).join(Quiz).where(Quiz.user_id == user_id)),
        )


async def test_mysql_persists_complete_quiz_and_keeps_answers_out_of_view(database):
    _, sessions = database
    service, user, _, topic_id = await make_service(sessions)
    app = create_app(session_factory=sessions)
    response = await app.state.quiz_service.save_generated_quiz(user, topic_id, "medium", valid_payload())
    with sessions() as db:
        quiz = db.get(Quiz, response.quiz.id)
        assert quiz.user_id == user.id and quiz.topic_id == topic_id
        assert quiz.status == "in_progress" and quiz.difficulty == "medium"
        assert quiz.score is None and quiz.completed_at is None
        questions = list(db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.position)))
        assert [question.position for question in questions] == [1, 2, 3, 4, 5]
        assert all(question.options == {"A": "1", "B": "2", "C": "3", "D": "4"} for question in questions)
        assert all(question.correct_answer == "B" and question.explanation == "Một cộng một bằng hai." for question in questions)
        assert [question.id for question in questions] == [item.id for item in response.quiz.questions]
        assert db.scalar(select(func.count()).select_from(LearningProgress).where(LearningProgress.user_id == user.id)) == 0
    assert counts(sessions, user.id) == (1, 5)
    assert "explanation" not in response.model_dump_json() and "correct_answer" not in response.model_dump_json()


async def test_mysql_rolls_back_quiz_and_earlier_questions_when_last_insert_fails(database):
    _, sessions = database
    service, user, _, topic_id = await make_service(sessions)

    def reject_last_question(mapper, connection, question):
        if question.position == 5:
            raise SQLAlchemyError("Injected failure after four question writes")

    event.listen(QuizQuestion, "before_insert", reject_last_question)
    try:
        with pytest.raises(AppError) as caught:
            await service.save_generated_quiz(user, topic_id, "hard", valid_payload())
        assert caught.value.code == "QUIZ_SAVE_FAILED"
    finally:
        event.remove(QuizQuestion, "before_insert", reject_last_question)
    assert counts(sessions, user.id) == (0, 0)
    # Failed transactions must not poison the session factory or leave a partial quiz.
    await service.save_generated_quiz(user, topic_id, "hard", valid_payload())
    assert counts(sessions, user.id) == (1, 5)


async def test_mysql_invalid_last_question_never_creates_partial_quiz(database):
    _, sessions = database
    service, user, _, topic_id = await make_service(sessions)
    payload = valid_payload()
    payload["questions"][4]["options"].pop("D")
    with pytest.raises(AppError) as caught:
        await service.save_generated_quiz(user, topic_id, "easy", payload)
    assert caught.value.code == "QUIZ_INVALID_RESPONSE"
    assert counts(sessions, user.id) == (0, 0)


async def test_mysql_commit_failure_is_reported_and_all_questions_are_rolled_back(database):
    _, sessions = database
    service, user, _, topic_id = await make_service(sessions)

    def reject_commit(db):
        raise SQLAlchemyError("Injected commit failure")

    event.listen(sessions, "before_commit", reject_commit)
    try:
        with pytest.raises(AppError) as caught:
            await service.save_generated_quiz(user, topic_id, "easy", valid_payload())
        assert caught.value.code == "QUIZ_SAVE_FAILED"
    finally:
        event.remove(sessions, "before_commit", reject_commit)
    assert counts(sessions, user.id) == (0, 0)


@pytest.mark.parametrize("closed", ["topic", "subject"])
async def test_mysql_catalog_disabled_after_selection_prevents_save(database, closed):
    _, sessions = database
    service, user, subject_id, topic_id = await make_service(sessions)
    with sessions.begin() as db:
        row = db.get(Topic, topic_id) if closed == "topic" else db.get(Subject, subject_id)
        row.is_active = False
    with pytest.raises(AppError) as caught:
        await service.save_generated_quiz(user, topic_id, "easy", valid_payload())
    assert caught.value.code == "TOPIC_NOT_FOUND"
    assert counts(sessions, user.id) == (0, 0)


async def test_mysql_account_disabled_after_authentication_prevents_save(database):
    _, sessions = database
    service, user, _, topic_id = await make_service(sessions)
    with sessions.begin() as db:
        db.get(User, user.id).is_active = False
    assert user.is_active  # Simulate authentication before another request disabled it.
    with pytest.raises(AppError) as caught:
        await service.save_generated_quiz(user, topic_id, "easy", valid_payload())
    assert caught.value.code == "ACCOUNT_INACTIVE"
    assert counts(sessions, user.id) == (0, 0)
