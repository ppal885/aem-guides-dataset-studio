/**
 * Jira QA RAG REST client — index issues into Chroma (`jira_qa`) for API/tools; not a separate chat product surface.
 */
import { apiUrl, fetchJson, fetchWithRetry } from '@/utils/api';

export interface JiraCsvPreviewFile {
  filename: string;
  file_hash: string;
  rows: number;
  columns: number;
  duplicate_headers: Record<string, number>;
  resolution_counts: Record<string, number>;
  already_imported: boolean;
  detected_customer: string;
  assigned_customer: string;
  customer_confidence: 'high' | 'medium' | 'low' | 'none';
  customer_evidence_signals: string[];
  warnings: string[];
}

export interface JiraCsvPreview {
  valid: boolean;
  total_files: number;
  total_rows: number;
  unique_issue_keys: number;
  overlap_count: number;
  overlapping_issue_keys: string[];
  redacted_fields: number;
  files: JiraCsvPreviewFile[];
}

export interface JiraCsvImportStatus {
  import_id: string;
  status: 'pending' | 'running' | 'completed' | 'completed_with_errors' | 'failed';
  filenames: string[];
  total_rows: number;
  processed_rows: number;
  indexed_issues: number;
  skipped_issues: number;
  metadata_merged_issues: number;
  failed_issues: number;
  chunks_indexed: number;
  redacted_fields: number;
  errors: string[];
  progress_percent: number;
  profile_rebuild?: Record<string, unknown>;
}

async function postJiraCsvFiles<T>(
  files: File[],
  dryRun: boolean,
  customerAssignments: Record<string, string> = {}
): Promise<T> {
  const body = new FormData();
  files.forEach(file => body.append('files', file));
  body.append('customer_assignments_json', JSON.stringify(customerAssignments));
  const response = await fetchWithRetry(
    apiUrl(`/api/v1/admin/jira-rag/import-csv?dry_run=${dryRun ? 'true' : 'false'}`),
    { method: 'POST', body },
    { maxAttempts: 1 }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `Jira CSV import failed with HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function previewJiraCsvFiles(
  files: File[],
  customerAssignments: Record<string, string> = {}
): Promise<JiraCsvPreview> {
  return postJiraCsvFiles<JiraCsvPreview>(files, true, customerAssignments);
}

export function startJiraCsvImport(
  files: File[],
  customerAssignments: Record<string, string>
): Promise<{ import_id: string; status_url: string; preview: JiraCsvPreview }> {
  return postJiraCsvFiles(files, false, customerAssignments);
}

export function getJiraCsvImportStatus(importId: string): Promise<JiraCsvImportStatus> {
  return fetchJson(apiUrl(`/api/v1/admin/jira-rag/imports/${importId}`));
}

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
