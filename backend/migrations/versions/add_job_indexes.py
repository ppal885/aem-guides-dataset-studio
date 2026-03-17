"""Add composite indexes to jobs table for performance

Revision ID: add_job_indexes
Revises: add_progress_tracking
Create Date: 2026-01-28 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_job_indexes'
down_revision = 'add_progress_tracking'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_jobs_user_status', 'jobs', ['user_id', 'status'])
    op.create_index('ix_jobs_user_created', 'jobs', ['user_id', 'created_at'])


def downgrade():
    op.drop_index('ix_jobs_user_created', table_name='jobs')
    op.drop_index('ix_jobs_user_status', table_name='jobs')
