"""Exercise real database scope/isolation with synthetic rows rolled back on exit."""

import asyncio
import hashlib
import json
from uuid import uuid4

from app.db import engine, session_factory
from app.domain.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    DocumentVersion,
    Product,
    ProductModel,
    ProductVersion,
)
from app.infrastructure.embeddings import embed_texts, embedding_profile
from app.rag.retrieval import Answerability, RetrievalFilters, hybrid_search, vector_search


async def main() -> None:
    texts = ["复位操作需按住按钮5秒。", "复位操作需按住按钮10秒。", "复位操作需按住按钮20秒。"]
    vectors = await embed_texts(texts)
    checks: list[str] = []
    async with session_factory() as session:
        try:
            products = [
                Product(id=str(uuid4()), brand="Synthetic", name=f"scope-{i}", category="eval")
                for i in range(2)
            ]
            session.add_all(products)
            await session.flush()
            models = [
                ProductModel(id=str(uuid4()), product_id=p.id, model="synthetic") for p in products
            ]
            session.add_all(models)
            await session.flush()
            versions = [
                ProductVersion(id=str(uuid4()), product_model_id=models[0].id, version=str(i))
                for i in range(2)
            ]
            session.add_all(versions)
            await session.flush()
            chunks: list[DocumentChunk] = []
            for i, text in enumerate(texts):
                product = products[0 if i < 2 else 1]
                model = models[0 if i < 2 else 1]
                document = Document(
                    id=str(uuid4()),
                    product_id=product.id,
                    product_model_id=model.id,
                    product_version_id=versions[i].id if i < 2 else None,
                    title=f"synthetic-scope-{i}",
                    source_type="uploaded",
                    language="zh-CN",
                    document_type="manual",
                    object_key=str(uuid4()),
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    status=DocumentStatus.READY,
                )
                session.add(document)
                await session.flush()
                revision = DocumentVersion(
                    id=str(uuid4()),
                    document_id=document.id,
                    content_hash=document.content_hash,
                    chunk_count=1,
                )
                session.add(revision)
                await session.flush()
                chunk = DocumentChunk(
                    id=str(uuid4()),
                    document_version_id=revision.id,
                    chunk_index=0,
                    text=text,
                    heading="复位",
                    embedding=vectors[i],
                    embedding_profile=embedding_profile(),
                )
                session.add(chunk)
                chunks.append(chunk)
            await session.flush()
            selected = RetrievalFilters(
                product_id=products[0].id,
                product_model_id=models[0].id,
                product_version_id=versions[0].id,
                language="zh-CN",
            )
            result = await hybrid_search(session, "复位操作", selected)
            assert not result.trace.warnings
            assert {item.chunk_id for item in result.evidence} == {chunks[0].id}
            checks.append("product_model_version_scope")
            mixed = await hybrid_search(
                session, "复位操作", RetrievalFilters(product_id=products[0].id)
            )
            assert {item.chunk_id for item in mixed.evidence} == {chunks[0].id, chunks[1].id}
            assert mixed.answerability == Answerability.CONFLICTED
            checks.append("mixed_version_conflict")
            foreign_language = await hybrid_search(
                session, "复位操作", RetrievalFilters(product_id=products[0].id, language="en-US")
            )
            assert not foreign_language.evidence
            checks.append("language_scope")
            chunks[0].embedding_profile = "other-space"
            await session.flush()
            assert not await vector_search(session, "复位操作", selected, 10)
            checks.append("embedding_space_isolation")
            document = await session.get(Document, result.evidence[0].document_id)
            assert document is not None
            document.status = DocumentStatus.ARCHIVED
            await session.flush()
            archived = await hybrid_search(session, "复位操作", selected)
            assert not archived.evidence
            checks.append("archived_source_exclusion")
        finally:
            await session.rollback()
    await engine.dispose()
    print(json.dumps({"checks": checks, "passed": len(checks), "fixture_rows": "rolled_back"}))


if __name__ == "__main__":
    asyncio.run(main())
