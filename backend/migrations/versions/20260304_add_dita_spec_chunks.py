"""Add dita_spec_chunks table

Revision ID: add_dita_spec_chunks
Revises: add_dataset_runs
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_dita_spec_chunks"
down_revision = "add_dataset_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dita_spec_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("element_name", sa.String(100), nullable=True, index=True),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column("parent_element", sa.String(100), nullable=True),
        sa.Column("children_elements", sa.Text(), nullable=True),
        sa.Column("attributes", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("dita_spec_chunks")
