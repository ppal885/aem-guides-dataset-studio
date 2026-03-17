"""Add progress tracking fields to jobs table

Revision ID: add_progress_tracking
Revises: add_jobs_table
Create Date: 2026-01-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_progress_tracking'
down_revision = 'add_jobs_table'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('progress_percent', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('files_generated', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('total_files_estimated', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('current_stage', sa.String(), nullable=True))


def downgrade():
    op.drop_column('jobs', 'current_stage')
    op.drop_column('jobs', 'total_files_estimated')
    op.drop_column('jobs', 'files_generated')
    op.drop_column('jobs', 'progress_percent')
