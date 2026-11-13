"""Trích văn bản và chia đoạn tài liệu PDF/TXT, không gọi dịch vụ AI.

Các giới hạn dưới đây là lựa chọn triển khai cho tài liệu tải lên tối đa 10 MiB.
PDF phải có lớp văn bản; ảnh quét và PDF có mật khẩu không được xử lý bằng OCR.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader, apply_configuration


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_EXTRACTED_CHARS = 1_000_000
MAX_PAGE_STREAM_BYTES = 4 * 1024 * 1024
MAX_CHUNKS = 2000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


class DocumentTextError(ValueError):
    """Tệp không có văn bản hợp lệ hoặc vượt giới hạn xử lý."""


def _normalize_text(text: str) -> str:
    if len(text) > MAX_EXTRACTED_CHARS:
        raise DocumentTextError("Nội dung tài liệu vượt quá giới hạn 1.000.000 ký tự.")
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    text = "".join(
        character for character in text
        if character.isspace() or unicodedata.category(character) not in {"Cc", "Cs"}
    )
    lines = [" ".join(line.split()) for line in text.lstrip("\ufeff").split("\n")]
    normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(normalized) > MAX_EXTRACTED_CHARS:
        raise DocumentTextError("Nội dung tài liệu vượt quá giới hạn 1.000.000 ký tự.")
    return normalized


def extract_document_text(path: Path) -> str:
    """Đọc file có giới hạn; trả văn bản sạch hoặc lỗi có thông báo an toàn."""
    extension = path.suffix.lower()
    if extension not in {".pdf", ".txt"}:
        raise DocumentTextError("Chỉ xử lý tài liệu PDF hoặc TXT.")
    try:
        with path.open("rb") as source:
            payload = source.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise DocumentTextError("Không thể đọc tệp tài liệu đã lưu.") from None
    if not payload:
        raise DocumentTextError("Tệp tài liệu không có nội dung.")
    if len(payload) > MAX_FILE_BYTES:
        raise DocumentTextError("Tệp tài liệu vượt quá giới hạn 10 MiB.")

    if extension == ".txt":
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DocumentTextError("Tệp TXT phải là văn bản mã hóa UTF-8.") from None
        if "\x00" in text:
            raise DocumentTextError("Tệp TXT chứa dữ liệu không phải văn bản hợp lệ.")
    else:
        text = _extract_pdf(payload)
    text = _normalize_text(text)
    if not text:
        raise DocumentTextError("Tài liệu không có văn bản có thể trích xuất.")
    return text


def _extract_pdf(payload: bytes) -> str:
    if not payload.startswith(b"%PDF-"):
        raise DocumentTextError("Nội dung tệp không phải PDF hợp lệ.")
    try:
        # Cấu hình theo execution context của pypdf, không sửa giới hạn toàn cục.
        with apply_configuration(
            maximum_declared_stream_length=MAX_FILE_BYTES,
            array_based_stream_maximum_output_length=MAX_PAGE_STREAM_BYTES,
            zlib_maximum_output_length=MAX_PAGE_STREAM_BYTES,
            lzw_maximum_output_length=MAX_PAGE_STREAM_BYTES,
            run_length_maximum_output_length=MAX_PAGE_STREAM_BYTES,
            brotli_maximum_output_length=MAX_PAGE_STREAM_BYTES,
            image_maximum_buffer_size=MAX_PAGE_STREAM_BYTES,
            jbig2dec_binary=None,
            stream_decoding_work_maximum_length=MAX_PAGE_STREAM_BYTES * 2,
            stream_parsing_work_maximum_count=100_000,
            page_tree_maximum_entries=MAX_PDF_PAGES * 8,
            xform_maximum_invocations_per_extraction=100,
        ):
            reader = PdfReader(io.BytesIO(payload), strict=False, xref_stream_maximum_entries=100_000)
            try:
                if reader.is_encrypted:
                    raise DocumentTextError("PDF có mật khẩu hoặc mã hóa chưa được hỗ trợ.")
                if len(reader.pages) > MAX_PDF_PAGES:
                    raise DocumentTextError("PDF vượt quá giới hạn 200 trang.")
                parts: list[str] = []
                total_length = 0
                for page in reader.pages:
                    stream = page.get_contents()
                    if stream is not None and len(stream.get_data()) > MAX_PAGE_STREAM_BYTES:
                        raise DocumentTextError("Nội dung một trang PDF vượt quá giới hạn xử lý.")
                    text = page.extract_text() or ""
                    total_length += len(text) + (2 if parts else 0)
                    if total_length > MAX_EXTRACTED_CHARS:
                        raise DocumentTextError("Nội dung tài liệu vượt quá giới hạn 1.000.000 ký tự.")
                    parts.append(text)
                result = "\n\n".join(parts)
            finally:
                reader.close()
    except DocumentTextError:
        raise
    except Exception:
        # Lỗi cấu trúc/giải mã PDF từ thư viện không được trả traceback hoặc nội dung file cho client.
        raise DocumentTextError("Không thể đọc PDF. Hãy kiểm tra tệp có bị hỏng hoặc quá phức tạp không.") from None
    if not result.strip():
        raise DocumentTextError("PDF không có lớp văn bản có thể trích xuất. Hãy dùng PDF có văn bản hoặc TXT.")
    return result


def split_document_text(text: str) -> list[str]:
    """Chia theo ranh giới đoạn/từ, tối đa 1000 ký tự; chồng lấp tới 150 ký tự.

    Các từ dài hơn giới hạn được cắt theo ký tự để luôn tiến về phía trước.
    Vị trí trong danh sách là thứ tự dùng để lưu ``chunk_index`` bắt đầu từ 0.
    """
    if not isinstance(text, str):
        raise DocumentTextError("Nội dung tài liệu phải là văn bản.")
    text = _normalize_text(text)
    if not text:
        raise DocumentTextError("Tài liệu không có văn bản để chia đoạn.")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            lower_bound = start + CHUNK_SIZE * 3 // 4
            # Ưu tiên kết thúc đoạn; chỉ tìm gần cuối để tránh tạo quá nhiều đoạn ngắn.
            for separator in ("\n\n", "\n", " "):
                boundary = text.rfind(separator, lower_bound, end)
                if boundary != -1:
                    end = boundary + len(separator)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if len(chunks) > MAX_CHUNKS:
            raise DocumentTextError("Tài liệu tạo quá nhiều đoạn văn bản.")
        if end == len(text):
            break
        next_start = max(start + 1, end - CHUNK_OVERLAP)
        # Giữ các từ trong phần chồng lấp nguyên vẹn khi có thể.
        if next_start > 0 and not text[next_start - 1].isspace():
            boundary = next((position for position in range(next_start, end) if text[position].isspace()), None)
            if boundary is not None:
                next_start = boundary + 1
        while next_start < len(text) and text[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks
