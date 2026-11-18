"""TK-052: validate generated quiz data, then save the entire quiz atomically."""

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.quiz_repository import QuizOwnerUnavailableError, QuizRepository
from app.repositories.user_repository import User, parse_user_id
from app.schemas.quiz import QuizItem, QuizQuestionItem, QuizResponse
from app.utils.errors import AppError
from app.validators.quiz import validate_generated_quiz


class QuizService:
    def __init__(self, repository: QuizRepository) -> None:
        self._repository = repository

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
        return QuizResponse(quiz=QuizItem(
            id=record.id, topic_id=record.topic_id, difficulty=record.difficulty, status=record.status,
            created_at=record.created_at, questions=[QuizQuestionItem(
                id=question.id, position=question.position, question_text=question.question_text, options=question.options,
            ) for question in record.questions],
        ))
