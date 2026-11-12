from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    JSON,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_chunk_index"),
        CheckConstraint(
            "embedding IS NULL OR (JSON_TYPE(embedding) = 'ARRAY' AND JSON_LENGTH(embedding) = 768)",
            name="ck_document_chunks_embedding",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_as_cs",
        },
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
