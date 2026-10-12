from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brand: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    models: Mapped[list[ProductModel]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductModel(Base):
    __tablename__ = "product_models"
    __table_args__ = (UniqueConstraint("product_id", "model", name="uq_product_model"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(160), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    hardware_revisions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(back_populates="models")
    versions: Mapped[list[ProductVersion]] = relationship(
        back_populates="product_model", cascade="all, delete-orphan"
    )


class ProductVersion(Base):
    __tablename__ = "product_versions"
    __table_args__ = (
        UniqueConstraint(
            "product_model_id",
            "version",
            "platform",
            name="uq_product_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_model_id: Mapped[str] = mapped_column(
        ForeignKey("product_models.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(120), index=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product_model: Mapped[ProductModel] = relationship(back_populates="versions")


class TrustedSource(Base):
    __tablename__ = "trusted_sources"
    __table_args__ = (UniqueConstraint("brand", "canonical_host", name="uq_trusted_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brand: Mapped[str] = mapped_column(String(120), index=True)
    canonical_host: Mapped[str] = mapped_column(String(255))
    allowed_subdomains: Mapped[list[str]] = mapped_column(JSONB, default=list)
    allowed_path_prefixes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_type: Mapped[str] = mapped_column(String(50), default="official")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    product_model_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(50), default="uploaded")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(30), default="zh-CN")
    document_type: Mapped[str] = mapped_column(String(30), default="manual")
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default=DocumentStatus.UPLOADED, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[list[IngestionJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "content_hash", name="uq_document_content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    pipeline_version: Mapped[str] = mapped_column(String(40), default="stage2-v1")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="versions")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default=JobStatus.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="ingestion_jobs")


class IndexVersion(Base):
    __tablename__ = "index_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="BUILDING", index=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
