"""Create product catalog and ingestion tables.

Revision ID: 0001_stage2_catalog
Revises:
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_stage2_catalog"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_table(
        "product_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "product_id",
            sa.String(36),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False),
        sa.Column("hardware_revisions", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "model", name="uq_product_model"),
    )
    op.create_index("ix_product_models_product_id", "product_models", ["product_id"])
    op.create_index("ix_product_models_model", "product_models", ["model"])
    op.create_table(
        "product_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "product_model_id",
            sa.String(36),
            sa.ForeignKey("product_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(120), nullable=False),
        sa.Column("platform", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("product_model_id", "version", "platform", name="uq_product_version"),
    )
    op.create_index(
        "ix_product_versions_product_model_id", "product_versions", ["product_model_id"]
    )
    op.create_index("ix_product_versions_version", "product_versions", ["version"])
    op.create_table(
        "trusted_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand", sa.String(120), nullable=False),
        sa.Column("canonical_host", sa.String(255), nullable=False),
        sa.Column("allowed_subdomains", postgresql.JSONB(), nullable=False),
        sa.Column("allowed_path_prefixes", postgresql.JSONB(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("brand", "canonical_host", name="uq_trusted_source"),
    )
    op.create_index("ix_trusted_sources_brand", "trusted_sources", ["brand"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "product_id",
            sa.String(36),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_model_id",
            sa.String(36),
            sa.ForeignKey("product_models.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "product_version_id",
            sa.String(36),
            sa.ForeignKey("product_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("language", sa.String(30), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for column in (
        "product_id",
        "product_model_id",
        "product_version_id",
        "content_hash",
        "status",
    ):
        op.create_index(f"ix_documents_{column}", "documents", [column])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(40), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "content_hash", name="uq_document_content_hash"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_content_hash", "document_versions", ["content_hash"])
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("heading", sa.String(300)),
        sa.Column("page_number", sa.Integer()),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_document_chunks_document_version_id", "document_chunks", ["document_version_id"]
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_table(
        "index_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_index_versions_status", "index_versions", ["status"])


def downgrade() -> None:
    for table in (
        "index_versions",
        "ingestion_jobs",
        "document_chunks",
        "document_versions",
        "documents",
        "trusted_sources",
        "product_versions",
        "product_models",
        "products",
    ):
        op.drop_table(table)
