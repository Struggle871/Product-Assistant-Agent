"""Atomically replace each ready document's embeddings after changing providers."""

import asyncio

from sqlalchemy import select

from app.db import engine, session_factory
from app.domain.models import Document, DocumentChunk, DocumentStatus, DocumentVersion
from app.infrastructure.embeddings import embed_texts, embedding_profile


async def main() -> None:
    profile = embedding_profile()
    async with session_factory() as session:
        document_ids = list(
            (
                await session.scalars(
                    select(Document.id).where(Document.status == DocumentStatus.READY)
                )
            ).all()
        )
    for document_id in document_ids:
        # Each document commits only after all its vectors pass validation. A
        # failed request leaves its old profile intact and excluded from search.
        async with session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            if document is None or document.status != DocumentStatus.READY:
                continue
            chunks = list(
                (
                    await session.scalars(
                        select(DocumentChunk)
                        .join(DocumentVersion)
                        .where(DocumentVersion.document_id == document_id)
                        .order_by(DocumentChunk.chunk_index)
                    )
                ).all()
            )
            if all(chunk.embedding_profile == profile for chunk in chunks):
                continue
            vectors = await embed_texts([chunk.text for chunk in chunks])
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_profile = profile
        print(f"Re-embedded document {document_id}: {len(chunks)} chunks")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
