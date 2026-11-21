"""Public keyword results contain source content and IDs, never server file paths."""

from pydantic import BaseModel, Field


class ChunkSearchItem(BaseModel):
    id: int
    document_id: int = Field(serialization_alias="documentId")
    document_title: str = Field(serialization_alias="documentTitle")
    topic_id: int = Field(serialization_alias="topicId")
    chunk_index: int = Field(serialization_alias="chunkIndex")
    content: str
    score: int
    similarity: float | None = None


class ChunkSearchResponse(BaseModel):
    topic_id: int = Field(serialization_alias="topicId")
    query: str
    limit: int
    search_mode: str = Field(default="keyword", serialization_alias="searchMode")
    chunks: list[ChunkSearchItem]
