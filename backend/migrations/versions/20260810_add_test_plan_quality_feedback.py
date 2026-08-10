"""Add append-only test-plan quality feedback.

Revision ID: test_plan_feedback_v1
Revises: evidence_graph_phase_b
"""

from alembic import op
import sqlalchemy as sa


revision = "test_plan_feedback_v1"
down_revision = "evidence_graph_phase_b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_plan_quality_feedback",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("jira_key", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=160), nullable=True),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(length=180), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_hash", sa.String(length=64), nullable=False),
        sa.Column("ac_id", sa.String(length=120), nullable=True),
        sa.Column("ac_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=True),
        sa.Column("before_hash", sa.String(length=64), nullable=True),
        sa.Column("after_hash", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("redaction_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_test_plan_quality_feedback_idempotency",
        ),
    )
    op.create_index(
        "ix_test_plan_feedback_jira_created",
        "test_plan_quality_feedback",
        ["jira_key", "created_at"],
    )
    op.create_index(
        "ix_test_plan_feedback_plan_created",
        "test_plan_quality_feedback",
        ["plan_fingerprint", "created_at"],
    )
    op.create_index(
        "ix_test_plan_feedback_event_created",
        "test_plan_quality_feedback",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_test_plan_feedback_tenant_jira",
        "test_plan_quality_feedback",
        ["tenant_id", "jira_key"],
    )


def downgrade():
    op.drop_index("ix_test_plan_feedback_tenant_jira", table_name="test_plan_quality_feedback")
    op.drop_index("ix_test_plan_feedback_event_created", table_name="test_plan_quality_feedback")
    op.drop_index("ix_test_plan_feedback_plan_created", table_name="test_plan_quality_feedback")
    op.drop_index("ix_test_plan_feedback_jira_created", table_name="test_plan_quality_feedback")
    op.drop_table("test_plan_quality_feedback")
