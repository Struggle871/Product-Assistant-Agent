"""Track embedding profiles so incompatible vector spaces cannot be mixed."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_embedding_profiles"
down_revision: str | None = "0002_stage3_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("embedding_profile", sa.String(128), nullable=True))
    op.execute(
        "UPDATE document_chunks SET embedding_profile = 'hash:hash-baseline-v1:1536' "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding_profile")
