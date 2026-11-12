from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, Boolean, CheckConstraint, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.topic import Topic


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    ERROR = "error"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'ready', 'error')", name="ck_documents_status"),
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
    topic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("topics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=DocumentStatus.PENDING.value,
        server_default=text("'pending'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    topic: Mapped[Topic] = relationship("Topic", back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
