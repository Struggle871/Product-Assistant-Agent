from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import get_session
from app.domain.models import (
    Document,
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
from app.infrastructure.object_store import ObjectStore
from app.rag.service import archive_document, create_document, seed_catalog
from app.worker import enqueue_ingestion

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminKeyDep = Annotated[str | None, Header(alias="X-Admin-API-Key")]


async def require_admin(api_key: str | None = None) -> None:
    if api_key != get_settings().admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )


class ProductVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: str
    platform: str | None


class ProductModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    model: str
    aliases: list[str]
    hardware_revisions: list[str]
    versions: list[ProductVersionResponse]


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    brand: str
    name: str
    category: str
    aliases: list[str]
    models: list[ProductModelResponse]


class TrustedSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    brand: str
    canonical_host: str
    allowed_subdomains: list[str]
    allowed_path_prefixes: list[str]
    source_type: str
    enabled: bool


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    product_model_id: str | None
    product_version_id: str | None
    title: str
    source_type: str
    source_url: str | None
    language: str
    document_type: str
    content_hash: str
    status: str
    error_message: str | None


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    content_hash: str
    pipeline_version: str
    page_count: int
    chunk_count: int


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    status: str
    attempts: int
    max_attempts: int
    error_message: str | None


class DocumentDetailResponse(DocumentResponse):
    latest_job: IngestionJobResponse | None = None
    latest_version: DocumentVersionResponse | None = None


class IndexVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: str
    status: str
    document_count: int
    chunk_count: int
    published_at: datetime | None


class CatalogSeedResponse(BaseModel):
    created: int
    products: int
    trusted_sources: int


@router.get("/products", response_model=list[ProductResponse])
async def list_products(
    session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> Sequence[Product]:
    await require_admin(x_admin_api_key)
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.models).selectinload(ProductModel.versions))
        .order_by(Product.brand, Product.name)
    )
    return result.scalars().all()


@router.post("/catalog/seed", response_model=CatalogSeedResponse)
async def seed_demo_catalog(
    session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> CatalogSeedResponse:
    await require_admin(x_admin_api_key)
    created = await seed_catalog(session)
    product_rows = (await session.execute(select(Product))).scalars().all()
    source_rows = (await session.execute(select(TrustedSource))).scalars().all()
    return CatalogSeedResponse(
        created=created,
        products=len(product_rows),
        trusted_sources=len(source_rows),
    )


@router.get("/trusted-sources", response_model=list[TrustedSourceResponse])
async def list_trusted_sources(
    session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> Sequence[TrustedSource]:
    await require_admin(x_admin_api_key)
    result = await session.execute(select(TrustedSource).order_by(TrustedSource.brand))
    return result.scalars().all()


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> Sequence[Document]:
    await require_admin(x_admin_api_key)
    result = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return result.scalars().all()


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str, session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> DocumentDetailResponse:
    await require_admin(x_admin_api_key)
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    job = (
        (
            await session.execute(
                select(IngestionJob)
                .where(IngestionJob.document_id == document_id)
                .order_by(IngestionJob.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    version = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    return DocumentDetailResponse(
        **DocumentResponse.model_validate(document).model_dump(),
        latest_job=IngestionJobResponse.model_validate(job) if job else None,
        latest_version=DocumentVersionResponse.model_validate(version) if version else None,
    )


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    session: SessionDep,
    x_admin_api_key: AdminKeyDep = None,
    file: UploadFile = File(...),  # noqa: B008
    product_id: str = Form(...),
    product_model_id: str | None = Form(default=None),
    product_version_id: str | None = Form(default=None),
    title: str | None = Form(default=None),
    language: str = Form(default="zh-CN"),
    document_type: str = Form(default="manual"),
) -> DocumentResponse:
    await require_admin(x_admin_api_key)
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    model = None
    if product_model_id is not None:
        model = await session.get(ProductModel, product_model_id)
        if model is None or model.product_id != product_id:
            raise HTTPException(status_code=404, detail="Product model not found")
    if product_version_id is not None:
        version = await session.get(ProductVersion, product_version_id)
        if version is None or model is None or version.product_model_id != model.id:
            raise HTTPException(status_code=404, detail="Product version not found")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Document is empty")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document exceeds 50 MiB limit")
    document, job, is_new = await create_document(
        session,
        ObjectStore(),
        content=content,
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        product_id=product_id,
        product_model_id=product_model_id,
        product_version_id=product_version_id,
        title=title,
        language=language,
        document_type=document_type,
    )
    if is_new:
        enqueue_ingestion(document.id, job.id)
    return DocumentResponse.model_validate(document)


@router.post("/documents/{document_id}/archive", response_model=DocumentResponse)
async def archive_document_endpoint(
    document_id: str, session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> Document:
    await require_admin(x_admin_api_key)
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status in {
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSING,
        DocumentStatus.CHUNKING,
        DocumentStatus.INDEXING,
    }:
        raise HTTPException(status_code=409, detail="Active ingestion cannot be archived")
    await archive_document(session, document)
    return document


@router.get("/ingestion-jobs", response_model=list[IngestionJobResponse])
async def list_ingestion_jobs(
    session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> Sequence[IngestionJob]:
    await require_admin(x_admin_api_key)
    result = await session.execute(
        select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(100)
    )
    return result.scalars().all()


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
async def get_ingestion_job(
    job_id: str, session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> IngestionJob:
    await require_admin(x_admin_api_key)
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.post(
    "/ingestion-jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_ingestion_job(
    job_id: str, session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> IngestionJob:
    await require_admin(x_admin_api_key)
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    if job.status not in {JobStatus.FAILED, JobStatus.QUEUED}:
        raise HTTPException(status_code=409, detail="Only failed or queued jobs can be retried")
    job.status = JobStatus.QUEUED
    job.error_message = None
    document = await session.get(Document, job.document_id)
    if document is not None:
        document.status = DocumentStatus.UPLOADED
        document.error_message = None
    await session.commit()
    enqueue_ingestion(job.document_id, job.id)
    return job


@router.get("/index-versions", response_model=list[IndexVersionResponse])
async def list_index_versions(
    session: SessionDep, x_admin_api_key: AdminKeyDep = None
) -> Sequence[IndexVersion]:
    await require_admin(x_admin_api_key)
    result = await session.execute(
        select(IndexVersion).order_by(IndexVersion.created_at.desc()).limit(50)
    )
    return result.scalars().all()
