from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TypedDict

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    DocumentVersion,
    IndexVersion,
    IngestionJob,
    JobStatus,
    Product,
    ProductModel,
    ProductVersion,
    TrustedSource,
)
from app.infrastructure.embeddings import embed_texts, embedding_profile
from app.infrastructure.object_store import ObjectStore
from app.rag.chunking import chunk_document
from app.rag.parsers import parse_document


class CatalogVersion(TypedDict):
    version: str
    platform: str | None


class CatalogItem(TypedDict):
    brand: str
    name: str
    category: str
    model: str
    model_aliases: list[str]
    versions: list[CatalogVersion]


class TrustedSourceItem(TypedDict):
    brand: str
    host: str
    subdomains: list[str]


DEMO_CATALOG: list[CatalogItem] = [
    {
        "brand": "TP-Link",
        "name": "Archer AX55",
        "category": "router",
        "model": "Archer AX55",
        "model_aliases": ["AX55"],
        "versions": [{"version": "1.0", "platform": "web"}],
    },
    {
        "brand": "HP",
        "name": "LaserJet M110w",
        "category": "printer",
        "model": "LaserJet M110w",
        "model_aliases": ["M110w"],
        "versions": [
            {"version": "1.0", "platform": "Windows"},
            {"version": "1.0", "platform": "macOS"},
        ],
    },
    {
        "brand": "TP-Link",
        "name": "Tapo C200",
        "category": "camera",
        "model": "Tapo C200",
        "model_aliases": ["C200"],
        "versions": [{"version": "1.0", "platform": "Tapo"}],
    },
]

TRUSTED_SOURCES: list[TrustedSourceItem] = [
    {
        "brand": "TP-Link",
        "host": "tp-link.com",
        "subdomains": ["www.tp-link.com", "static.tp-link.com"],
    },
    {
        "brand": "HP",
        "host": "hp.com",
        "subdomains": ["support.hp.com", "www.hp.com"],
    },
]


async def seed_catalog(session: AsyncSession) -> int:
    created = 0
    for item in DEMO_CATALOG:
        product = (
            await session.execute(
                select(Product).where(Product.brand == item["brand"], Product.name == item["name"])
            )
        ).scalar_one_or_none()
        if product is None:
            product = Product(
                brand=item["brand"],
                name=item["name"],
                category=item["category"],
                aliases=[],
            )
            session.add(product)
            await session.flush()
            created += 1

        model = (
            await session.execute(
                select(ProductModel).where(
                    ProductModel.product_id == product.id,
                    ProductModel.model == item["model"],
                )
            )
        ).scalar_one_or_none()
        if model is None:
            model = ProductModel(
                product_id=product.id,
                model=item["model"],
                aliases=item["model_aliases"],
                hardware_revisions=[],
            )
            session.add(model)
            await session.flush()

        for version in item["versions"]:
            existing_version = (
                await session.execute(
                    select(ProductVersion).where(
                        ProductVersion.product_model_id == model.id,
                        ProductVersion.version == version["version"],
                        ProductVersion.platform == version["platform"],
                    )
                )
            ).scalar_one_or_none()
            if existing_version is None:
                session.add(
                    ProductVersion(
                        product_model_id=model.id,
                        version=version["version"],
                        platform=version["platform"],
                    )
                )

    for item in TRUSTED_SOURCES:
        existing_source = (
            await session.execute(
                select(TrustedSource).where(
                    TrustedSource.brand == item["brand"],
                    TrustedSource.canonical_host == item["host"],
                )
            )
        ).scalar_one_or_none()
        if existing_source is None:
            session.add(
                TrustedSource(
                    brand=item["brand"],
                    canonical_host=item["host"],
                    allowed_subdomains=item["subdomains"],
                    allowed_path_prefixes=[],
                    source_type="official",
                    enabled=True,
                )
            )
            created += 1

    await session.commit()
    return created


