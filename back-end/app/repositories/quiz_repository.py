"""Atomic quiz creation and owner-scoped reads, including each quiz's questions."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import utc_timestamp
from app.repositories.progress_repository import InMemoryProgressRepository, ProgressRecord
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
    score: Decimal | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class QuizSummaryRecord:
    id: int
    topic_id: int
    topic_name: str
    subject_name: str
    difficulty: str
    status: str
    created_at: str
    score: Decimal | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class QuizAnswerRecord:
    id: int
    question_id: int
    user_answer: str
    is_correct: bool
    created_at: str


@dataclass(frozen=True)
class QuizGradeRecord:
    quiz_id: int
    score: Decimal
    correct_count: int
    total_count: int
    completed_at: str
    answers: tuple[QuizAnswerRecord, ...]


class QuizOwnerUnavailableError(Exception):
    """The authenticated account no longer exists or is inactive at save time."""


class QuizAlreadySubmittedError(Exception):
    """Answers have already been saved or the quiz is no longer in progress."""


class QuizInvalidAnswersError(Exception):
    """Submitted question IDs do not match the exact 5 questions of this quiz."""


class QuizAnswersRequiredError(Exception):
    """A legacy quiz must have a complete set of saved answers before grading."""


def mastery_percent(correct_count: int, total_count: int) -> Decimal:
    return (Decimal(correct_count) * 100 / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total_count else Decimal("0.00")


class QuizRepository(Protocol):
    async def list_quizzes(self, user_id: int, *, limit: int, offset: int) -> list[QuizSummaryRecord]: ...

    async def create_quiz(self, user_id: int, topic_id: int, difficulty: QuizDifficulty, generated: GeneratedQuiz) -> QuizRecord | None: ...

    async def find_quiz(self, user_id: int, quiz_id: int) -> QuizRecord | None: ...

    async def find_answers(self, user_id: int, quiz_id: int) -> list[QuizAnswerRecord]: ...

    async def save_answers(self, user_id: int, quiz_id: int, answers: dict[int, str]) -> list[QuizAnswerRecord] | None: ...

    async def grade_quiz(self, user_id: int, quiz_id: int, answers: dict[int, str] | None = None) -> QuizGradeRecord | None: ...


    async def find_quiz_answers(self, user_id: int, quiz_id: int) -> list[QuizAnswerRecord] | None: ...



class InMemoryQuizRepository:
    def __init__(self, catalog_repository: InMemoryCatalogRepository | None = None, *, progress_repository: InMemoryProgressRepository | None = None) -> None:
        self._catalog = catalog_repository if catalog_repository is not None else InMemoryCatalogRepository()
        self._quizzes: dict[int, QuizRecord] = {}
        self._answers: dict[int, QuizAnswerRecord] = {}
        self._next_id = 1
        self._next_question_id = 1
        self._next_answer_id = 1
        self.progress_repository = progress_repository if progress_repository is not None else InMemoryProgressRepository()

    async def list_quizzes(self, user_id: int, *, limit: int, offset: int) -> list[QuizSummaryRecord]:
        records = sorted(
            (record for record in self._quizzes.values() if record.user_id == user_id),
            key=lambda record: (record.created_at, record.id), reverse=True,
        )[offset:offset + limit]
        summaries = []
        for record in records:
            topic = self._catalog._topics.get(record.topic_id, {})
            subject = self._catalog._subjects.get(topic.get("subject_id"), {})
            summaries.append(QuizSummaryRecord(
                id=record.id, topic_id=record.topic_id, topic_name=topic.get("name", ""),
                subject_name=subject.get("name", ""), difficulty=record.difficulty, status=record.status,
                created_at=record.created_at, score=record.score if record.status == "completed" else None,
                completed_at=record.completed_at,
            ))
        return summaries

    async def find_quiz(self, user_id: int, quiz_id: int) -> QuizRecord | None:
        record = self._quizzes.get(quiz_id)
        return record if record is not None and record.user_id == user_id else None

    async def find_answers(self, user_id: int, quiz_id: int) -> list[QuizAnswerRecord]:
        record = await self.find_quiz(user_id, quiz_id)
        if record is None:
            return []
        return [self._answers[question.id] for question in record.questions if question.id in self._answers]

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

    async def save_answers(self, user_id: int, quiz_id: int, answers: dict[int, str]) -> list[QuizAnswerRecord] | None:
        record = self._quizzes.get(quiz_id)
        if record is None or record.user_id != user_id:
            return None
        question_ids = {question.id for question in record.questions}
        if record.status != "in_progress" or any(qid in self._answers for qid in question_ids):
            raise QuizAlreadySubmittedError()
        if set(answers) != question_ids:
            raise QuizInvalidAnswersError()
        now = utc_timestamp(datetime.now(timezone.utc))
        saved: list[QuizAnswerRecord] = []
        for question in record.questions:
            choice = answers[question.id]
            saved.append(QuizAnswerRecord(
                id=self._next_answer_id + len(saved),
                question_id=question.id,
                user_answer=choice,
                is_correct=(choice == question.correct_answer),
                created_at=now,
            ))
        for item in saved:
            self._answers[item.question_id] = item
        self._next_answer_id += len(saved)
        return saved

    async def grade_quiz(self, user_id: int, quiz_id: int, answers: dict[int, str] | None = None) -> QuizGradeRecord | None:
        record = self._quizzes.get(quiz_id)
        if record is None or record.user_id != user_id:
            return None
        if record.status != "in_progress":
            raise QuizAlreadySubmittedError()
        question_ids = {question.id for question in record.questions}
        if len(record.questions) != 5 or len(question_ids) != 5 or {question.position for question in record.questions} != {1, 2, 3, 4, 5}:
            raise QuizInvalidAnswersError()
        existing = {qid: self._answers[qid] for qid in question_ids if qid in self._answers}
        if answers is None:
            if set(existing) != question_ids:
                raise QuizAnswersRequiredError()
            choices = {qid: answer.user_answer for qid, answer in existing.items()}
        else:
            if existing:
                raise QuizAlreadySubmittedError()
            choices = answers
        if set(choices) != question_ids or any(choice not in {"A", "B", "C", "D"} for choice in choices.values()):
            raise QuizInvalidAnswersError()
        now = utc_timestamp(datetime.now(timezone.utc))
        saved = tuple(
            replace(existing[question.id], is_correct=choices[question.id] == question.correct_answer)
            if question.id in existing else QuizAnswerRecord(
                id=self._next_answer_id + index, question_id=question.id,
                user_answer=choices[question.id], is_correct=choices[question.id] == question.correct_answer, created_at=now,
            )
            for index, question in enumerate(record.questions)
        )
        correct = sum(answer.is_correct for answer in saved)
        score = Decimal(correct * 20).quantize(Decimal("0.01"))
        rows = self.progress_repository._records
        old = next((row for row in rows.values() if row.user_id == user_id and row.topic_id == record.topic_id), None)
        total_correct = (old.correct_count if old else 0) + correct
        total_count = (old.total_count if old else 0) + 5
        progress = ProgressRecord(
            id=old.id if old else max(rows, default=0) + 1, user_id=user_id, topic_id=record.topic_id,
            total_quizzes=(old.total_quizzes if old else 0) + 1,
            correct_count=total_correct, total_count=total_count,
            mastery_percent=mastery_percent(total_correct, total_count), last_studied_at=now,
        )
        # All validation/calculation precedes publication; no await permits a partial read.
        rows[progress.id] = progress
        self._answers.update({answer.question_id: answer for answer in saved})
        self._quizzes[quiz_id] = replace(record, status="completed", score=score, completed_at=now)
        if not existing:
            self._next_answer_id += 5
        return QuizGradeRecord(quiz_id, score, correct, 5, now, saved)


    async def find_quiz_answers(self, user_id: int, quiz_id: int) -> list[QuizAnswerRecord] | None:
        record = self._quizzes.get(quiz_id)
        if record is None or record.user_id != user_id:
            return None
        return [self._answers[q.id] for q in record.questions if q.id in self._answers]
