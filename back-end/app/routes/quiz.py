"""Quiz reads are private to the authenticated account, including their questions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.routes.auth import require_json
from app.schemas.auth import ErrorResponse
from app.schemas.quiz import QuizResponse, QuizSubmissionResponse, SubmitQuizAnswersRequest
from app.services.quiz_service import QuizService


router = APIRouter(
    prefix="/api/quizzes", tags=["quiz"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)},
)
CurrentUser = Annotated[User, Depends(get_current_user)]
QuizId = Annotated[int, Path(ge=1, le=2**31 - 1)]


def get_service(request: Request) -> QuizService:
    return request.app.state.quiz_service


@router.get("/{quiz_id}", response_model=QuizResponse, summary="Đọc bài luyện tập của chính mình")
async def get_quiz(
    quiz_id: QuizId, user: CurrentUser, service: Annotated[QuizService, Depends(get_service)],
) -> QuizResponse:
    return await service.get_quiz(user, quiz_id)


@router.post(
    "/{quiz_id}/submit",
    response_model=QuizSubmissionResponse,
    dependencies=[Depends(require_json)],
    summary="Lưu 01 câu trả lời cho mỗi câu hỏi của bài luyện tập",
)
async def submit_quiz_answers(
    quiz_id: QuizId,
    payload: SubmitQuizAnswersRequest,
    user: CurrentUser,
    service: Annotated[QuizService, Depends(get_service)],
) -> QuizSubmissionResponse:
    return await service.submit_answers(user, quiz_id, payload)
