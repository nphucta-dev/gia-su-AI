"""TK-046: Embedding client và tính toán độ tương đồng vector (768 chiều).

CSDL hiện tại dùng MySQL lưu embedding dạng JSON array 768 phần tử (nullable).
Embedding/vector search là tính năng bổ sung (Could): khi chưa cấu hình provider
hoặc lỗi gọi API, hệ thống tự động fallback về tìm kiếm từ khóa.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 768


class EmbeddingError(Exception):
    """Lỗi khi tạo vector embedding từ provider."""


class EmbeddingProvider(Protocol):
    @property
    def is_configured(self) -> bool: ...

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


def validate_embedding(
    vector: Sequence[float],
    *,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> list[float]:
    """Kiểm tra vector đúng số chiều, hữu hạn và khác vector 0."""
    if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)):
        raise EmbeddingError("Embedding phải là danh sách số thực.")
    if len(vector) != dimensions:
        raise EmbeddingError(f"Embedding phải có đúng {dimensions} chiều, nhận {len(vector)}.")
    result: list[float] = []
    norm_sq = 0.0
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EmbeddingError("Phần tử embedding phải là số thực.")
        num = float(value)
        if not math.isfinite(num):
            raise EmbeddingError("Phần tử embedding không được là NaN hoặc vô cực.")
        result.append(num)
        norm_sq += num * num
    if norm_sq <= 0.0:
        raise EmbeddingError("Vector embedding không được là vector 0.")
    return result


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Tính cosine similarity giữa hai vector cùng chiều trong khoảng [-1.0, 1.0]."""
    if len(left) != len(right) or not left:
        return 0.0
    dot = 0.0
    left_norm_sq = 0.0
    right_norm_sq = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm_sq += a * a
        right_norm_sq += b * b
    if left_norm_sq <= 0.0 or right_norm_sq <= 0.0:
        return 0.0
    similarity = dot / (math.sqrt(left_norm_sq) * math.sqrt(right_norm_sq))
    return max(-1.0, min(1.0, similarity))


class HttpEmbeddingClient:
    """Client gọi API tạo embedding (hỗ trợ OpenAI-compatible /embeddings)."""

    def __init__(self, settings: Settings) -> None:
        self._api_url = settings.embedding_api_url.strip()
        self._api_key = (settings.embedding_api_key or settings.llm_api_key).strip()
        self._model = settings.embedding_model.strip()
        self._dimensions = settings.embedding_dimensions
        self._timeout = settings.embedding_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._api_url and self._model)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.is_configured:
            raise EmbeddingError("Chưa cấu hình EMBEDDING_API_URL và EMBEDDING_MODEL.")
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: dict[str, object] = {
            "model": self._model,
            "input": list(texts),
        }
        if self._dimensions > 0:
            payload["dimensions"] = self._dimensions
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._api_url, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Không thể gọi API embedding: %s", exc)
            raise EmbeddingError("Không thể tạo embedding từ dịch vụ AI.") from None

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingError("Phản hồi embedding không khớp số lượng đoạn văn bản.")
        ordered = sorted(
            data,
            key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0,
        )
        vectors: list[list[float]] = []
        for item in ordered:
            if not isinstance(item, dict) or "embedding" not in item:
                raise EmbeddingError("Phản hồi embedding thiếu trường embedding.")
            vectors.append(validate_embedding(item["embedding"], dimensions=self._dimensions))
        return vectors
