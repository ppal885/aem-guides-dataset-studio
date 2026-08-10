"""Add Phase B evidence graph query telemetry.

Revision ID: evidence_graph_phase_b
Revises: add_evidence_graph
"""

from alembic import op
import sqlalchemy as sa


revision = "evidence_graph_phase_b"
down_revision = "add_evidence_graph"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_graph_query_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_generations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("actor_hash", sa.String(length=64), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("selector_hash", sa.String(length=64), nullable=False),
        sa.Column("influence_mode", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("path_count", sa.Integer(), nullable=False),
        sa.Column("leaf_count", sa.Integer(), nullable=False),
        sa.Column("cross_customer_detail_count", sa.Integer(), nullable=False),
        sa.Column("cross_customer_aggregate_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_evidence_graph_query_audits_generation_id",
        "evidence_graph_query_audits",
        ["generation_id"],
    )
    op.create_index(
        "ix_evidence_graph_query_audit_created",
        "evidence_graph_query_audits",
        ["created_at"],
    )
    op.create_index(
        "ix_evidence_graph_query_audit_tenant",
        "evidence_graph_query_audits",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_evidence_graph_query_audit_status",
        "evidence_graph_query_audits",
        ["status", "created_at"],
    )


def downgrade():
    op.drop_index("ix_evidence_graph_query_audit_status", table_name="evidence_graph_query_audits")
    op.drop_index("ix_evidence_graph_query_audit_tenant", table_name="evidence_graph_query_audits")
    op.drop_index("ix_evidence_graph_query_audit_created", table_name="evidence_graph_query_audits")
    op.drop_index("ix_evidence_graph_query_audits_generation_id", table_name="evidence_graph_query_audits")
    op.drop_table("evidence_graph_query_audits")
