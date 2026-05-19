"""Add dataset_artifact_index for ZIP reuse by fingerprint.

Revision ID: add_dataset_artifact_index
Revises: add_jira_comments_json
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = "add_dataset_artifact_index"
down_revision = "add_jira_comments_json"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dataset_artifact_index",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(120), nullable=False, index=True),
        sa.Column("artifact_key", sa.String(64), nullable=False),
        sa.Column("source_job_id", sa.String(36), nullable=False, index=True),
        sa.Column("created_by_user_id", sa.String(120), nullable=False),
        sa.Column("recipe_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_dataset_artifact_tenant_key",
        "dataset_artifact_index",
        ["tenant_id", "artifact_key"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_dataset_artifact_tenant_key", table_name="dataset_artifact_index")
    op.drop_table("dataset_artifact_index")
