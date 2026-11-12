"""Kiểm tra file, lưu file riêng tư và tạo metadata tài liệu chờ xử lý."""

from __future__ import annotations

import asyncio
import codecs
import re
import unicodedata
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import UploadFile

from app.repositories.document_repository import DocumentRecord, DocumentRepository, missing_topic_error
from app.repositories.user_repository import parse_user_id
from app.schemas.document import DocumentInfo, UploadSubjectInfo, UploadTopicInfo
from app.utils.errors import AppError

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
_MIME_TYPES = {".pdf": "application/pdf", ".txt": "text/plain"}


def invalid_field(field: str, message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", "Dữ liệu tải tài liệu chưa hợp lệ.", {field: message})


class DocumentService:
    def __init__(self, repository: DocumentRepository, upload_dir: Path) -> None:
        self.repository = repository
        self.upload_dir = upload_dir.resolve()

    async def options(self) -> list[UploadSubjectInfo]:
        return [
            UploadSubjectInfo(
                id=subject.id,
                name=subject.name,
                grade_level=subject.grade_level,
                topics=[UploadTopicInfo(id=topic.id, name=topic.name, chapter_name=topic.chapter_name) for topic in subject.topics],
            )
            for subject in await self.repository.list_subjects()
        ]

    async def list_documents(self) -> list[DocumentInfo]:
        records = await self.repository.list_documents()
        return await asyncio.to_thread(lambda: [self._public_document(record) for record in records])

    async def upload(self, *, topic_id: object, title: object, file: UploadFile) -> DocumentInfo:
        parsed_id = parse_user_id(topic_id) if isinstance(topic_id, (str, int)) else None
        if parsed_id is None:
            raise invalid_field("topic_id", "Vui lòng chọn chủ đề hợp lệ.")
        if not isinstance(title, str):
            raise invalid_field("title", "Vui lòng nhập tiêu đề tài liệu.")
        title = title.strip()
        if not title or len(title) > 200:
            raise invalid_field("title", "Tiêu đề tài liệu phải có từ 1 đến 200 ký tự.")
        if any(unicodedata.category(char) in {"Cc", "Cs"} for char in title):
            raise invalid_field("title", "Tiêu đề tài liệu chứa ký tự không hợp lệ.")
        if await self.repository.find_upload_topic(parsed_id) is None:
            raise missing_topic_error()

        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        extension_match = re.search(r"\.(pdf|txt)$", filename, re.IGNORECASE)
        if extension_match is None or "\x00" in filename:
            raise invalid_field("file", "Định dạng không hợp lệ. Hãy chọn tệp PDF hoặc TXT.")
        extension = extension_match.group(0).lower()
        media_type = (file.content_type or "").split(";", 1)[0].strip().lower()
        if media_type != _MIME_TYPES[extension]:
            raise invalid_field("file", "Loại nội dung của tệp không khớp định dạng PDF/TXT.")

        payload = bytearray()
        decoder = codecs.getincrementaldecoder("utf-8-sig")() if extension == ".txt" else None
        while True:
            chunk = await file.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            if len(payload) + len(chunk) > MAX_DOCUMENT_BYTES:
                raise AppError(413, "FILE_TOO_LARGE", "Tệp vượt quá giới hạn 10 MB.", {"file": "Tệp tối đa 10 MB."})
            if decoder is not None:
                try:
                    decoded = decoder.decode(chunk)
                except UnicodeDecodeError:
                    raise invalid_field("file", "Tệp TXT phải là văn bản mã hóa UTF-8.") from None
                if "\x00" in decoded:
                    raise invalid_field("file", "Tệp TXT chứa dữ liệu không phải văn bản hợp lệ.")
            payload.extend(chunk)
        if not payload:
            raise invalid_field("file", "Tệp tài liệu không được để trống.")
        if decoder is not None:
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                raise invalid_field("file", "Tệp TXT phải là văn bản mã hóa UTF-8.") from None
        elif not payload.startswith(b"%PDF-"):
            raise invalid_field("file", "Nội dung tệp không phải định dạng PDF hợp lệ.")

        storage_name = uuid4().hex + extension
        saved_path = self.upload_dir / storage_name
        await asyncio.to_thread(self._save_file, saved_path, payload)
        try:
            record = await self.repository.create(topic_id=parsed_id, title=title, file_path=storage_name)
        except Exception:
            # Chỉ xóa đúng file vừa tạo khi transaction metadata không thành công.
            await asyncio.to_thread(saved_path.unlink, missing_ok=True)
            raise
        return self._public_document(record)

    def _save_file(self, path: Path, payload: bytearray) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        created = False
        try:
            with path.open("xb") as output:
                created = True
                output.write(payload)
        except Exception:
            # open('xb') không ghi đè file có sẵn; chỉ dọn file tạo dở trong lượt này.
            if created:
                path.unlink(missing_ok=True)
            raise

    def _public_document(self, record: DocumentRecord) -> DocumentInfo:
        size: int | None = None
        relative_path = Path(record.file_path)
        # Chỉ stat file nằm trực tiếp trong kho riêng, không truy cập đường dẫn metadata cũ ngoài kho.
        if relative_path.name == record.file_path and not relative_path.is_absolute():
            candidate = self.upload_dir / relative_path
            try:
                if candidate.resolve().parent == self.upload_dir and candidate.is_file():
                    size = candidate.stat().st_size
            except OSError:
                pass
        extension = relative_path.suffix.lower()
        if extension not in _MIME_TYPES:
            extension = ""
        display_name = record.title if record.title.lower().endswith(extension) else record.title + extension
        return DocumentInfo(
            id=record.id,
            topic_id=record.topic_id,
            title=record.title,
            subject_name=record.subject_name,
            topic_name=record.topic_name,
            status=record.status,
            is_active=record.is_active,
            created_at=record.created_at,
            size_bytes=size,
            file_name=display_name,
        )
