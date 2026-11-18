"""MySQL quiz + five questions are committed together or rolled back together."""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.quiz import Quiz
from app.models.quiz_question import QuizQuestion
from app.models.subject import Subject
from app.models.topic import Topic
from app.models.user import User
from app.repositories.chat_repository import utc_timestamp
from app.repositories.quiz_repository import QuizOwnerUnavailableError, QuizQuestionRecord, QuizRecord
from app.schemas.quiz import GeneratedQuiz, QuizDifficulty


class SqlAlchemyQuizRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def create_quiz(self, user_id: int, topic_id: int, difficulty: QuizDifficulty, generated: GeneratedQuiz) -> QuizRecord | None:
        return await asyncio.to_thread(self._create_quiz, user_id, topic_id, difficulty, generated)

    def _create_quiz(self, user_id: int, topic_id: int, difficulty: QuizDifficulty, generated: GeneratedQuiz) -> QuizRecord | None:
        with self._sessions.begin() as db:
            owner = db.scalar(select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update())
            if owner is None:
                raise QuizOwnerUnavailableError()
            row = db.execute(
                select(Topic, Subject).join(Subject, Subject.id == Topic.subject_id)
                .where(Topic.id == topic_id).with_for_update()
            ).first()
            if row is None or not row[0].is_active or not row[1].is_active:
                return None
            now = db.scalar(select(func.utc_timestamp(6)))
            quiz = Quiz(user_id=user_id, topic_id=topic_id, difficulty=difficulty, status="in_progress", created_at=now)
            db.add(quiz)
            db.flush()
            records = []
            for position, item in enumerate(generated.questions, start=1):
                question = QuizQuestion(
                    quiz_id=quiz.id, position=position, question_text=item.question_text,
                    options=item.options.model_dump(), correct_answer=item.correct_answer, explanation=item.explanation,
                )
                db.add(question)
                db.flush()
                records.append(QuizQuestionRecord(
                    id=question.id, position=position, question_text=question.question_text,
                    options=dict(question.options), correct_answer=question.correct_answer, explanation=question.explanation,
                ))
            return QuizRecord(
                id=quiz.id, user_id=quiz.user_id, topic_id=quiz.topic_id, difficulty=quiz.difficulty,
                status=quiz.status, created_at=utc_timestamp(quiz.created_at), questions=tuple(records),
            )
