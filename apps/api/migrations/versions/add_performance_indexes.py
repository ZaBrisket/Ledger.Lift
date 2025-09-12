"""Add performance indexes

Revision ID: add_performance_indexes
Revises: 9db8c0e41e1f
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_performance_indexes'
down_revision = '9db8c0e41e1f'
branch_labels = None
depends_on = None

def upgrade():
    """Add performance indexes for better query performance."""
    
    # Document table indexes
    op.create_index('idx_documents_status', 'documents', ['processing_status'])
    op.create_index('idx_documents_created_at', 'documents', ['created_at'])
    op.create_index('idx_documents_updated_at', 'documents', ['updated_at'])
    op.create_index('idx_documents_sha256_hash', 'documents', ['sha256_hash'])
    op.create_index('idx_documents_s3_key', 'documents', ['s3_key'])
    
    # Composite indexes for common queries
    op.create_index('idx_documents_status_created', 'documents', ['processing_status', 'created_at'])
    op.create_index('idx_documents_status_updated', 'documents', ['processing_status', 'updated_at'])
    
    # Page table indexes
    op.create_index('idx_pages_document_id', 'pages', ['document_id'])
    op.create_index('idx_pages_page_number', 'pages', ['page_number'])
    op.create_index('idx_pages_document_page', 'pages', ['document_id', 'page_number'])
    
    # Processing events indexes
    op.create_index('idx_processing_events_document_id', 'processing_events', ['document_id'])
    op.create_index('idx_processing_events_event_type', 'processing_events', ['event_type'])
    op.create_index('idx_processing_events_created_at', 'processing_events', ['created_at'])
    op.create_index('idx_processing_events_document_created', 'processing_events', ['document_id', 'created_at'])
    
    # Artifacts indexes
    op.create_index('idx_artifacts_document_id', 'artifacts', ['document_id'])
    op.create_index('idx_artifacts_artifact_type', 'artifacts', ['artifact_type'])
    op.create_index('idx_artifacts_page_id', 'artifacts', ['page_id'])
    op.create_index('idx_artifacts_created_at', 'artifacts', ['created_at'])
    op.create_index('idx_artifacts_document_type', 'artifacts', ['document_id', 'artifact_type'])
    op.create_index('idx_artifacts_confidence_score', 'artifacts', ['confidence_score'])

def downgrade():
    """Remove performance indexes."""
    
    # Drop composite indexes first
    op.drop_index('idx_documents_status_updated', 'documents')
    op.drop_index('idx_documents_status_created', 'documents')
    op.drop_index('idx_processing_events_document_created', 'processing_events')
    op.drop_index('idx_artifacts_document_type', 'artifacts')
    op.drop_index('idx_pages_document_page', 'pages')
    
    # Drop single column indexes
    op.drop_index('idx_artifacts_confidence_score', 'artifacts')
    op.drop_index('idx_artifacts_created_at', 'artifacts')
    op.drop_index('idx_artifacts_page_id', 'artifacts')
    op.drop_index('idx_artifacts_artifact_type', 'artifacts')
    op.drop_index('idx_artifacts_document_id', 'artifacts')
    op.drop_index('idx_processing_events_document_created', 'processing_events')
    op.drop_index('idx_processing_events_created_at', 'processing_events')
    op.drop_index('idx_processing_events_event_type', 'processing_events')
    op.drop_index('idx_processing_events_document_id', 'processing_events')
    op.drop_index('idx_pages_document_page', 'pages')
    op.drop_index('idx_pages_page_number', 'pages')
    op.drop_index('idx_pages_document_id', 'pages')
    op.drop_index('idx_documents_s3_key', 'documents')
    op.drop_index('idx_documents_sha256_hash', 'documents')
    op.drop_index('idx_documents_updated_at', 'documents')
    op.drop_index('idx_documents_created_at', 'documents')
    op.drop_index('idx_documents_status', 'documents')