"""Support BGE-M3 1024 dimensions while preserving existing 1536 vectors."""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_variable_vector_dimensions"
down_revision: str | None = "0003_embedding_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector")
    for dimensions in (1024, 1536):
        op.execute(
            f"CREATE INDEX ix_document_chunks_embedding_hnsw_{dimensions} "
            f"ON document_chunks USING hnsw ((embedding::vector({dimensions})) vector_cosine_ops) "
            f"WHERE vector_dims(embedding) = {dimensions}"
        )


def downgrade() -> None:
    # Refuse loss of BGE vectors instead of silently truncating/clearing them.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM document_chunks "
        "WHERE vector_dims(embedding) <> 1536) THEN "
        "RAISE EXCEPTION 'Cannot downgrade while non-1536 vectors exist'; END IF; END $$"
    )
    for dimensions in (1024, 1536):
        op.execute(f"DROP INDEX ix_document_chunks_embedding_hnsw_{dimensions}")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )
