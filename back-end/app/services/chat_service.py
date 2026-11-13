"""Phiên và tin nhắn thật, ngữ cảnh riêng tư, điều phối thang gợi ý 1–3."""

from contextlib import asynccontextmanager
from dataclasses import asdict
import unicodedata

from app.config import Settings
from app.prompts import SocraticTopic
from app.repositories.chat_repository import ChatChangedError, ChatMessageRecord, ChatRepository, ChatSessionRecord
from app.repositories.user_repository import User
from app.schemas.chat import (
    ChatMessageItem, ChatMessageListResponse, ChatReplyResponse, ChatSessionItem,
    ChatSessionListResponse, ChatSessionResponse,
)
from app.services.chat_context import build_chat_messages, redact_sensitive_text
from app.services.llm_client import LLMClient
from app.utils.errors import AppError


def session_item(record: ChatSessionRecord) -> ChatSessionItem:
    values = asdict(record)
    return ChatSessionItem(**{name: values[name] for name in ChatSessionItem.model_fields})


def message_item(record: ChatMessageRecord) -> ChatMessageItem:
    return ChatMessageItem(**asdict(record))


def missing_session() -> AppError:
    return AppError(404, "CHAT_SESSION_NOT_FOUND", "Không tìm thấy phiên chat của bạn.")


def changed_session() -> AppError:
    return AppError(409, "CHAT_CHANGED", "Hội thoại vừa được cập nhật. Hãy xem lại lịch sử trước khi gửi tiếp.")


