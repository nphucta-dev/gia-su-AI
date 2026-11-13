"""Đọc nội dung thực và kiểm tra tính đầy đủ/thứ tự của đoạn tài liệu."""

import io
import unicodedata

import pytest
from pypdf import PdfWriter, get_configuration
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services import document_text
from app.services.document_text import (
    CHUNK_OVERLAP, CHUNK_SIZE, DocumentTextError, extract_document_text, split_document_text,
)


def pdf_bytes(*texts: str, encrypted=False, compressed=False) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        if text:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream.flate_encode() if compressed else stream)
    if encrypted:
        writer.encrypt("private-test-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_txt_bom_unicode_and_paragraph_whitespace(tmp_path):
    source = tmp_path / "source.TXT"
    text = "\ufeff  Hàm\t số  bậc hai\r\n\r\n\r\n  Δ = b² − 4ac.  \rGiải\vphương trình.\x07"
    source.write_bytes(unicodedata.normalize("NFD", text).encode("utf-8"))
    extracted = extract_document_text(source)
    assert extracted == "Hàm số bậc hai\n\nΔ = b² − 4ac.\nGiải phương trình."
    assert unicodedata.is_normalized("NFC", extracted)


def test_real_pdf_pages_have_text_in_original_order(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(pdf_bytes("First page: x squared + 2x + 1.", "Second page: (x + 1) squared."))
    extracted = extract_document_text(source)
    assert "First page: x squared + 2x + 1." in extracted
    assert "Second page: (x + 1) squared." in extracted
    assert extracted.index("First page") < extracted.index("Second page")


def test_compressed_pdf_text_and_scoped_configuration(tmp_path):
    source = tmp_path / "compressed.pdf"
    source.write_bytes(pdf_bytes("Compressed text", compressed=True))
    before = get_configuration()
    assert extract_document_text(source) == "Compressed text"
    assert get_configuration() is before


@pytest.mark.parametrize("name,content", [
    ("empty.txt", b""), ("blank.txt", b" \r\n\t "),
    ("utf16.txt", b"\xff\xfe\x00x"), ("binary.txt", b"hello\x00binary"),
    ("broken.pdf", b"%PDF-1.4\nbroken"), ("wrong.pdf", b"Hello PDF"),
    ("image-only.pdf", pdf_bytes("")), ("encrypted.pdf", pdf_bytes("Locked text", encrypted=True)),
    ("unsupported.docx", b"unsupported"),
])
def test_unprocessable_documents_have_safe_controlled_errors(tmp_path, name, content):
    source = tmp_path / name
    source.write_bytes(content)
    with pytest.raises(DocumentTextError) as failure:
        extract_document_text(source)
    assert str(tmp_path) not in str(failure.value)
    assert "private-test-password" not in str(failure.value)


def test_missing_file_is_controlled_without_internal_path(tmp_path):
    with pytest.raises(DocumentTextError) as failure:
        extract_document_text(tmp_path / "missing.txt")
    assert str(tmp_path) not in str(failure.value)


def test_file_byte_and_text_character_limits(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_bytes(b"a" * 21)
    monkeypatch.setattr(document_text, "MAX_FILE_BYTES", 20)
    with pytest.raises(DocumentTextError):
        extract_document_text(source)
    monkeypatch.setattr(document_text, "MAX_FILE_BYTES", 100)
    monkeypatch.setattr(document_text, "MAX_EXTRACTED_CHARS", 20)
    with pytest.raises(DocumentTextError):
        extract_document_text(source)


def test_pdf_page_count_limit(tmp_path, monkeypatch):
    source = tmp_path / "pages.pdf"
    source.write_bytes(pdf_bytes("Page one", "Page two"))
    monkeypatch.setattr(document_text, "MAX_PDF_PAGES", 1)
    with pytest.raises(DocumentTextError, match="200"):
        extract_document_text(source)


def test_pdf_decompressed_stream_limit(tmp_path, monkeypatch):
    source = tmp_path / "stream.pdf"
    source.write_bytes(pdf_bytes("x" * 5000, compressed=True))
    monkeypatch.setattr(document_text, "MAX_PAGE_STREAM_BYTES", 1024)
    before = get_configuration()
    with pytest.raises(DocumentTextError):
        extract_document_text(source)
    assert get_configuration() is before


def test_pdf_extracted_character_limit(tmp_path, monkeypatch):
    source = tmp_path / "long.pdf"
    source.write_bytes(pdf_bytes("a" * 40))
    monkeypatch.setattr(document_text, "MAX_EXTRACTED_CHARS", 20)
    with pytest.raises(DocumentTextError):
        extract_document_text(source)


def test_short_text_is_one_nonempty_chunk():
    assert split_document_text("  Giải   phương trình\r\nx² + 2x + 1 = 0.  ") == ["Giải phương trình\nx² + 2x + 1 = 0."]


def test_chunks_preserve_all_words_in_order_with_bounded_overlap():
    words = [f"từ{index:05d}" for index in range(1800)]
    source = " ".join(words)
    chunks = split_document_text(source)
    assert len(chunks) > 1
    assert chunks == split_document_text(source)
    covered = []
    previous_last = -1
    for chunk in chunks:
        assert 0 < len(chunk) <= CHUNK_SIZE
        indices = [int(word[2:]) for word in chunk.split()]
        assert indices == list(range(indices[0], indices[-1] + 1))
        assert indices[0] <= previous_last + 1
        assert indices[-1] > previous_last
        covered.extend(indices)
        previous_last = indices[-1]
    assert set(covered) == set(range(len(words)))
    for previous, current in zip(chunks, chunks[1:]):
        overlap = set(previous.split()) & set(current.split())
        assert overlap and len(" ".join(overlap)) <= CHUNK_OVERLAP


def test_paragraph_boundary_is_preferred_near_end():
    first = "a " * 430
    second = "b " * 300
    chunks = split_document_text(first + "\n\n" + second)
    assert chunks[0].endswith("a")
    assert "b" not in chunks[0]
    assert "b" in chunks[-1]


def test_long_unbroken_word_always_advances_and_covers_entire_text():
    text = "x" * (CHUNK_SIZE * 3 + 17)
    chunks = split_document_text(text)
    assert all(0 < len(chunk) <= CHUNK_SIZE for chunk in chunks)
    reconstructed = chunks[0] + "".join(chunk[CHUNK_OVERLAP:] for chunk in chunks[1:])
    assert reconstructed == text


@pytest.mark.parametrize("text", ["", "  \n\t ", None])
def test_empty_or_nontext_input_never_produces_ready_chunks(text):
    with pytest.raises(DocumentTextError):
        split_document_text(text)


def test_split_applies_text_and_chunk_count_limits(monkeypatch):
    monkeypatch.setattr(document_text, "MAX_EXTRACTED_CHARS", 20)
    with pytest.raises(DocumentTextError):
        split_document_text("x" * 21)
    monkeypatch.setattr(document_text, "MAX_EXTRACTED_CHARS", 10000)
    monkeypatch.setattr(document_text, "MAX_CHUNKS", 1)
    with pytest.raises(DocumentTextError):
        split_document_text("word " * 1000)


def test_normalized_unicode_expansion_still_obeys_character_limit(monkeypatch):
    monkeypatch.setattr(document_text, "MAX_EXTRACTED_CHARS", 20)
    assert len(unicodedata.normalize("NFC", "\u0344" * 11)) == 22
    with pytest.raises(DocumentTextError):
        split_document_text("\u0344" * 11)
