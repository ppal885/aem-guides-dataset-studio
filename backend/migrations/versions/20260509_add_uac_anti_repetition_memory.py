"""Add uac_anti_repetition_memory for UAC response de-duplication across Jira tickets.

Revision ID: add_uac_anti_repetition_memory
Revises: add_chat_bulk_preset_runner_meta
"""

from alembic import op
import sqlalchemy as sa

revision = "add_uac_anti_repetition_memory"
down_revision = "add_chat_bulk_preset_runner_meta"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "uac_anti_repetition_memory",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("jira_key", sa.String(length=48), nullable=False),
        sa.Column("scenario_titles", sa.JSON(), nullable=False),
        sa.Column("risk_drivers", sa.JSON(), nullable=False),
        sa.Column("clarification_questions", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_uac_anti_rep_created_at", "uac_anti_repetition_memory", ["created_at"])
    op.create_index("ix_uac_anti_rep_domain", "uac_anti_repetition_memory", ["domain"])
    op.create_index("ix_uac_anti_rep_jira_key", "uac_anti_repetition_memory", ["jira_key"])


def downgrade():
    op.drop_index("ix_uac_anti_rep_jira_key", table_name="uac_anti_repetition_memory")
    op.drop_index("ix_uac_anti_rep_domain", table_name="uac_anti_repetition_memory")
    op.drop_index("ix_uac_anti_rep_created_at", table_name="uac_anti_repetition_memory")
    op.drop_table("uac_anti_repetition_memory")
