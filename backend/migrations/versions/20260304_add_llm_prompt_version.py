"""Add prompt_version to llm_runs

Revision ID: add_llm_prompt_version
Revises: add_llm_runs
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_llm_prompt_version"
down_revision = "add_llm_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("llm_runs", sa.Column("prompt_version", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("llm_runs", "prompt_version")
