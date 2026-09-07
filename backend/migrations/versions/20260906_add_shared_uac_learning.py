"""Shared Human UAC corrections, immutable lesson revisions and indexing outbox."""
from alembic import op
import sqlalchemy as sa

revision = "shared_uac_learning_v1"
down_revision = "test_plan_feedback_v1"
branch_labels = None
depends_on = None

IMMUTABLE_TABLES = ("uac_learning_drafts", "uac_feedback_deltas", "uac_feedback_bindings", "uac_lesson_revisions")


def _identity_columns():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(120), nullable=False),
            sa.Column("actor_id", sa.String(160), nullable=False),
            sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table("uac_learning_drafts", *_identity_columns(),
        sa.Column("jira_key", sa.String(64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence_bundle_id", sa.String(180), nullable=False),
        sa.Column("run_id", sa.String(160), nullable=False), sa.Column("content", sa.JSON(), nullable=False))
    op.create_table("uac_feedback_deltas", *_identity_columns(),
        sa.Column("jira_key", sa.String(64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("raw_feedback", sa.Text(), nullable=False),
        sa.Column("proposed_correction", sa.Text(), nullable=False),
        sa.Column("delta_type", sa.String(80), nullable=False), sa.Column("content", sa.JSON(), nullable=False))
    op.create_table("uac_feedback_bindings", *_identity_columns(),
        sa.Column("delta_id", sa.String(36), sa.ForeignKey("uac_feedback_deltas.id"), nullable=False, unique=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("uac_learning_drafts.id"), nullable=False))
    op.create_table("uac_lesson_revisions", *_identity_columns(),
        sa.Column("lesson_id", sa.String(36), sa.ForeignKey("uac_feedback_deltas.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("state", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("lesson_id", "version", name="uq_uac_lesson_version"))
    op.create_table("uac_learning_outbox", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(120), nullable=False),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("uac_lesson_revisions.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(200), nullable=False), sa.Column("lease_owner", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)))
    for table in IMMUTABLE_TABLES:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index("ix_uac_draft_binding", "uac_learning_drafts", ["tenant_id", "jira_key", "plan_fingerprint"])
    op.create_index("ix_uac_delta_issue_created", "uac_feedback_deltas", ["tenant_id", "jira_key", "created_at"])
    op.create_index("ix_uac_lesson_current", "uac_lesson_revisions", ["tenant_id", "lesson_id", "version"])
    op.create_index("ix_uac_outbox_ready", "uac_learning_outbox", ["tenant_id", "status", "next_attempt_at"])
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("CREATE FUNCTION reject_uac_learning_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Shared UAC learning records are immutable'; END; $$")
    for table in IMMUTABLE_TABLES:
        if dialect == "postgresql":
            op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_uac_learning_mutation()")
        elif dialect == "sqlite":
            for operation in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Shared UAC learning records are immutable'); END")


def downgrade():
    for table in ("uac_learning_outbox", "uac_lesson_revisions", "uac_feedback_bindings", "uac_feedback_deltas", "uac_learning_drafts"):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_uac_learning_mutation()")
