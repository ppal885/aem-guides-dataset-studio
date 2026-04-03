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
                    res = conn.execute(text("PRAGMA table_info(chat_sessions)"))
                    cs_cols = [row[1] for row in res.fetchall()]
                    if cs_cols and "last_generation_json" not in cs_cols:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN last_generation_json TEXT"))
                        conn.commit()
                        logger.info("Migration: added last_generation_json to chat_sessions")
                except Exception as e:
                    logger.debug("chat_sessions last_generation_json migration skipped: %s", e)
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
                    if col_exists("chat_sessions", "last_generation_json") is False:
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN last_generation_json TEXT"))
                        conn.commit()
                        logger.info("Migration: added last_generation_json to chat_sessions (PostgreSQL)")
                except Exception as e:
                    logger.debug("chat_sessions last_generation_json migration skipped: %s", e)
    except Exception as e:
        logger.warning("Migration skipped or failed (table may not exist yet): %s", e)
