"""Add dataset_runs table

Revision ID: add_dataset_runs
Revises: add_jira_attachment_text_search
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_dataset_runs"
down_revision = "add_jira_attachment_text_search"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dataset_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("jira_id", sa.String(50), nullable=False, index=True),
        sa.Column("scenario_type", sa.String(50), nullable=True, index=True),
        sa.Column("recipes_used", sa.Text(), nullable=True),
        sa.Column("bundle_zip", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("dataset_runs")
