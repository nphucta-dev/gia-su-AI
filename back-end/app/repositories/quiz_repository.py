"""Atomic quiz creation and owner-scoped reads, including each quiz's questions."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import utc_timestamp
from app.schemas.quiz import GeneratedQuiz, QuizDifficulty


@dataclass(frozen=True)
class QuizQuestionRecord:
    id: int
    position: int
    question_text: str
    options: dict[str, str]
    correct_answer: str = field(repr=False)
    explanation: str = field(repr=False)


@dataclass(frozen=True)
class QuizRecord:
    id: int
    user_id: int
    topic_id: int
    difficulty: str
    status: str
    created_at: str
    questions: tuple[QuizQuestionRecord, ...]


class QuizOwnerUnavailableError(Exception):
    """The authenticated account no longer exists or is inactive at save time."""


class QuizRepository(Protocol):
    async def create_quiz(self, user_id: int, topic_id: int, difficulty: QuizDifficulty, generated: GeneratedQuiz) -> QuizRecord | None: ...

    async def find_quiz(self, user_id: int, quiz_id: int) -> QuizRecord | None: ...


class InMemoryQuizRepository:
    def __init__(self, catalog_repository: InMemoryCatalogRepository | None = None) -> None:
        self._catalog = catalog_repository if catalog_repository is not None else InMemoryCatalogRepository()
        self._quizzes: dict[int, QuizRecord] = {}
        self._next_id = 1
        self._next_question_id = 1

    async def find_quiz(self, user_id: int, quiz_id: int) -> QuizRecord | None:
        record = self._quizzes.get(quiz_id)
        return record if record is not None and record.user_id == user_id else None

    async def create_quiz(self, user_id: int, topic_id: int, difficulty: QuizDifficulty, generated: GeneratedQuiz) -> QuizRecord | None:
        topic = self._catalog._topics.get(topic_id)
        subject = self._catalog._subjects.get(topic["subject_id"]) if topic else None
        if topic is None or subject is None or not topic["is_active"] or not subject["is_active"]:
            return None
        questions = tuple(
            QuizQuestionRecord(
                id=self._next_question_id + offset, position=offset + 1, question_text=item.question_text,
                options=item.options.model_dump(), correct_answer=item.correct_answer, explanation=item.explanation,
            ) for offset, item in enumerate(generated.questions)
        )
        record = QuizRecord(
            id=self._next_id, user_id=user_id, topic_id=topic_id, difficulty=difficulty,
            status="in_progress", created_at=utc_timestamp(datetime.now(timezone.utc)), questions=questions,
        )
        # Publish only the complete set; no await/partial mutation during assembly.
        self._quizzes[record.id] = record
        self._next_id += 1
        self._next_question_id += len(questions)
        return record
