"""Batch embedding adapters shared by ingestion and retrieval."""

from __future__ import annotations

import hashlib
import math

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings


class EmbeddingError(RuntimeError):
    """A sanitized error safe to expose in ingestion status and retrieval traces."""


class EmbeddingItem(BaseModel):
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    data: list[EmbeddingItem]


def embedding_profile(settings: Settings | None = None) -> str:
    active = settings or get_settings()
    if active.embedding_provider == "hash":
        return f"hash:hash-baseline-v1:{active.embedding_dimensions}"
    # The endpoint matters: identical model names can refer to different weights.
    endpoint = hashlib.sha256(active.embedding_base_url.rstrip("/").encode()).hexdigest()[:16]
    model = hashlib.sha256(active.embedding_model.encode()).hexdigest()[:16]
    return f"openai:{endpoint}:{model}:{active.embedding_dimensions}"


def hash_embedding(text_value: str, dimensions: int = 1536) -> list[float]:
    """Offline plumbing baseline; this is not a semantic language model."""
    values = [0.0] * dimensions
    encoded = text_value.lower().encode("utf-8")
    for index in range(0, len(encoded), 4):
        digest = hashlib.blake2b(encoded[index : index + 4], digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        values[slot] += (int.from_bytes(digest[4:], "big") / 2**64) * 2 - 1
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


async def embed_texts(
    texts: list[str],
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[list[float]]:
    active = settings or get_settings()
    if not texts:
        return []
    if any(not value.strip() for value in texts):
        raise EmbeddingError("Embedding input must not be empty")
    if active.embedding_provider == "hash":
        return [hash_embedding(value, active.embedding_dimensions) for value in texts]
    if active.embedding_base_url.rstrip("/") in {
        "https://api.openai.com/v1",
        "https://api.siliconflow.cn/v1",
    }:
        if not active.embedding_api_key:
            raise EmbeddingError("EMBEDDING_API_KEY is required for the configured service")
    headers = {"Authorization": f"Bearer {active.embedding_api_key}"}
    async with httpx.AsyncClient(
        timeout=active.embedding_timeout_seconds,
        transport=transport,
        follow_redirects=False,
    ) as client:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), active.embedding_batch_size):
            batch = texts[start : start + active.embedding_batch_size]
            payload: dict[str, object] = {
                "model": active.embedding_model,
                "input": batch,
                "encoding_format": "float",
            }
            if active.embedding_send_dimensions:
                payload["dimensions"] = active.embedding_dimensions
            try:
                response = await client.post(
                    f"{active.embedding_base_url.rstrip('/')}/embeddings",
                    headers=headers if active.embedding_api_key else {},
                    json=payload,
                )
                response.raise_for_status()
                parsed = EmbeddingResponse.model_validate(response.json())
            except httpx.HTTPStatusError as exc:
                raise EmbeddingError(
                    f"Embedding service returned HTTP {exc.response.status_code}"
                ) from None
            except httpx.RequestError:
                raise EmbeddingError("Embedding service is unavailable or timed out") from None
            except (ValueError, ValidationError):
                raise EmbeddingError("Embedding service returned an invalid response") from None
            items = sorted(parsed.data, key=lambda item: item.index)
            if [item.index for item in items] != list(range(len(batch))):
                raise EmbeddingError("Embedding response indexes do not match the input batch")
            for item in items:
                if len(item.embedding) != active.embedding_dimensions:
                    raise EmbeddingError("Embedding dimensions do not match configured dimensions")
                if not all(math.isfinite(value) for value in item.embedding):
                    raise EmbeddingError("Embedding response contains non-finite values")
                if not any(item.embedding):
                    raise EmbeddingError("Embedding response contains a zero vector")
                vectors.append(item.embedding)
        return vectors
