"""Initial migration

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create documents table
    op.create_table('documents',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('s3_key', sa.String(), nullable=False),
    sa.Column('original_filename', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('s3_key')
    )
    op.create_index(op.f('ix_documents_s3_key'), 'documents', ['s3_key'], unique=False)
    
    # Create pages table
    op.create_table('pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create artifacts table
    op.create_table('artifacts',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('engine', sa.String(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_artifacts_document_id'), 'artifacts', ['document_id'], unique=False)
    op.create_index(op.f('ix_artifacts_kind'), 'artifacts', ['kind'], unique=False)
    op.create_index(op.f('ix_artifacts_status'), 'artifacts', ['status'], unique=False)


def downgrade() -> None:
    # Drop artifacts table
    op.drop_index(op.f('ix_artifacts_status'), table_name='artifacts')
    op.drop_index(op.f('ix_artifacts_kind'), table_name='artifacts')
    op.drop_index(op.f('ix_artifacts_document_id'), table_name='artifacts')
    op.drop_table('artifacts')
    
    # Drop pages table
    op.drop_table('pages')
    
    # Drop documents table
    op.drop_index(op.f('ix_documents_s3_key'), table_name='documents')
    op.drop_table('documents')