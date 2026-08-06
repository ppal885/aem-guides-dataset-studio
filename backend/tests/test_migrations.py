from sqlalchemy import create_engine, text

from app.db import migrations


def test_sqlite_jira_import_columns_are_added_without_run_feedback(monkeypatch, tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE jira_csv_import_runs (
                    id VARCHAR(36) PRIMARY KEY,
                    status VARCHAR(30) NOT NULL,
                    filenames JSON NOT NULL,
                    file_hashes JSON NOT NULL,
                    total_rows INTEGER NOT NULL DEFAULT 0,
                    processed_rows INTEGER NOT NULL DEFAULT 0,
                    indexed_issues INTEGER NOT NULL DEFAULT 0,
                    skipped_issues INTEGER NOT NULL DEFAULT 0,
                    failed_issues INTEGER NOT NULL DEFAULT 0,
                    chunks_indexed INTEGER NOT NULL DEFAULT 0,
                    redacted_fields INTEGER NOT NULL DEFAULT 0,
                    errors JSON NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    monkeypatch.setattr(migrations, "engine", database)

    migrations.run_migrations()

    with database.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(jira_csv_import_runs)")).fetchall()
        }
        run_feedback = connection.execute(text("PRAGMA table_info(run_feedback)")).fetchall()

    assert {
        "importer_version",
        "customer_assignments",
        "profile_rebuild",
        "metadata_merged_issues",
    } <= columns
    assert run_feedback == []
