"""Add text_search_blob to jira_attachments

Revision ID: add_jira_attachment_text_search
Revises: add_llm_prompt_version
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_jira_attachment_text_search"
down_revision = "add_llm_prompt_version"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jira_attachments", sa.Column("text_search_blob", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("jira_attachments", "text_search_blob")
