"""T3 Enhancements: Audit, Costs, GDPR, Schedules

Revision ID: t3_001
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 't3_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgcrypto extension for gen_random_uuid()
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    
    # Create audit_events table with BRIN index for time-series optimization
    op.create_table(
        'audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('job_id', sa.String(255), nullable=False, index=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=True, index=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('trace_id', sa.String(255), nullable=True, index=True),
        sa.Column('idempotency_key', sa.String(64), nullable=False, unique=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    
    # BRIN index for time-series append-only workload
    op.execute('CREATE INDEX idx_audit_events_created_at_brin ON audit_events USING BRIN(created_at)')
    
    # Create cost_records table
    op.create_table(
        'cost_records',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.String(255), nullable=False, index=True),
        sa.Column('user_id', sa.String(255), nullable=False, index=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('pages', sa.Integer, nullable=False),
        sa.Column('cost_cents', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    
    # Create job_schedules table
    op.create_table(
        'job_schedules',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.String(255), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('row_count', sa.Integer, nullable=False),
        sa.Column('col_count', sa.Integer, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    
    # Add T3 columns to existing jobs table
    op.add_column('jobs', sa.Column('trace_id', sa.String(255), nullable=True))
    op.add_column('jobs', sa.Column('schema_version', sa.Integer, nullable=False, server_default='1'))
    op.add_column('jobs', sa.Column('cancellation_requested', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('selected_schedule_ids', postgresql.ARRAY(sa.Integer), nullable=True))
    op.add_column('jobs', sa.Column('deletion_manifest', postgresql.JSONB, nullable=True))


def downgrade() -> None:
    # Remove T3 columns from jobs
    op.drop_column('jobs', 'deletion_manifest')
    op.drop_column('jobs', 'selected_schedule_ids')
    op.drop_column('jobs', 'cancellation_requested')
    op.drop_column('jobs', 'schema_version')
    op.drop_column('jobs', 'trace_id')
    
    # Drop T3 tables
    op.drop_table('job_schedules')
    op.drop_table('cost_records')
    op.drop_table('audit_events')
    
    # Drop pgcrypto extension
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
