"""Add Jira CSV import provenance and run tracking.

Revision ID: add_jira_csv_import
Revises: add_uac_anti_repetition_memory
"""

from alembic import op
import sqlalchemy as sa


revision = "add_jira_csv_import"
down_revision = "add_uac_anti_repetition_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jira_enriched_issues", sa.Column("resolution", sa.String(length=120), nullable=True))
    op.add_column("jira_enriched_issues", sa.Column("jira_updated_at", sa.DateTime(), nullable=True))
    op.add_column("jira_enriched_issues", sa.Column("source_type", sa.String(length=80), nullable=True))
    op.add_column("jira_enriched_issues", sa.Column("source_file_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_jira_enriched_issues_resolution", "jira_enriched_issues", ["resolution"])
    op.create_index("ix_jira_enriched_issues_jira_updated_at", "jira_enriched_issues", ["jira_updated_at"])
    op.create_index("ix_jira_enriched_issues_source_type", "jira_enriched_issues", ["source_type"])
    op.create_index("ix_jira_enriched_issues_source_file_hash", "jira_enriched_issues", ["source_file_hash"])
    op.create_table(
        "jira_csv_import_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("filenames", sa.JSON(), nullable=False),
        sa.Column("file_hashes", sa.JSON(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("redacted_fields", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_jira_csv_import_runs_status", "jira_csv_import_runs", ["status"])


def downgrade():
    op.drop_index("ix_jira_csv_import_runs_status", table_name="jira_csv_import_runs")
    op.drop_table("jira_csv_import_runs")
    op.drop_index("ix_jira_enriched_issues_source_file_hash", table_name="jira_enriched_issues")
    op.drop_index("ix_jira_enriched_issues_source_type", table_name="jira_enriched_issues")
    op.drop_index("ix_jira_enriched_issues_jira_updated_at", table_name="jira_enriched_issues")
    op.drop_index("ix_jira_enriched_issues_resolution", table_name="jira_enriched_issues")
    op.drop_column("jira_enriched_issues", "source_file_hash")
    op.drop_column("jira_enriched_issues", "source_type")
    op.drop_column("jira_enriched_issues", "jira_updated_at")
    op.drop_column("jira_enriched_issues", "resolution")
