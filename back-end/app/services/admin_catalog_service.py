"""Tạo, sửa và bật/tắt danh mục; giữ nguyên bản ghi và các liên kết lịch sử."""

from dataclasses import asdict
from typing import Any, Protocol
from unicodedata import category

from app.repositories.catalog_repository import (
    AdminSubject, AdminTopic, CatalogConflictError, CatalogSubjectNotFoundError,
)
from app.schemas.admin_catalog import AdminSubjectItem, AdminTopicItem
from app.utils.errors import AppError


class AdminCatalogRepository(Protocol):
    async def list_admin_subjects(self) -> list[AdminSubject]: ...
    async def list_admin_topics(self) -> list[AdminTopic]: ...
    async def create_subject(self, values: dict) -> AdminSubject: ...
    async def update_subject(self, subject_id: int, changes: dict) -> AdminSubject | None: ...
    async def create_topic(self, values: dict) -> AdminTopic: ...
    async def update_topic(self, topic_id: int, changes: dict) -> AdminTopic | None: ...


def invalid_text(value: str) -> bool:
    """Không lưu surrogate/control không biểu diễn được trong UTF-8 hay giao diện."""
    return any(category(char) == "Cs" or (category(char) == "Cc" and not char.isspace()) for char in value)


def validate_input(payload: Any, *, topic: bool, partial: bool) -> dict:
    text_fields = {"name": ("name", 180 if topic else 120)}
    text_fields.update({"chapterName": ("chapter_name", 150)} if topic else {"gradeLevel": ("grade_level", 50)})
    allowed = set(text_fields) | ({"subjectId", "description"} if topic else set())
    if partial:
        allowed.add("isActive")
    errors: dict[str, str] = {}
    result: dict = {}
    if not isinstance(payload, dict) or not payload:
        raise AppError(422, "VALIDATION_ERROR", "Dữ liệu danh mục chưa hợp lệ.", {"body": "Gửi một đối tượng JSON có ít nhất một trường."})
    for key in payload.keys() - allowed:
        errors[key] = "Trường này không được phép cập nhật."
    for public_name, (internal_name, limit) in text_fields.items():
        if partial and public_name not in payload:
            continue
        value = payload.get(public_name)
        if not isinstance(value, str):
            errors[public_name] = "Vui lòng nhập chuỗi ký tự hợp lệ."
            continue
        value = " ".join(value.split())
        if not value or len(value) > limit or invalid_text(value):
            errors[public_name] = f"Vui lòng nhập từ 1 đến {limit} ký tự."
        else:
            result[internal_name] = value
    if topic:
        if not partial or "subjectId" in payload:
            value = payload.get("subjectId")
            if type(value) is not int or not 1 <= value <= 2**31 - 1:
                errors["subjectId"] = "Vui lòng chọn môn học hợp lệ."
            else:
                result["subject_id"] = value
        if "description" in payload:
            value = payload["description"]
            if value is not None and (not isinstance(value, str) or invalid_text(value) or len(value.encode("utf-8")) > 65535):
                errors["description"] = "Mô tả phải là văn bản tối đa 65535 byte hoặc null."
            else:
                result["description"] = value.strip() or None if value is not None else None
    if partial and "isActive" in payload:
        if type(payload["isActive"]) is not bool:
            errors["isActive"] = "Trạng thái phải là true hoặc false."
        else:
            result["is_active"] = payload["isActive"]
    if errors:
        raise AppError(422, "VALIDATION_ERROR", "Dữ liệu danh mục chưa hợp lệ.", errors)
    return result


class AdminCatalogService:
    def __init__(self, repository: AdminCatalogRepository) -> None:
        self._repository = repository

    async def list_subjects(self) -> list[AdminSubjectItem]:
        return [AdminSubjectItem(**asdict(item)) for item in await self._repository.list_admin_subjects()]

    async def list_topics(self) -> list[AdminTopicItem]:
        return [AdminTopicItem(**asdict(item)) for item in await self._repository.list_admin_topics()]

    async def save_subject(self, payload: Any, subject_id: int | None = None) -> AdminSubjectItem:
        values = validate_input(payload, topic=False, partial=subject_id is not None)
        try:
            item = await self._repository.create_subject(values) if subject_id is None else await self._repository.update_subject(subject_id, values)
        except CatalogConflictError:
            raise AppError(409, "SUBJECT_ALREADY_EXISTS", "Môn học cùng tên và cấp học đã tồn tại.", {"name": "Tên môn và cấp học này đã được sử dụng."}) from None
        if item is None:
            raise AppError(404, "SUBJECT_NOT_FOUND", "Môn học không tồn tại.")
        return AdminSubjectItem(**asdict(item))

    async def save_topic(self, payload: Any, topic_id: int | None = None) -> AdminTopicItem:
        values = validate_input(payload, topic=True, partial=topic_id is not None)
        try:
            item = await self._repository.create_topic(values) if topic_id is None else await self._repository.update_topic(topic_id, values)
        except CatalogConflictError:
            raise AppError(409, "TOPIC_ALREADY_EXISTS", "Chủ đề cùng tên trong môn và chương đã tồn tại.", {"name": "Tên chủ đề đã được sử dụng trong môn và chương này."}) from None
        except CatalogSubjectNotFoundError:
            raise AppError(404, "SUBJECT_NOT_FOUND", "Môn học không tồn tại.", {"subjectId": "Vui lòng chọn môn học đang tồn tại."}) from None
        if item is None:
            raise AppError(404, "TOPIC_NOT_FOUND", "Chủ đề không tồn tại.")
        return AdminTopicItem(**asdict(item))
