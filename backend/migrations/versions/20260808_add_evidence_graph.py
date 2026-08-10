"""Add production evidence knowledge graph tables.

Revision ID: add_evidence_graph
Revises: add_jira_csv_import
"""

from alembic import op
import sqlalchemy as sa


revision = "add_evidence_graph"
down_revision = "add_jira_csv_import"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_graph_generations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evidence_graph_generations_status", "evidence_graph_generations", ["status"])
    op.create_index("ix_evidence_graph_generations_promoted_at", "evidence_graph_generations", ["promoted_at"])

    op.create_table(
        "evidence_graph_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stable_key", sa.String(length=512), nullable=False),
        sa.Column("node_type", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=30), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("generation_id", "stable_key", name="uq_evidence_graph_node_key"),
    )
    op.create_index("ix_evidence_graph_nodes_generation_id", "evidence_graph_nodes", ["generation_id"])
    op.create_index("ix_evidence_graph_node_type_generation", "evidence_graph_nodes", ["generation_id", "node_type"])
    op.create_index("ix_evidence_graph_node_visibility", "evidence_graph_nodes", ["generation_id", "visibility", "tenant_id"])

    op.create_table(
        "evidence_graph_edges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_node_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(length=80), nullable=False),
        sa.Column("trust_tier", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "generation_id",
            "source_node_id",
            "relation",
            "target_node_id",
            name="uq_evidence_graph_edge_path",
        ),
    )
    op.create_index("ix_evidence_graph_edges_generation_id", "evidence_graph_edges", ["generation_id"])
    op.create_index("ix_evidence_graph_edge_out", "evidence_graph_edges", ["generation_id", "source_node_id", "relation"])
    op.create_index("ix_evidence_graph_edge_in", "evidence_graph_edges", ["generation_id", "target_node_id", "relation"])
    op.create_index("ix_evidence_graph_edge_trust", "evidence_graph_edges", ["generation_id", "trust_tier"])

    op.create_table(
        "evidence_graph_assertions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(length=36), sa.ForeignKey("evidence_graph_nodes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("edge_id", sa.String(length=36), sa.ForeignKey("evidence_graph_edges.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_ref", sa.String(length=1000), nullable=False),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("source_chunk_id", sa.String(length=512), nullable=True),
        sa.Column("source_hash", sa.String(length=80), nullable=False),
        sa.Column("extraction_method", sa.String(length=120), nullable=False),
        sa.Column("authority", sa.String(length=80), nullable=False),
        sa.Column("trust_tier", sa.String(length=40), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=30), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "(node_id IS NOT NULL AND edge_id IS NULL) OR (node_id IS NULL AND edge_id IS NOT NULL)",
            name="ck_evidence_graph_assertion_target",
        ),
        sa.UniqueConstraint(
            "generation_id",
            "node_id",
            "edge_id",
            "source_kind",
            "source_record_id",
            "source_hash",
            name="uq_evidence_graph_assertion_source",
        ),
    )
    op.create_index("ix_evidence_graph_assertions_generation_id", "evidence_graph_assertions", ["generation_id"])
    op.create_index("ix_evidence_graph_assertion_node", "evidence_graph_assertions", ["generation_id", "node_id"])
    op.create_index("ix_evidence_graph_assertion_edge", "evidence_graph_assertions", ["generation_id", "edge_id"])
    op.create_index("ix_evidence_graph_assertion_trust", "evidence_graph_assertions", ["generation_id", "trust_tier"])

    op.create_table(
        "evidence_graph_source_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("source_hash", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "source_kind",
            "source_record_id",
            "event_type",
            "source_hash",
            name="uq_evidence_graph_source_event",
        ),
    )
    op.create_index("ix_evidence_graph_event_queue", "evidence_graph_source_events", ["status", "next_attempt_at", "created_at"])

    op.create_table(
        "evidence_graph_source_state",
        sa.Column("source_name", sa.String(length=120), primary_key=True),
        sa.Column(
            "active_generation_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_generations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cursor", sa.JSON(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_evidence_graph_source_state_active_generation_id",
        "evidence_graph_source_state",
        ["active_generation_id"],
    )

    op.create_table(
        "evidence_graph_sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(length=36),
            sa.ForeignKey("evidence_graph_generations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("counters", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evidence_graph_sync_runs_generation_id", "evidence_graph_sync_runs", ["generation_id"])
    op.create_index("ix_evidence_graph_sync_run_status", "evidence_graph_sync_runs", ["status", "started_at"])


def downgrade():
    op.drop_index("ix_evidence_graph_sync_run_status", table_name="evidence_graph_sync_runs")
    op.drop_index("ix_evidence_graph_sync_runs_generation_id", table_name="evidence_graph_sync_runs")
    op.drop_table("evidence_graph_sync_runs")
    op.drop_index(
        "ix_evidence_graph_source_state_active_generation_id",
        table_name="evidence_graph_source_state",
    )
    op.drop_table("evidence_graph_source_state")
    op.drop_index("ix_evidence_graph_event_queue", table_name="evidence_graph_source_events")
    op.drop_table("evidence_graph_source_events")
    op.drop_index("ix_evidence_graph_assertion_trust", table_name="evidence_graph_assertions")
    op.drop_index("ix_evidence_graph_assertion_edge", table_name="evidence_graph_assertions")
    op.drop_index("ix_evidence_graph_assertion_node", table_name="evidence_graph_assertions")
    op.drop_index("ix_evidence_graph_assertions_generation_id", table_name="evidence_graph_assertions")
    op.drop_table("evidence_graph_assertions")
    op.drop_index("ix_evidence_graph_edge_trust", table_name="evidence_graph_edges")
    op.drop_index("ix_evidence_graph_edge_in", table_name="evidence_graph_edges")
    op.drop_index("ix_evidence_graph_edge_out", table_name="evidence_graph_edges")
    op.drop_index("ix_evidence_graph_edges_generation_id", table_name="evidence_graph_edges")
    op.drop_table("evidence_graph_edges")
    op.drop_index("ix_evidence_graph_node_visibility", table_name="evidence_graph_nodes")
    op.drop_index("ix_evidence_graph_node_type_generation", table_name="evidence_graph_nodes")
    op.drop_index("ix_evidence_graph_nodes_generation_id", table_name="evidence_graph_nodes")
    op.drop_table("evidence_graph_nodes")
    op.drop_index("ix_evidence_graph_generations_promoted_at", table_name="evidence_graph_generations")
    op.drop_index("ix_evidence_graph_generations_status", table_name="evidence_graph_generations")
    op.drop_table("evidence_graph_generations")
