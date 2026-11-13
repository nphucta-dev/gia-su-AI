"""API chat riêng từng tài khoản; model chỉ được gọi qua service ở backend."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.routes.auth import require_json
from app.schemas.auth import ErrorResponse
from app.schemas.chat import (
    ChatMessageListResponse, ChatReplyResponse, ChatSessionListResponse, ChatSessionResponse,
    CreateChatSessionRequest, SendChatMessageRequest,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"], responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 502, 503, 504)})
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionId = Annotated[int, Path(ge=1, le=2**31 - 1)]
Offset = Annotated[int, Query(ge=0, le=100000)]


def get_service(request: Request) -> ChatService:
    return request.app.state.chat_service


Service = Annotated[ChatService, Depends(get_service)]


@router.post("/sessions", status_code=201, response_model=ChatSessionResponse, dependencies=[Depends(require_json)], summary="Tạo phiên chat theo chủ đề đang mở")
async def create_session(payload: CreateChatSessionRequest, user: CurrentUser, service: Service) -> ChatSessionResponse:
    return await service.create_session(user, payload.topic_id, payload.title)


@router.get("/sessions", response_model=ChatSessionListResponse, summary="Lịch sử phiên chat của tài khoản hiện tại")
async def list_sessions(user: CurrentUser, service: Service, limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Offset = 0) -> ChatSessionListResponse:
    return await service.list_sessions(user, limit=limit, offset=offset)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(session_id: SessionId, user: CurrentUser, service: Service) -> ChatSessionResponse:
    return await service.get_session(user, session_id)


@router.get("/sessions/{session_id}/messages", response_model=ChatMessageListResponse, summary="Tin nhắn trong phiên chat của chính mình")
async def list_messages(session_id: SessionId, user: CurrentUser, service: Service, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Offset = 0) -> ChatMessageListResponse:
    return await service.list_messages(user, session_id, limit=limit, offset=offset)


@router.post("/sessions/{session_id}/messages", status_code=201, response_model=ChatReplyResponse, dependencies=[Depends(require_json)], summary="Lưu câu hỏi và gọi gia sư với ngữ cảnh gần nhất")
async def send_message(session_id: SessionId, payload: SendChatMessageRequest, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.send_message(user, session_id, payload.content)


@router.post("/sessions/{session_id}/hints", status_code=201, response_model=ChatReplyResponse, summary="Gợi ý tiếp theo; server quyết định mức 1–3")
async def next_hint(session_id: SessionId, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.next_hint(user, session_id)
