"""TK-095 demo sources are real, self-contained UTF-8 learning documents."""

from collections import Counter
import json
from pathlib import Path
import shutil
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

import app.db.seed as seed_module
from app.db.seed import SAMPLE_SUBJECTS
from app.services.document_text import extract_document_text, split_document_text


SOURCE_DIR = Path(__file__).resolve().parents[1] / "app" / "db" / "demo_documents"


def manifest():
    return json.loads((SOURCE_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_demo_catalog_has_five_topics_per_subject_and_preserves_existing_names():
    assert len(SAMPLE_SUBJECTS) == 2
    assert all(5 <= len(topics) <= 10 for _, _, topics in SAMPLE_SUBJECTS)
    topics = {
        (subject, grade, chapter, topic)
        for subject, grade, entries in SAMPLE_SUBJECTS
        for chapter, topic in entries
    }
    assert len(topics) == 10
    assert {
        ("Toán", "THPT", "Hàm số", "Hàm số bậc hai"),
        ("Toán", "THPT", "Đại số", "Phương trình bậc hai"),
        ("Vật lí", "THPT", "Cơ học", "Chuyển động thẳng đều"),
    } <= topics
    rows = manifest()
    assert {(row["subject"], row["grade_level"], row["chapter_name"], row["topic_name"]) for row in rows} == topics
    assert Counter(row["subject"] for row in rows) == {"Toán": 5, "Vật lí": 5}


def test_every_seed_topic_has_its_own_extractable_source_and_nonempty_chunks():
    rows = manifest()
    assert len(rows) == len({row["file_name"] for row in rows}) == 10
    assert {row["file_name"] for row in rows} == {path.name for path in SOURCE_DIR.glob("*.txt")}
    for row in rows:
        name = row["file_name"]
        assert Path(name).name == name and Path(name).suffix == ".txt"
        assert isinstance(row["title"], str) and 0 < len(row["title"]) <= 200
        source = SOURCE_DIR / name
        raw = source.read_bytes()
        assert raw and len(raw) <= 10 * 1024 * 1024
        assert "\x00" not in raw.decode("utf-8-sig")
        text = extract_document_text(source)
        assert row["title"].casefold() in text.casefold()
        chunks = split_document_text(text)
        assert chunks and all(chunk.strip() and len(chunk) <= 1000 for chunk in chunks)
        assert all(word in " ".join(chunks) for word in (text.split()[0], text.split()[-1]))


def test_demo_source_provenance_is_included_with_the_sources():
    readme = (SOURCE_DIR / "README.md").read_text(encoding="utf-8")
    assert "CC0" in readme
    assert "Gia Sư AI" in readme


@pytest.mark.parametrize("failure", ["missing-file", "empty-file", "unsafe-path"])
def test_invalid_bundled_source_fails_before_any_database_write(failure, tmp_path, monkeypatch):
    source = tmp_path / "sources"
    shutil.copytree(SOURCE_DIR, source)
    rows = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    path = source / rows[-1]["file_name"]
    if failure == "missing-file":
        path.unlink()
    elif failure == "empty-file":
        path.write_bytes(b"")
    else:
        rows[-1]["file_name"] = "../outside.txt"
        (source / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(seed_module, "DEMO_DOCUMENT_DIR", source)
    db = Mock(spec=Session)
    with pytest.raises((OSError, ValueError)):
        seed_module.seed_data(db, upload_dir=tmp_path / "uploads")
    assert db.mock_calls == []
    assert not (tmp_path / "uploads").exists()
