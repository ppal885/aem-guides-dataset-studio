"""Add Jira indexing tables

Revision ID: add_jira_tables
Revises: add_job_indexes
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_jira_tables"
down_revision = "add_job_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jira_issues",
        sa.Column("issue_key", sa.String(50), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("issue_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("components_json", sa.Text(), nullable=True),
        sa.Column("labels_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("text_for_search", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "jira_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issue_key", sa.String(50), sa.ForeignKey("jira_issues.issue_key"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("jira_url", sa.Text(), nullable=True),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column("text_excerpt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_jira_attachments_issue_key", "jira_attachments", ["issue_key"])


def downgrade():
    op.drop_index("ix_jira_attachments_issue_key", table_name="jira_attachments")
    op.drop_table("jira_attachments")
    op.drop_table("jira_issues")