class ChatService:
    def __init__(self, repository: ChatRepository, client: LLMClient, settings: Settings) -> None:
        self._repository = repository
        self._client = client
        self._settings = settings
        self._busy: set[int] = set()

    @asynccontextmanager
    async def _generating(self, session_id: int):
        if session_id in self._busy:
            raise AppError(409, "CHAT_BUSY", "Phiên chat đang chờ phản hồi. Vui lòng thử lại sau.")
        self._busy.add(session_id)
        try:
            yield
        finally:
            self._busy.discard(session_id)

    async def _find(self, user_id: int, session_id: int) -> ChatSessionRecord:
        record = await self._repository.find_session(user_id, session_id)
        if record is None:
            raise missing_session()
        return record

    @staticmethod
    def _require_open(session: ChatSessionRecord) -> None:
        if not session.topic_active or not session.subject_active:
            raise AppError(409, "TOPIC_CLOSED", "Môn học hoặc chủ đề đã tắt. Bạn vẫn có thể xem lịch sử.")

    async def create_session(self, user: User, topic_id: int, title: str | None) -> ChatSessionResponse:
        if title is not None:
            if any(unicodedata.category(char) in {"Cc", "Cs"} and not char.isspace() for char in title):
                raise AppError(422, "VALIDATION_ERROR", "Tiêu đề phiên chat không hợp lệ.")
            title = " ".join(title.split()) or None
        record = await self._repository.create_session(user.id, topic_id, title)
        if record is None:
            raise AppError(404, "TOPIC_NOT_FOUND", "Chủ đề không tồn tại hoặc chưa được mở.")
        return ChatSessionResponse(session=session_item(record))

    async def list_sessions(self, user: User, *, limit: int, offset: int) -> ChatSessionListResponse:
        records = await self._repository.list_sessions(user.id, limit=limit + 1, offset=offset)
        return ChatSessionListResponse(
            sessions=[session_item(item) for item in records[:limit]], limit=limit, offset=offset,
            has_more=len(records) > limit,
        )

    async def get_session(self, user: User, session_id: int) -> ChatSessionResponse:
        return ChatSessionResponse(session=session_item(await self._find(user.id, session_id)))

    async def list_messages(self, user: User, session_id: int, *, limit: int, offset: int) -> ChatMessageListResponse:
        session = await self._find(user.id, session_id)
        records = await self._repository.list_messages(user.id, session_id, limit=limit + 1, offset=offset)
        return ChatMessageListResponse(
            session=session_item(session), messages=[message_item(item) for item in records[:limit]],
            limit=limit, offset=offset, has_more=len(records) > limit,
        )

    def _privacy(self, user: User) -> dict:
        # Các giá trị này chỉ dùng để lọc bản sao; không đưa tài khoản vào payload LLM.
        return {
            "known_name": user.name, "known_email": user.email,
            "secret_values": (user.password_hash, self._settings.llm_api_key, self._settings.jwt_secret),
        }

    async def send_message(self, user: User, session_id: int, content: str) -> ChatReplyResponse:
        session = await self._find(user.id, session_id)
        self._require_open(session)
        content = content.strip()
        # Giữ hợp đồng đầu vào tối thiểu của API gửi tin và bộ tạo prompt.
        if not content or any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in content):
            raise AppError(422, "VALIDATION_ERROR", "Nội dung tin nhắn không hợp lệ.")
        async with self._generating(session_id):
            saved = await self._repository.append_user_message(user.id, session_id, content)
            if saved is None:
                raise missing_session()
            response = await self._reply(user, session, expected_last_id=saved.id, hint_level=1)
            response.user_message = message_item(saved)
            return response

    async def next_hint(self, user: User, session_id: int) -> ChatReplyResponse:
        session = await self._find(user.id, session_id)
        self._require_open(session)
        async with self._generating(session_id):
            history = await self._repository.recent_messages(user.id, session_id, limit=24)
            question = next((item for item in reversed(history) if item.role == "user"), None)
            if question is None:
                raise AppError(409, "CHAT_QUESTION_REQUIRED", "Hãy gửi một câu hỏi trước khi xin gợi ý.")
            levels = [item.hint_level or 0 for item in history if item.role == "assistant" and item.id > question.id]
            level = max(levels, default=0) + 1
            if level > 3:
                raise AppError(409, "HINT_LIMIT_REACHED", "Bạn đã nhận đủ 3 mức gợi ý cho câu hỏi này.")
            return await self._reply(user, session, expected_last_id=history[-1].id, hint_level=level, history=history)

    async def _reply(
        self, user: User, session: ChatSessionRecord, *, expected_last_id: int, hint_level: int,
        history: list[ChatMessageRecord] | None = None,
    ) -> ChatReplyResponse:
        if history is None:
            history = await self._repository.recent_messages(user.id, session.id, limit=24)
        if not history or history[-1].id != expected_last_id:
            raise changed_session()
        try:
            messages = build_chat_messages(
                topic=SocraticTopic(
                    subject_name=session.subject_name, topic_name=session.topic_name, grade_level=session.grade_level,
                    chapter_name=session.chapter_name, description=session.topic_description,
                ),
                history=[{"role": item.role, "content": item.content} for item in history],
                hint_level=hint_level, **self._privacy(user),
            )
        except ValueError:
            raise AppError(422, "INVALID_CHAT_CONTEXT", "Ngữ cảnh hội thoại chưa hợp lệ. Tin nhắn đã được lưu.") from None
        try:
            reply = await self._client.generate(messages)
        except AppError as error:
            raise AppError(error.status_code, error.code, error.message + " Tin nhắn đã gửi vẫn được lưu trong lịch sử.", headers=error.headers) from None
        try:
            content = redact_sensitive_text(reply.content, **self._privacy(user))
        except ValueError:
            raise AppError(502, "LLM_INVALID_RESPONSE", "Gia sư chưa trả về nội dung hợp lệ. Câu hỏi của bạn đã được lưu.") from None
        if not content.strip() or len(content) > 8000:
            raise AppError(502, "LLM_INVALID_RESPONSE", "Gia sư chưa trả về nội dung hợp lệ. Câu hỏi của bạn đã được lưu.")
        try:
            saved = await self._repository.append_assistant_message(
                user.id, session.id, content, hint_level=hint_level, token_count=reply.token_count,
                expected_last_id=expected_last_id,
            )
        except ChatChangedError:
            raise changed_session() from None
        if saved is None:
            raise missing_session()
        current = await self._find(user.id, session.id)
        return ChatReplyResponse(session=session_item(current), assistant_message=message_item(saved))
