"""Check the configured embedding service without printing keys or vectors."""

import asyncio
import json

from app.config import get_settings
from app.infrastructure.embeddings import EmbeddingError, embed_texts


async def main() -> None:
    settings = get_settings()
    try:
        vectors = await embed_texts(["路由器首次连接", "打印机卡纸处理"])
    except EmbeddingError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "status": "ok",
                "model": settings.embedding_model,
                "vector_count": len(vectors),
                "dimensions": [len(vector) for vector in vectors],
                "semantic_provider": settings.embedding_provider != "hash",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
