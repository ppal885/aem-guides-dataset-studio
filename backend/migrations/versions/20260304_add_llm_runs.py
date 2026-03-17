"""Add LLM runs table for observability

Revision ID: add_llm_runs
Revises: add_jira_tables
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = "add_llm_runs"
down_revision = "add_jira_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(50), nullable=True),
        sa.Column("jira_id", sa.String(50), nullable=True),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_llm_runs_trace_id", "llm_runs", ["trace_id"])
    op.create_index("ix_llm_runs_jira_id", "llm_runs", ["jira_id"])
    op.create_index("ix_llm_runs_step_name", "llm_runs", ["step_name"])
    op.create_index("ix_llm_runs_created_at", "llm_runs", ["created_at"])


def downgrade():
    op.drop_index("ix_llm_runs_created_at", table_name="llm_runs")
    op.drop_index("ix_llm_runs_step_name", table_name="llm_runs")
    op.drop_index("ix_llm_runs_jira_id", table_name="llm_runs")
    op.drop_index("ix_llm_runs_trace_id", table_name="llm_runs")
    op.drop_table("llm_runs")
