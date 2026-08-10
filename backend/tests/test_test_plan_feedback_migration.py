import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.test_plan_feedback_models import TestPlanQualityFeedback


def _migration_module(filename: str, module_name: str):
    path = Path(__file__).parents[1] / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_feedback_model_compiles_for_postgresql():
    dialect = postgresql.dialect()
    table = TestPlanQualityFeedback.__table__
    assert f"CREATE TABLE {table.name}" in str(CreateTable(table).compile(dialect=dialect))
    for index in table.indexes:
        assert "CREATE INDEX" in str(CreateIndex(index).compile(dialect=dialect))


def test_feedback_migration_upgrade_and_downgrade_on_sqlite():
    engine = create_engine("sqlite://")
    phase_a = _migration_module("20260808_add_evidence_graph.py", "feedback_phase_a")
    phase_b = _migration_module(
        "20260809_add_evidence_graph_phase_b.py",
        "feedback_phase_b",
    )
    feedback = _migration_module(
        "20260810_add_test_plan_quality_feedback.py",
        "feedback_migration",
    )
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        phase_a.op = operations
        phase_b.op = operations
        feedback.op = operations
        phase_a.upgrade()
        phase_b.upgrade()
        feedback.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert TestPlanQualityFeedback.__tablename__ in tables
        indexes = {
            item["name"]
            for item in inspect(connection).get_indexes(TestPlanQualityFeedback.__tablename__)
        }
        assert "ix_test_plan_feedback_plan_created" in indexes

        feedback.downgrade()
        assert TestPlanQualityFeedback.__tablename__ not in set(
            inspect(connection).get_table_names()
        )
        phase_b.downgrade()
        phase_a.downgrade()
