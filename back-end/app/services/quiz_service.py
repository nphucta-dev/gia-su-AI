"""Validate/save generated quizzes and keep reads private to their owner."""

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.quiz_repository import (
    QuizAlreadySubmittedError, QuizInvalidAnswersError,
    QuizOwnerUnavailableError, QuizRecord, QuizRepository,
)
from app.repositories.user_repository import User, parse_user_id
from app.schemas.quiz import (
    QuizItem, QuizQuestionItem, QuizResponse,
    QuizSubmissionItem, QuizSubmissionResponse, SavedQuizAnswerItem, SubmitQuizAnswersRequest,
)
from app.utils.errors import AppError
from app.validators.quiz import validate_generated_quiz


class QuizService:
    def __init__(self, repository: QuizRepository) -> None:
        self._repository = repository

    @staticmethod
    def _response(record: QuizRecord) -> QuizResponse:
        return QuizResponse(quiz=QuizItem(
            id=record.id, topic_id=record.topic_id, difficulty=record.difficulty, status=record.status,
            created_at=record.created_at, questions=[QuizQuestionItem(
                id=question.id, position=question.position, question_text=question.question_text, options=question.options,
            ) for question in record.questions],
        ))

    async def get_quiz(self, user: User, quiz_id: int) -> QuizResponse:
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
        return self._response(record)

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
        try:
            saved = await self._repository.save_answers(user.id, quiz_id, answer_map)
        except QuizAlreadySubmittedError:
            raise AppError(409, "ALREADY_SUBMITTED", "Bài luyện tập này đã được lưu câu trả lời trước đó.") from None
        except QuizInvalidAnswersError:
            raise AppError(422, "INVALID_ANSWERS", "Danh sách câu hỏi không khớp với bài luyện tập hiện tại.") from None
        except SQLAlchemyError:
            raise AppError(503, "QUIZ_SAVE_FAILED", "Chưa thể lưu câu trả lời. Vui lòng thử lại sau.") from None
        if saved is None:
            raise AppError(404, "QUIZ_NOT_FOUND", "Không tìm thấy bài luyện tập của bạn.")
        return QuizSubmissionResponse(submission=QuizSubmissionItem(
            quiz_id=quiz_id,
            status="accepted",
            saved_count=len(saved),
            answers=[SavedQuizAnswerItem(question_id=item.question_id, user_answer=item.user_answer) for item in saved],
        ))
