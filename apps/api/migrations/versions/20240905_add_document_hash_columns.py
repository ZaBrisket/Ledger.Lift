"""Add document hash columns"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240905_add_document_hash_columns"
down_revision = "add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("sha256_raw", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("sha256_canonical", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_documents_sha256_raw", ["sha256_raw"], unique=False)
        batch_op.create_index("ix_documents_sha256_canonical", ["sha256_canonical"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_sha256_canonical")
        batch_op.drop_index("ix_documents_sha256_raw")
        batch_op.drop_column("sha256_canonical")
        batch_op.drop_column("sha256_raw")
