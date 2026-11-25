"""Validate/save generated quizzes and keep reads private to their owner."""

from __future__ import annotations
import asyncio
from dataclasses import asdict
from contextlib import AbstractAsyncContextManager, asynccontextmanager
import re
from typing import Protocol
from sqlalchemy.exc import SQLAlchemyError
from app.config import Settings
from app.prompts.quiz import build_quiz_messages
from app.repositories.quiz_repository import (
    QuizAlreadySubmittedError, QuizAnswersRequiredError, QuizInvalidAnswersError,
    QuizOwnerUnavailableError, QuizRecord, QuizRepository, QuizGradeRecord,
)
from app.repositories.user_repository import User, parse_user_id
from app.schemas.quiz import (
    QuizItem, QuizQuestionItem, QuizResponse,
    QuizResultItem, QuizResultQuestion, QuizResultResponse,
    QuizSubmissionItem, QuizSubmissionResponse, SavedQuizAnswerItem, SubmitQuizAnswersRequest,
)
from app.services.catalog_service import CatalogService
from app.services.chat_context import redact_sensitive_text
from app.services.document_retrieval import DocumentRetrievalService
from app.services.llm_client import LLMClient
from app.utils.errors import AppError
from app.utils.async_tasks import finish_pending_task
from app.utils.keywords import text_terms
from app.validators.quiz import invalid_quiz_response, validate_generated_quiz
from app.schemas.quiz import QuizListResponse, QuizSummaryItem
from app.repositories.quiz_repository import (
    QuizAlreadySubmittedError, QuizInvalidAnswersError,
    QuizOwnerUnavailableError, QuizRecord, QuizRepository,
)
from app.schemas.quiz import (
    QuizItem, QuizQuestionItem, QuizResponse, QuizResultItem, QuizResultQuestionItem, QuizResultResponse,
    QuizSubmissionItem, QuizSubmissionResponse, SavedQuizAnswerItem, SubmitQuizAnswersRequest,
)





class QuizQuota(Protocol):
    def generation(self, user_id: int) -> AbstractAsyncContextManager: ...


