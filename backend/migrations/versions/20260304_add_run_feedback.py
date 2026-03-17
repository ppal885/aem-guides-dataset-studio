"""Add run_feedback table

Revision ID: add_run_feedback
Revises: add_dita_spec_chunks
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_run_feedback"
down_revision = "add_dita_spec_chunks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "run_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=True, index=True),
        sa.Column("jira_id", sa.String(50), nullable=True, index=True),
        sa.Column("validation_errors", sa.Text(), nullable=True),
        sa.Column("eval_metrics", sa.Text(), nullable=True),
        sa.Column("suggested_updates", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("run_feedback")
