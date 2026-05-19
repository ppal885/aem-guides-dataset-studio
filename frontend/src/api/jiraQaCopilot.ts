/**
 * Jira QA RAG REST client — index issues into Chroma (`jira_qa`) for API/tools; not a separate chat product surface.
 */
import { apiUrl, fetchJson } from '@/utils/api';

/** GET /api/v1/jira-rag/status/chunks — row count in the Jira QA Chroma collection. */
export async function getJiraQaChunkStatus(): Promise<{ collection: string; chunk_count: number }> {
  return fetchJson(apiUrl('/api/v1/jira-rag/status/chunks'));
}

export interface JiraRagIndexResponse {
  indexed_issues?: number;
  issues_indexed?: number;
  keys_returned?: number;
  issues_failed?: number;
  chunks?: number;
  chunks_avg_per_indexed_issue?: number | null;
  message?: string;
  error?: string;
  errors?: string[];
}

/** POST /api/v1/jira-rag/index — pull JQL issues into Chroma (uses JIRA_* env on server). */
export async function postJiraRagIndex(body: {
  jql: string;
  limit?: number;
  force_reindex?: boolean;
}): Promise<JiraRagIndexResponse> {
  return fetchJson<JiraRagIndexResponse>(apiUrl('/api/v1/jira-rag/index'), {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