async def create_document(
    session: AsyncSession,
    store: ObjectStore,
    *,
    content: bytes,
    filename: str,
    content_type: str,
    product_id: str,
    product_model_id: str | None,
    product_version_id: str | None,
    title: str | None,
    language: str,
    document_type: str,
) -> tuple[Document, IngestionJob, bool]:
    digest = hashlib.sha256(content).hexdigest()
    existing = (
        await session.execute(
            select(Document).where(
                Document.content_hash == digest,
                Document.product_id == product_id,
                Document.product_model_id == product_model_id,
                Document.product_version_id == product_version_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        job = (
            (
                await session.execute(
                    select(IngestionJob)
                    .where(IngestionJob.document_id == existing.id)
                    .order_by(IngestionJob.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if job is None:
            job = IngestionJob(document_id=existing.id, status=JobStatus.QUEUED)
            session.add(job)
            await session.commit()
            return existing, job, True
        return existing, job, False

    safe_name = PurePosixPath(filename).name.replace(" ", "_")
    object_key = f"documents/{product_id}/{digest[:12]}-{safe_name}"
    await store.put(object_key, content, content_type)
    document = Document(
        product_id=product_id,
        product_model_id=product_model_id,
        product_version_id=product_version_id,
        title=title or safe_name,
        source_type="uploaded",
        language=language,
        document_type=document_type,
        object_key=object_key,
        content_hash=digest,
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    try:
        await session.flush()
        job = IngestionJob(document_id=document.id, status=JobStatus.QUEUED)
        session.add(job)
        await session.commit()
    except Exception:
        await session.rollback()
        await store.delete(object_key)
        raise
    return document, job, True


async def process_document(
    session: AsyncSession,
    store: ObjectStore,
    document_id: str,
    job_id: str,
) -> None:
    document = await session.get(Document, document_id)
    job = await session.get(IngestionJob, job_id)
    if document is None or job is None:
        raise ValueError("Document or ingestion job not found")
    if document.status == DocumentStatus.ARCHIVED:
        raise ValueError("Archived documents cannot be ingested")

    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    document.status = DocumentStatus.PARSING
    await session.commit()
    try:
        content = await store.read(document.object_key)
        parsed = parse_document(content, document.object_key, _content_type(document.object_key))
        document.status = DocumentStatus.CHUNKING
        await session.flush()
        chunks = chunk_document(parsed)
        if not chunks:
            raise ValueError("No usable text was extracted from the document")

        document.status = DocumentStatus.INDEXING
        vectors = await embed_texts([chunk.text for chunk in chunks])
        profile = embedding_profile()

        version = DocumentVersion(
            document_id=document.id,
            content_hash=document.content_hash,
            page_count=parsed.page_count,
            chunk_count=len(chunks),
        )
        session.add(version)
        await session.flush()
        for chunk, vector in zip(chunks, vectors, strict=True):
            session.add(
                DocumentChunk(
                    document_version_id=version.id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    heading=chunk.heading,
                    page_number=chunk.page_number,
                    metadata_json={
                        "product_id": document.product_id,
                        "product_model_id": document.product_model_id,
                        "product_version_id": document.product_version_id,
                        "language": document.language,
                        "document_type": document.document_type,
                    },
                    embedding=vector,
                    embedding_profile=profile,
                )
            )
        document.status = DocumentStatus.READY
        document.error_message = None
        job.status = JobStatus.SUCCEEDED
        job.error_message = None
        job.completed_at = datetime.now(UTC)
        await publish_index_version(session)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed_document = await session.get(Document, document_id)
        failed_job = await session.get(IngestionJob, job_id)
        if failed_document is None or failed_job is None:
            raise
        failed_document.status = DocumentStatus.FAILED
        failed_document.error_message = str(exc)[:2000]
        failed_job.status = JobStatus.FAILED
        failed_job.error_message = str(exc)[:2000]
        failed_job.completed_at = datetime.now(UTC)
        await session.commit()
        raise


async def archive_document(session: AsyncSession, document: Document) -> None:
    if document.status == DocumentStatus.ARCHIVED:
        return
    document.status = DocumentStatus.ARCHIVED
    document.error_message = None
    await publish_index_version(session)
    await session.commit()


async def publish_index_version(session: AsyncSession) -> IndexVersion:
    await session.flush()
    document_count = (
        await session.scalar(
            select(func.count(Document.id)).where(Document.status == DocumentStatus.READY)
        )
        or 0
    )
    chunk_count = (
        await session.scalar(
            select(func.count(DocumentChunk.id))
            .join(DocumentVersion)
            .join(Document)
            .where(Document.status == DocumentStatus.READY)
        )
        or 0
    )
    await session.execute(
        update(IndexVersion).where(IndexVersion.status == "PUBLISHED").values(status="ARCHIVED")
    )
    now = datetime.now(UTC)
    version = IndexVersion(
        version=f"stage2-{now.strftime('%Y%m%d%H%M%S%f')}",
        status="PUBLISHED",
        document_count=document_count,
        chunk_count=chunk_count,
        published_at=now,
    )
    session.add(version)
    return version


def _content_type(filename: str) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "html": "text/html",
        "htm": "text/html",
        "md": "text/markdown",
        "markdown": "text/markdown",
        "txt": "text/plain",
    }.get(suffix, "")
