"""Schema migrations for existing databases."""
from sqlalchemy import text
from app.db.session import engine
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def run_migrations() -> None:
    """Apply schema migrations for existing databases."""
    try:
        db_url = str(engine.url)
        with engine.connect() as conn:
            if "sqlite" in db_url:
                # JiraIssue: embedding_json for pre-indexed embeddings
                try:
                    res = conn.execute(text("PRAGMA table_info(jira_issues)"))
                    jira_cols = [row[1] for row in res.fetchall()]
                    if "embedding_json" not in jira_cols:
                        conn.execute(text("ALTER TABLE jira_issues ADD COLUMN embedding_json TEXT"))
                        conn.commit()
                        logger.info("Migration: added embedding_json to jira_issues")
                except Exception as e:
                    logger.debug("jira_issues migration skipped: %s", e)

                result = conn.execute(text("PRAGMA table_info(run_feedback)"))
                columns = [row[1] for row in result.fetchall()]
                if "scenario_id" not in columns:
                    conn.execute(text("ALTER TABLE run_feedback ADD COLUMN scenario_id VARCHAR(100)"))
                    conn.commit()
                    logger.info("Migration: added scenario_id to run_feedback")
                for col, sql_type in [
                    ("user_rating", "VARCHAR(20)"),
                    ("expected_recipe_id", "VARCHAR(100)"),
                    ("suggested_recipe_id", "VARCHAR(100)"),
                    ("selected_feature", "VARCHAR(50)"),
                    ("selected_pattern", "VARCHAR(50)"),
                    ("recipes_used", "TEXT"),
                ]:
                    res = conn.execute(text("PRAGMA table_info(run_feedback)"))
                    cols = [row[1] for row in res.fetchall()]
                    if col not in cols:
                        conn.execute(text(f"ALTER TABLE run_feedback ADD COLUMN {col} {sql_type}"))
                        conn.commit()
                        logger.info("Migration: added %s to run_feedback", col)

                # Chat sessions and messages
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_sessions (
                            id VARCHAR(36) PRIMARY KEY,
                            title VARCHAR(500),
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_sessions table")
                except Exception as e:
                    logger.debug("chat_sessions migration skipped: %s", e)
                # llm_runs: retry_count for LLM observability
                try:
                    res = conn.execute(text("PRAGMA table_info(llm_runs)"))
                    llm_cols = [row[1] for row in res.fetchall()]
                    if llm_cols and "retry_count" not in llm_cols:
                        conn.execute(text("ALTER TABLE llm_runs ADD COLUMN retry_count INTEGER"))
                        conn.commit()
                        logger.info("Migration: added retry_count to llm_runs")
                except Exception as e:
                    logger.debug("llm_runs retry_count migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_messages (
                            id VARCHAR(36) PRIMARY KEY,
                            session_id VARCHAR(36) NOT NULL,
                            role VARCHAR(20) NOT NULL,
                            content TEXT,
                            tool_calls TEXT,
                            tool_results TEXT,
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_messages table")
                except Exception as e:
                    logger.debug("chat_messages migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_message_feedback (
                            id VARCHAR(36) PRIMARY KEY,
                            message_id VARCHAR(36) NOT NULL,
                            session_id VARCHAR(36) NOT NULL,
                            rating VARCHAR(50) NOT NULL,
                            correction_text TEXT,
                            error_type VARCHAR(100),
                            auto_detected INTEGER NOT NULL DEFAULT 0,
                            original_snippet TEXT,
                            correct_snippet TEXT,
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_message_feedback table")
                except Exception as e:
                    logger.debug("chat_message_feedback migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS learned_prompt_entries (
                            id VARCHAR(36) PRIMARY KEY,
                            prompt TEXT NOT NULL,
                            normalized_prompt TEXT NOT NULL,
                            prompt_hash VARCHAR(64) NOT NULL,
                            final_answer TEXT NOT NULL,
                            tags_json TEXT,
                            topic VARCHAR(120),
                            source_type VARCHAR(50) NOT NULL DEFAULT 'chat_feedback',
                            answer_style VARCHAR(100) NOT NULL DEFAULT 'senior_technical_docs',
                            status VARCHAR(30) NOT NULL DEFAULT 'pending_review',
                            accepted_at DATETIME,
                            approved_at DATETIME,
                            session_id VARCHAR(36),
                            message_id VARCHAR(36),
                            support_count INTEGER NOT NULL DEFAULT 1,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created learned_prompt_entries table")
                except Exception as e:
                    logger.debug("learned_prompt_entries migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_answer_quality (
                            id VARCHAR(36) PRIMARY KEY,
                            message_id VARCHAR(36) NOT NULL UNIQUE,
                            session_id VARCHAR(36) NOT NULL,
                            user_message_id VARCHAR(36),
                            grounding_status VARCHAR(30) NOT NULL DEFAULT 'none',
                            confidence REAL,
                            thin_evidence INTEGER NOT NULL DEFAULT 0,
                            has_conflict INTEGER NOT NULL DEFAULT 0,
                            source_domain VARCHAR(50),
                            answer_kind VARCHAR(80),
                            source_policy VARCHAR(80),
                            quality_score INTEGER NOT NULL DEFAULT 50,
                            weak_phrases_detected INTEGER NOT NULL DEFAULT 0,
                            needs_review INTEGER NOT NULL DEFAULT 0,
                            review_status VARCHAR(30),
                            langsmith_run_id VARCHAR(120),
                            langsmith_trace_url VARCHAR(500),
                            improvement_hints_json TEXT,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_answer_quality table")
                except Exception as e:
                    logger.debug("chat_answer_quality migration skipped: %s", e)
                try:
                    res = conn.execute(text("PRAGMA table_info(chat_sessions)"))
                    cs_cols = [row[1] for row in res.fetchall()]
                    if cs_cols and "last_generation_json" not in cs_cols:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN last_generation_json TEXT"))
                        conn.commit()
                        logger.info("Migration: added last_generation_json to chat_sessions")
                    if cs_cols and "user_id" not in cs_cols:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN user_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added user_id to chat_sessions")
                    if cs_cols and "tenant_id" not in cs_cols:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN tenant_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added tenant_id to chat_sessions")
                except Exception as e:
                    logger.debug("chat_sessions last_generation_json migration skipped: %s", e)
                try:
                    res = conn.execute(text("PRAGMA table_info(dataset_runs)"))
                    dr_cols = [row[1] for row in res.fetchall()]
                    if dr_cols and "user_id" not in dr_cols:
                        conn.execute(text("ALTER TABLE dataset_runs ADD COLUMN user_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added user_id to dataset_runs")
                    if dr_cols and "tenant_id" not in dr_cols:
                        conn.execute(text("ALTER TABLE dataset_runs ADD COLUMN tenant_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added tenant_id to dataset_runs")
                except Exception as e:
                    logger.debug("dataset_runs user/tenant migration skipped: %s", e)
                try:
                    res = conn.execute(text("PRAGMA table_info(jira_enriched_issues)"))
                    jira_enriched_cols = [row[1] for row in res.fetchall()]
                    for col, sql_type in (
                        ("resolution", "VARCHAR(120)"),
                        ("jira_updated_at", "DATETIME"),
                        ("source_type", "VARCHAR(80)"),
                        ("source_file_hash", "VARCHAR(64)"),
                        ("source_file_hashes", "JSON"),
                        ("import_provenance", "JSON"),
                        ("evidence_archive", "JSON"),
                        ("company_names", "JSON"),
                        ("customer_cohorts", "JSON"),
                        ("resolutions", "JSON"),
                    ):
                        if jira_enriched_cols and col not in jira_enriched_cols:
                            conn.execute(text(f"ALTER TABLE jira_enriched_issues ADD COLUMN {col} {sql_type}"))
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS jira_csv_import_runs (
                            id VARCHAR(36) PRIMARY KEY,
                            status VARCHAR(30) NOT NULL,
                            filenames JSON NOT NULL,
                            file_hashes JSON NOT NULL,
                            importer_version VARCHAR(40) NOT NULL DEFAULT '1',
                            customer_assignments JSON NOT NULL DEFAULT '{}',
                            profile_rebuild JSON NOT NULL DEFAULT '{}',
                            total_rows INTEGER NOT NULL DEFAULT 0,
                            processed_rows INTEGER NOT NULL DEFAULT 0,
                            indexed_issues INTEGER NOT NULL DEFAULT 0,
                            skipped_issues INTEGER NOT NULL DEFAULT 0,
                            metadata_merged_issues INTEGER NOT NULL DEFAULT 0,
                            failed_issues INTEGER NOT NULL DEFAULT 0,
                            chunks_indexed INTEGER NOT NULL DEFAULT 0,
                            redacted_fields INTEGER NOT NULL DEFAULT 0,
                            errors JSON NOT NULL,
                            created_by VARCHAR(120),
                            created_at DATETIME NOT NULL,
                            started_at DATETIME,
                            completed_at DATETIME
                        )
                    """))
                    run_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(jira_csv_import_runs)")).fetchall()]
                    for col, sql_type in (
                        ("importer_version", "VARCHAR(40) NOT NULL DEFAULT '1'"),
                        ("customer_assignments", "JSON NOT NULL DEFAULT '{}'"),
                        ("profile_rebuild", "JSON NOT NULL DEFAULT '{}'"),
                        ("metadata_merged_issues", "INTEGER NOT NULL DEFAULT 0"),
                    ):
                        if col not in run_cols:
                            conn.execute(text(f"ALTER TABLE jira_csv_import_runs ADD COLUMN {col} {sql_type}"))
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS jira_customer_profiles (
                            customer_key VARCHAR(120) PRIMARY KEY,
                            customer_name VARCHAR(200) NOT NULL,
                            issue_count INTEGER NOT NULL DEFAULT 0,
                            issue_types JSON NOT NULL,
                            problem_types JSON NOT NULL,
                            components JSON NOT NULL,
                            product_areas JSON NOT NULL,
                            domains JSON NOT NULL,
                            workflows JSON NOT NULL,
                            affected_outputs JSON NOT NULL,
                            dita_entities JSON NOT NULL,
                            content_data_signals JSON NOT NULL,
                            classification_quality JSON NOT NULL,
                            failure_areas JSON NOT NULL,
                            automation_signals JSON NOT NULL,
                            resolution_patterns JSON NOT NULL,
                            representative_keys JSON NOT NULL,
                            source_file_hashes JSON NOT NULL,
                            profile_version VARCHAR(40) NOT NULL DEFAULT '1',
                            profile_hash VARCHAR(64),
                            approval_status VARCHAR(30) NOT NULL DEFAULT 'draft',
                            approved_by VARCHAR(120),
                            approved_at DATETIME,
                            review_notes TEXT,
                            rebuilt_at DATETIME NOT NULL
                        )
                    """))
                    profile_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(jira_customer_profiles)")).fetchall()]
                    for col, sql_type in (
                        ("issue_types", "JSON NOT NULL DEFAULT '[]'"),
                        ("problem_types", "JSON NOT NULL DEFAULT '[]'"),
                        ("product_areas", "JSON NOT NULL DEFAULT '[]'"),
                        ("content_data_signals", "JSON NOT NULL DEFAULT '[]'"),
                        ("classification_quality", "JSON NOT NULL DEFAULT '{}'"),
                        ("profile_hash", "VARCHAR(64)"),
                        ("approval_status", "VARCHAR(30) NOT NULL DEFAULT 'draft'"),
                        ("approved_by", "VARCHAR(120)"),
                        ("approved_at", "DATETIME"),
                        ("review_notes", "TEXT"),
                    ):
                        if col not in profile_cols:
                            conn.execute(text(f"ALTER TABLE jira_customer_profiles ADD COLUMN {col} {sql_type}"))
                    conn.commit()
                    logger.info("Migration: ensured Jira CSV import schema")
                except Exception as e:
                    logger.debug("Jira CSV import migration skipped: %s", e)
            else:
                def col_exists(table: str, c: str) -> bool:
                    r = conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :t AND column_name = :c"
                        ),
                        {"t": table, "c": c},
                    )
                    return r.fetchone() is not None

                # JiraIssue: embedding_json
                if not col_exists("jira_issues", "embedding_json"):
                    conn.execute(text("ALTER TABLE jira_issues ADD COLUMN embedding_json TEXT"))
                    conn.commit()
                    logger.info("Migration: added embedding_json to jira_issues")

                if not col_exists("run_feedback", "scenario_id"):
                    conn.execute(text("ALTER TABLE run_feedback ADD COLUMN scenario_id VARCHAR(100)"))
                    conn.commit()
                    logger.info("Migration: added scenario_id to run_feedback")
                for col, sql_type in [
                    ("user_rating", "VARCHAR(20)"),
                    ("expected_recipe_id", "VARCHAR(100)"),
                    ("suggested_recipe_id", "VARCHAR(100)"),
                    ("selected_feature", "VARCHAR(50)"),
                    ("selected_pattern", "VARCHAR(50)"),
                    ("recipes_used", "TEXT"),
                ]:
                    if not col_exists("run_feedback", col):
                        conn.execute(text(f"ALTER TABLE run_feedback ADD COLUMN {col} {sql_type}"))
                        conn.commit()
                        logger.info("Migration: added %s to run_feedback", col)

                # llm_runs: retry_count for LLM observability
                try:
                    if col_exists("llm_runs", "retry_count") is False:
                        conn.execute(text("ALTER TABLE llm_runs ADD COLUMN retry_count INTEGER"))
                        conn.commit()
                        logger.info("Migration: added retry_count to llm_runs")
                except Exception as e:
                    logger.debug("llm_runs retry_count migration skipped: %s", e)
                # Chat sessions and messages (PostgreSQL)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_sessions (
                            id VARCHAR(36) PRIMARY KEY,
                            title VARCHAR(500),
                            created_at TIMESTAMP NOT NULL,
                            updated_at TIMESTAMP NOT NULL
                        )
                    """))
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_messages (
                            id VARCHAR(36) PRIMARY KEY,
                            session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                            role VARCHAR(20) NOT NULL,
                            content TEXT,
                            tool_calls TEXT,
                            tool_results TEXT,
                            created_at TIMESTAMP NOT NULL
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_sessions and chat_messages tables")
                except Exception as e:
                    logger.debug("chat tables migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_message_feedback (
                            id VARCHAR(36) PRIMARY KEY,
                            message_id VARCHAR(36) NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                            session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                            rating VARCHAR(50) NOT NULL,
                            correction_text TEXT,
                            error_type VARCHAR(100),
                            auto_detected BOOLEAN NOT NULL DEFAULT FALSE,
                            original_snippet TEXT,
                            correct_snippet TEXT,
                            created_at TIMESTAMP NOT NULL
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_message_feedback table (PostgreSQL)")
                except Exception as e:
                    logger.debug("chat_message_feedback migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS learned_prompt_entries (
                            id VARCHAR(36) PRIMARY KEY,
                            prompt TEXT NOT NULL,
                            normalized_prompt TEXT NOT NULL,
                            prompt_hash VARCHAR(64) NOT NULL,
                            final_answer TEXT NOT NULL,
                            tags_json TEXT,
                            topic VARCHAR(120),
                            source_type VARCHAR(50) NOT NULL DEFAULT 'chat_feedback',
                            answer_style VARCHAR(100) NOT NULL DEFAULT 'senior_technical_docs',
                            status VARCHAR(30) NOT NULL DEFAULT 'pending_review',
                            accepted_at TIMESTAMP,
                            approved_at TIMESTAMP,
                            session_id VARCHAR(36),
                            message_id VARCHAR(36),
                            support_count INTEGER NOT NULL DEFAULT 1,
                            created_at TIMESTAMP NOT NULL,
                            updated_at TIMESTAMP NOT NULL
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created learned_prompt_entries table (PostgreSQL)")
                except Exception as e:
                    logger.debug("learned_prompt_entries migration skipped: %s", e)
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_answer_quality (
                            id VARCHAR(36) PRIMARY KEY,
                            message_id VARCHAR(36) NOT NULL UNIQUE,
                            session_id VARCHAR(36) NOT NULL,
                            user_message_id VARCHAR(36),
                            grounding_status VARCHAR(30) NOT NULL DEFAULT 'none',
                            confidence DOUBLE PRECISION,
                            thin_evidence BOOLEAN NOT NULL DEFAULT FALSE,
                            has_conflict BOOLEAN NOT NULL DEFAULT FALSE,
                            source_domain VARCHAR(50),
                            answer_kind VARCHAR(80),
                            source_policy VARCHAR(80),
                            quality_score INTEGER NOT NULL DEFAULT 50,
                            weak_phrases_detected BOOLEAN NOT NULL DEFAULT FALSE,
                            needs_review BOOLEAN NOT NULL DEFAULT FALSE,
                            review_status VARCHAR(30),
                            langsmith_run_id VARCHAR(120),
                            langsmith_trace_url VARCHAR(500),
                            improvement_hints_json TEXT,
                            created_at TIMESTAMP NOT NULL,
                            updated_at TIMESTAMP NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                        )
                    """))
                    conn.commit()
                    logger.info("Migration: created chat_answer_quality table (PostgreSQL)")
                except Exception as e:
                    logger.debug("chat_answer_quality migration skipped: %s", e)
                try:
                    if col_exists("chat_sessions", "last_generation_json") is False:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN last_generation_json TEXT"))
                        conn.commit()
                        logger.info("Migration: added last_generation_json to chat_sessions (PostgreSQL)")
                    if col_exists("chat_sessions", "user_id") is False:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN user_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added user_id to chat_sessions (PostgreSQL)")
                    if col_exists("chat_sessions", "tenant_id") is False:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN tenant_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added tenant_id to chat_sessions (PostgreSQL)")
                except Exception as e:
                    logger.debug("chat_sessions last_generation_json migration skipped: %s", e)
                try:
                    if col_exists("dataset_runs", "user_id") is False:
                        conn.execute(text("ALTER TABLE dataset_runs ADD COLUMN user_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added user_id to dataset_runs (PostgreSQL)")
                    if col_exists("dataset_runs", "tenant_id") is False:
                        conn.execute(text("ALTER TABLE dataset_runs ADD COLUMN tenant_id VARCHAR(120)"))
                        conn.commit()
                        logger.info("Migration: added tenant_id to dataset_runs (PostgreSQL)")
                except Exception as e:
                    logger.debug("dataset_runs user/tenant migration skipped: %s", e)
                try:
                    for col, sql_type in (
                        ("resolution", "VARCHAR(120)"),
                        ("jira_updated_at", "TIMESTAMP"),
                        ("source_type", "VARCHAR(80)"),
                        ("source_file_hash", "VARCHAR(64)"),
                        ("source_file_hashes", "JSON"),
                        ("import_provenance", "JSON"),
                        ("evidence_archive", "JSON"),
                        ("company_names", "JSON"),
                        ("customer_cohorts", "JSON"),
                        ("resolutions", "JSON"),
                    ):
                        if col_exists("jira_enriched_issues", col) is False:
                            conn.execute(text(f"ALTER TABLE jira_enriched_issues ADD COLUMN {col} {sql_type}"))
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS jira_csv_import_runs (
                            id VARCHAR(36) PRIMARY KEY,
                            status VARCHAR(30) NOT NULL,
                            filenames JSON NOT NULL,
                            file_hashes JSON NOT NULL,
                            importer_version VARCHAR(40) NOT NULL DEFAULT '1',
                            customer_assignments JSON NOT NULL DEFAULT '{}'::json,
                            profile_rebuild JSON NOT NULL DEFAULT '{}'::json,
                            total_rows INTEGER NOT NULL DEFAULT 0,
                            processed_rows INTEGER NOT NULL DEFAULT 0,
                            indexed_issues INTEGER NOT NULL DEFAULT 0,
                            skipped_issues INTEGER NOT NULL DEFAULT 0,
                            metadata_merged_issues INTEGER NOT NULL DEFAULT 0,
                            failed_issues INTEGER NOT NULL DEFAULT 0,
                            chunks_indexed INTEGER NOT NULL DEFAULT 0,
                            redacted_fields INTEGER NOT NULL DEFAULT 0,
                            errors JSON NOT NULL,
                            created_by VARCHAR(120),
                            created_at TIMESTAMP NOT NULL,
                            started_at TIMESTAMP,
                            completed_at TIMESTAMP
                        )
                    """))
                    for col, sql_type in (
                        ("importer_version", "VARCHAR(40) NOT NULL DEFAULT '1'"),
                        ("customer_assignments", "JSON NOT NULL DEFAULT '{}'::json"),
                        ("profile_rebuild", "JSON NOT NULL DEFAULT '{}'::json"),
                        ("metadata_merged_issues", "INTEGER NOT NULL DEFAULT 0"),
                    ):
                        if col_exists("jira_csv_import_runs", col) is False:
                            conn.execute(text(f"ALTER TABLE jira_csv_import_runs ADD COLUMN {col} {sql_type}"))
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS jira_customer_profiles (
                            customer_key VARCHAR(120) PRIMARY KEY,
                            customer_name VARCHAR(200) NOT NULL,
                            issue_count INTEGER NOT NULL DEFAULT 0,
                            issue_types JSON NOT NULL,
                            problem_types JSON NOT NULL,
                            components JSON NOT NULL,
                            product_areas JSON NOT NULL,
                            domains JSON NOT NULL,
                            workflows JSON NOT NULL,
                            affected_outputs JSON NOT NULL,
                            dita_entities JSON NOT NULL,
                            content_data_signals JSON NOT NULL,
                            classification_quality JSON NOT NULL,
                            failure_areas JSON NOT NULL,
                            automation_signals JSON NOT NULL,
                            resolution_patterns JSON NOT NULL,
                            representative_keys JSON NOT NULL,
                            source_file_hashes JSON NOT NULL,
                            profile_version VARCHAR(40) NOT NULL DEFAULT '1',
                            profile_hash VARCHAR(64),
                            approval_status VARCHAR(30) NOT NULL DEFAULT 'draft',
                            approved_by VARCHAR(120),
                            approved_at TIMESTAMP,
                            review_notes TEXT,
                            rebuilt_at TIMESTAMP NOT NULL
                        )
                    """))
                    for col, sql_type in (
                        ("issue_types", "JSON NOT NULL DEFAULT '[]'::json"),
                        ("problem_types", "JSON NOT NULL DEFAULT '[]'::json"),
                        ("product_areas", "JSON NOT NULL DEFAULT '[]'::json"),
                        ("content_data_signals", "JSON NOT NULL DEFAULT '[]'::json"),
                        ("classification_quality", "JSON NOT NULL DEFAULT '{}'::json"),
                        ("profile_hash", "VARCHAR(64)"),
                        ("approval_status", "VARCHAR(30) NOT NULL DEFAULT 'draft'"),
                        ("approved_by", "VARCHAR(120)"),
                        ("approved_at", "TIMESTAMP"),
                        ("review_notes", "TEXT"),
                    ):
                        if col_exists("jira_customer_profiles", col) is False:
                            conn.execute(text(f"ALTER TABLE jira_customer_profiles ADD COLUMN {col} {sql_type}"))
                    conn.commit()
                    logger.info("Migration: ensured Jira CSV import schema (PostgreSQL)")
                except Exception as e:
                    logger.debug("Jira CSV import migration skipped: %s", e)
    except Exception as e:
        logger.warning("Migration skipped or failed (table may not exist yet): %s", e)
