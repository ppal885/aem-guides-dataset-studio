-- Jira enrichment SQL store (logical "jira_issues" + "jira_chunks" from product spec).
-- Legacy table `jira_issues` (JiraIssue ORM) remains for older indexers; enriched rows live in `jira_enriched_issues`.
--
-- PostgreSQL (JSONB). Optional pgvector (uncomment if extension + dimension match your embedder):
--   CREATE EXTENSION IF NOT EXISTS vector;
--   ALTER TABLE jira_chunks ADD COLUMN embedding_vec vector(1536);
-- Application currently stores float arrays in `embedding` JSONB for portability.

CREATE TABLE IF NOT EXISTS jira_enriched_issues (
    id SERIAL PRIMARY KEY,
    jira_key VARCHAR(50) NOT NULL UNIQUE,
    summary TEXT,
    description TEXT,
    issue_type VARCHAR(120),
    status VARCHAR(120),
    priority VARCHAR(120),
    labels JSONB,
    components JSONB,
    customer_names JSONB,
    domain VARCHAR(80) NOT NULL DEFAULT 'unknown',
    sub_domain VARCHAR(120),
    affected_outputs JSONB,
    affected_features JSONB,
    dita_entities JSONB,
    symptoms JSONB,
    expected_behavior TEXT,
    actual_behavior TEXT,
    qa_risk_tags JSONB,
    automation_fit VARCHAR(200),
    missing_info JSONB,
    raw_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    indexed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_jira_enriched_issues_domain ON jira_enriched_issues (domain);
CREATE INDEX IF NOT EXISTS ix_jira_enriched_issues_indexed_at ON jira_enriched_issues (indexed_at);

CREATE TABLE IF NOT EXISTS jira_chunks (
    id SERIAL PRIMARY KEY,
    jira_key VARCHAR(50) NOT NULL REFERENCES jira_enriched_issues (jira_key) ON DELETE CASCADE,
    chunk_type VARCHAR(80) NOT NULL,
    chunk_text TEXT NOT NULL,
    domain VARCHAR(80),
    customer_names JSONB,
    affected_outputs JSONB,
    dita_entities JSONB,
    embedding JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_jira_chunks_jira_key ON jira_chunks (jira_key);
CREATE INDEX IF NOT EXISTS ix_jira_chunks_chunk_type ON jira_chunks (chunk_type);
CREATE INDEX IF NOT EXISTS ix_jira_chunks_domain ON jira_chunks (domain);
