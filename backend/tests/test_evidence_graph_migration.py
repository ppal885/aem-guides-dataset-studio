import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.evidence_graph_models import (
    EvidenceGraphAssertion,
    EvidenceGraphEdge,
    EvidenceGraphGeneration,
    EvidenceGraphNode,
    EvidenceGraphQueryAudit,
    EvidenceGraphSourceEvent,
    EvidenceGraphSourceState,
    EvidenceGraphSyncRun,
)


GRAPH_TABLES = [
    EvidenceGraphGeneration.__table__,
    EvidenceGraphNode.__table__,
    EvidenceGraphEdge.__table__,
    EvidenceGraphAssertion.__table__,
    EvidenceGraphSourceEvent.__table__,
    EvidenceGraphSourceState.__table__,
    EvidenceGraphSyncRun.__table__,
]
PHASE_B_TABLES = [EvidenceGraphQueryAudit.__table__]


def _migration_module(filename="20260808_add_evidence_graph.py", module_name="evidence_graph_migration"):
    path = Path(__file__).parents[1] / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_alembic_upgrade_and_downgrade_on_sqlite():
    engine = create_engine("sqlite://")
    migration = _migration_module()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert {table.name for table in GRAPH_TABLES} <= tables
        state_indexes = {item["name"] for item in inspect(connection).get_indexes("evidence_graph_source_state")}
        assert "ix_evidence_graph_source_state_active_generation_id" in state_indexes

        migration.downgrade()
        tables = set(inspect(connection).get_table_names())
        assert not ({table.name for table in GRAPH_TABLES} & tables)


def test_graph_models_compile_for_postgresql_dialect():
    dialect = postgresql.dialect()
    for table in [*GRAPH_TABLES, *PHASE_B_TABLES]:
        sql = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in sql
        for index in table.indexes:
            assert "CREATE INDEX" in str(CreateIndex(index).compile(dialect=dialect))


def test_phase_b_upgrade_and_downgrade_on_sqlite():
    engine = create_engine("sqlite://")
    phase_a = _migration_module()
    phase_b = _migration_module(
        "20260809_add_evidence_graph_phase_b.py",
        "evidence_graph_phase_b_migration",
    )
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        phase_a.op = operations
        phase_b.op = operations
        phase_a.upgrade()
        phase_b.upgrade()
        assert EvidenceGraphQueryAudit.__tablename__ in set(inspect(connection).get_table_names())

        phase_b.downgrade()
        assert EvidenceGraphQueryAudit.__tablename__ not in set(inspect(connection).get_table_names())
        phase_a.downgrade()