class QuizService:
    def __init__(
        self, repository: QuizRepository, *, catalog_service: CatalogService | None = None,
        llm_client: LLMClient | None = None, settings: Settings | None = None,
        retrieval_service: DocumentRetrievalService | None = None, quota_service: QuizQuota | None = None,
    ) -> None:
        self._repository = repository
        self._catalog = catalog_service
        self._client = llm_client
        self._settings = settings or Settings()
        self._retrieval = retrieval_service
        self._quota = quota_service

    @asynccontextmanager
    async def _generation(self, user_id: int):
        if self._quota is None:
            yield
        else:
            async with self._quota.generation(user_id):
                yield

    def _redact(self, value: str, user: User) -> str:
        try:
            return redact_sensitive_text(
                value, known_name=user.name, known_email=user.email,
                secret_values=(user.password_hash, self._settings.jwt_secret, self._settings.llm_api_key),
            )
        except ValueError:
            raise AppError(422, "INVALID_QUIZ_CONTEXT", "Nội dung chủ đề hoặc tài liệu chưa hợp lệ.") from None

    async def list_quizzes(self, user: User, *, limit: int = 20, offset: int = 0) -> QuizListResponse:
        if not user.is_active or parse_user_id(user.id) is None:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.")
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 100000:
            raise AppError(422, "VALIDATION_ERROR", "Phân trang bài luyện tập không hợp lệ.")
        try:
            records = await self._repository.list_quizzes(user.id, limit=limit + 1, offset=offset)
        except SQLAlchemyError:
            raise AppError(503, "QUIZ_UNAVAILABLE", "Chưa thể tải lịch sử luyện tập. Vui lòng thử lại.") from None
        return QuizListResponse(
            quizzes=[QuizSummaryItem(**asdict(record)) for record in records[:limit]],
            limit=limit, offset=offset, has_more=len(records) > limit,
        )

    async def generate_quiz(self, user: User, topic_id: int, difficulty: str) -> QuizResponse:
        if not user.is_active or parse_user_id(user.id) is None:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.")
        if type(topic_id) is not int or parse_user_id(topic_id) is None or not isinstance(difficulty, str) or difficulty not in {"easy", "medium", "hard"}:
            raise AppError(422, "VALIDATION_ERROR", "Chủ đề hoặc độ khó không hợp lệ.")
        if self._catalog is None or self._client is None:
            raise AppError(503, "LLM_NOT_CONFIGURED", "Chưa cấu hình dịch vụ tạo bài luyện tập.")
        try:
            topic = await self._catalog.get_open_topic(topic_id)
        except SQLAlchemyError:
            raise AppError(503, "CATALOG_UNAVAILABLE", "Chưa thể tải chủ đề học tập. Vui lòng thử lại.") from None
        safe_topic = {
            "subject": self._redact(topic.subject_name, user)[:120],
            "grade": self._redact(topic.grade_level, user)[:50],
            "chapter": self._redact(topic.chapter_name, user)[:150],
            "name": self._redact(topic.name, user)[:180],
            "description": self._redact(topic.description or "", user)[:2000],
        }
        sources = []
        terms = tuple(dict.fromkeys(text_terms(safe_topic["name"] + " " + safe_topic["description"])))[:20]
        if self._retrieval is not None and terms:
            retrieved = await self._retrieval.search(topic_id, " ".join(terms)[:400], limit=3)
            for match in retrieved.matches:
                sources.append({
                    "title": self._redact(match.chunk.document_title, user)[:200],
                    "content": self._redact(match.chunk.content, user)[:1200],
                })
        async with self._generation(user.id):
            reply = await self._client.generate(build_quiz_messages(safe_topic, difficulty, sources))
            content = reply.content
            if not isinstance(content, str) or len(content) > 128_000:
                raise invalid_quiz_response()
            fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n\s*```", content.strip(), flags=re.DOTALL | re.IGNORECASE)
            generated = validate_generated_quiz(fenced.group(1).strip() if fenced else content)
            payload = generated.model_dump()
            for question in payload["questions"]:
                question["question_text"] = self._redact(question["question_text"], user)
                question["explanation"] = self._redact(question["explanation"], user)
                question["options"] = {letter: self._redact(value, user) for letter, value in question["options"].items()}
            # save_generated_quiz revalidates the redacted copy with the same
            # complete-quiz contract before opening a write transaction.
            # The SQL repository may still be committing in a worker thread when
            # the request is cancelled. Keep admission locked until that write ends.
            pending = asyncio.create_task(self.save_generated_quiz(user, topic_id, difficulty, payload))
            try:
                return await asyncio.shield(pending)
            except asyncio.CancelledError:
                try:
                    await finish_pending_task(pending)
                except Exception:
                    pass
                raise

    @staticmethod
    def _response(record: QuizRecord) -> QuizResponse:
        return QuizResponse(quiz=QuizItem(
            id=record.id, topic_id=record.topic_id, difficulty=record.difficulty, status=record.status,
            created_at=record.created_at, questions=[QuizQuestionItem(
                id=question.id, position=question.position, question_text=question.question_text, options=question.options,
            ) for question in record.questions],
        ))

    async def _owned_record(self, user: User, quiz_id: int) -> QuizRecord:
        if not user.is_active or parse_user_id(user.id) is None:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.")
        if not isinstance(quiz_id, int) or parse_user_id(quiz_id) is None:
            raise AppError(422, "VALIDATION_ERROR", "Mã bài luyện tập không hợp lệ.")
        try:
            record = await self._repository.find_quiz(user.id, quiz_id)
        except SQLAlchemyError:
            raise AppError(503, "QUIZ_UNAVAILABLE", "Chưa thể tải bài luyện tập. Vui lòng thử lại sau.") from None
        if record is None or record.user_id != user.id:
            # Deliberately identical for unknown IDs and another account's private quiz.
            raise AppError(404, "QUIZ_NOT_FOUND", "Không tìm thấy bài luyện tập của bạn.")
        return record

    async def get_quiz(self, user: User, quiz_id: int) -> QuizResponse:
        return self._response(await self._owned_record(user, quiz_id))

    async def get_result(self, user: User, quiz_id: int) -> QuizResultResponse:
        record = await self._owned_record(user, quiz_id)
        if record.status != "completed":
            raise AppError(409, "QUIZ_NOT_COMPLETED", "Bài luyện tập chưa được nộp và chấm điểm.")
        try:
            answers = await self._repository.find_answers(user.id, quiz_id)
        except SQLAlchemyError:
            raise AppError(503, "QUIZ_UNAVAILABLE", "Chưa thể tải kết quả bài luyện tập. Vui lòng thử lại.") from None
        by_question = {answer.question_id: answer for answer in answers}
        if (
            len(record.questions) != 5 or len(answers) != 5
            or set(by_question) != {question.id for question in record.questions}
            or record.score is None or record.completed_at is None
        ):
            raise AppError(409, "QUIZ_RESULT_UNAVAILABLE", "Kết quả bài luyện tập chưa đầy đủ.")
        return QuizResultResponse(result=QuizResultItem(
            quiz_id=record.id, topic_id=record.topic_id, difficulty=record.difficulty, score=float(record.score),
            correct_count=sum(answer.is_correct for answer in answers), total_count=5,
            completed_at=record.completed_at, questions=[QuizResultQuestion(
                id=question.id, position=question.position, question_text=question.question_text,
                options=question.options, user_answer=by_question[question.id].user_answer,
                correct_answer=question.correct_answer, is_correct=by_question[question.id].is_correct,
                explanation=question.explanation,
            ) for question in record.questions],
        ))

    async def save_generated_quiz(self, user: User, topic_id: int, difficulty: str, generated_payload: object) -> QuizResponse:
        """Called by the server's generation flow; user identity never comes from AI."""
        if not user.is_active or parse_user_id(user.id) is None:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.")
        if parse_user_id(topic_id) is None or not isinstance(topic_id, int) or not isinstance(difficulty, str) or difficulty not in {"easy", "medium", "hard"}:
            raise AppError(422, "VALIDATION_ERROR", "Chủ đề hoặc độ khó không hợp lệ.")
        generated = validate_generated_quiz(generated_payload)
        try:
            record = await self._repository.create_quiz(user.id, topic_id, difficulty, generated)
        except QuizOwnerUnavailableError:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.") from None
        except SQLAlchemyError:
            raise AppError(503, "QUIZ_SAVE_FAILED", "Chưa thể lưu bài luyện tập. Vui lòng thử lại sau.") from None
        if record is None:
            raise AppError(404, "TOPIC_NOT_FOUND", "Chủ đề không tồn tại hoặc chưa được mở.")
        return self._response(record)

    async def submit_answers(self, user: User, quiz_id: int, payload: SubmitQuizAnswersRequest) -> QuizSubmissionResponse:
        if not user.is_active or parse_user_id(user.id) is None:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.")
        if not isinstance(quiz_id, int) or parse_user_id(quiz_id) is None:
            raise AppError(422, "VALIDATION_ERROR", "Mã bài luyện tập không hợp lệ.")
        answer_map: dict[int, str] = {}
        for item in payload.answers:
            if item.question_id in answer_map:
                raise AppError(422, "INVALID_ANSWERS", "Mỗi câu hỏi chỉ được gửi đúng một câu trả lời.")
            answer_map[item.question_id] = item.user_answer
        return await self._grade(user, quiz_id, answer_map)

    async def grade_saved_answers(self, user: User, quiz_id: int) -> QuizSubmissionResponse:
        if not user.is_active or parse_user_id(user.id) is None:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.")
        if not isinstance(quiz_id, int) or parse_user_id(quiz_id) is None:
            raise AppError(422, "VALIDATION_ERROR", "Mã bài luyện tập không hợp lệ.")
        return await self._grade(user, quiz_id, None)

    async def _grade(self, user: User, quiz_id: int, answers: dict[int, str] | None) -> QuizSubmissionResponse:
        try:
            graded = await self._repository.grade_quiz(user.id, quiz_id, answers)
        except QuizAlreadySubmittedError:
            raise AppError(409, "ALREADY_SUBMITTED", "Bài luyện tập này đã được nộp hoặc chấm trước đó.") from None
        except QuizAnswersRequiredError:
            raise AppError(409, "ANSWERS_REQUIRED", "Bài luyện tập cần có đủ 5 câu trả lời đã lưu trước khi chấm.") from None
        except QuizInvalidAnswersError:
            raise AppError(422, "INVALID_ANSWERS", "Danh sách câu hỏi không khớp với bài luyện tập hiện tại.") from None
        except QuizOwnerUnavailableError:
            raise AppError(401, "ACCOUNT_INACTIVE", "Tài khoản không còn hoạt động.") from None
        except SQLAlchemyError:
            raise AppError(503, "QUIZ_SAVE_FAILED", "Chưa thể chấm và lưu bài luyện tập. Vui lòng thử lại sau.") from None
        if graded is None:
            raise AppError(404, "QUIZ_NOT_FOUND", "Không tìm thấy bài luyện tập của bạn.")
        return self._grade_response(graded)

    @staticmethod
    def _grade_response(graded: QuizGradeRecord) -> QuizSubmissionResponse:
        return QuizSubmissionResponse(submission=QuizSubmissionItem(
            quiz_id=graded.quiz_id,
            status="accepted",
            saved_count=len(graded.answers),
            answers=[SavedQuizAnswerItem(question_id=item.question_id, user_answer=item.user_answer) for item in graded.answers],
            quiz_status="completed", score=float(graded.score), correct_count=graded.correct_count,
            total_count=graded.total_count, completed_at=graded.completed_at,
        ))


    async def get_quiz_result(self, user: User, quiz_id: int) -> QuizResultResponse:
        return await self.get_result(user, quiz_id)
