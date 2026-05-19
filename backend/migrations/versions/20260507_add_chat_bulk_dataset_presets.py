"""Add chat_bulk_dataset_presets for chat-saved bulk job configs.

Revision ID: add_chat_bulk_dataset_presets
Revises: add_dataset_artifact_index
"""

from alembic import op
import sqlalchemy as sa

revision = "add_chat_bulk_dataset_presets"
down_revision = "add_dataset_artifact_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_bulk_dataset_presets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(120), nullable=False),
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("source_job_id", sa.String(36), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_chat_bulk_dataset_presets_user_id",
        "chat_bulk_dataset_presets",
        ["user_id"],
    )
    op.create_index(
        "ix_chat_bulk_dataset_presets_tenant_id",
        "chat_bulk_dataset_presets",
        ["tenant_id"],
    )
    op.create_index(
        "ix_chat_bulk_dataset_presets_source_job_id",
        "chat_bulk_dataset_presets",
        ["source_job_id"],
    )
    op.create_unique_constraint(
        "uq_chat_bulk_preset_user_tenant_label",
        "chat_bulk_dataset_presets",
        ["user_id", "tenant_id", "label"],
    )


def downgrade():
    op.drop_constraint("uq_chat_bulk_preset_user_tenant_label", "chat_bulk_dataset_presets", type_="unique")
    op.drop_index("ix_chat_bulk_dataset_presets_source_job_id", table_name="chat_bulk_dataset_presets")
    op.drop_index("ix_chat_bulk_dataset_presets_tenant_id", table_name="chat_bulk_dataset_presets")
    op.drop_index("ix_chat_bulk_dataset_presets_user_id", table_name="chat_bulk_dataset_presets")
    op.drop_table("chat_bulk_dataset_presets")
