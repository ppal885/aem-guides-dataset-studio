"""Add comments_json to jira_issues

Revision ID: add_jira_comments_json
Revises: add_run_feedback
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_jira_comments_json"
down_revision = "add_run_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jira_issues", sa.Column("comments_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("jira_issues", "comments_json")
