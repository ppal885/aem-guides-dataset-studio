"""Add runner script + Jira metadata to chat_bulk_dataset_presets.

Revision ID: add_chat_bulk_preset_runner_meta
Revises: add_chat_bulk_dataset_presets
"""

from alembic import op
import sqlalchemy as sa

revision = "add_chat_bulk_preset_runner_meta"
down_revision = "add_chat_bulk_dataset_presets"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chat_bulk_dataset_presets",
        sa.Column("runner_script_relpath", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "chat_bulk_dataset_presets",
        sa.Column("jira_key", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "chat_bulk_dataset_presets",
        sa.Column("classification", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_chat_bulk_dataset_presets_jira_key",
        "chat_bulk_dataset_presets",
        ["jira_key"],
    )


def downgrade():
    op.drop_index("ix_chat_bulk_dataset_presets_jira_key", table_name="chat_bulk_dataset_presets")
    op.drop_column("chat_bulk_dataset_presets", "classification")
    op.drop_column("chat_bulk_dataset_presets", "jira_key")
    op.drop_column("chat_bulk_dataset_presets", "runner_script_relpath")
