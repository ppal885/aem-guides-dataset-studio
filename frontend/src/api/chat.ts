/**
 * Chat API client - sessions, messages, streaming.
 */
import { apiUrl, fetchJson } from '@/utils/api';

export interface GenerateStatus {
  status: 'running' | 'completed' | 'failed';
  stage?: string;
  message?: string;
  jira_id?: string;
  run_id?: string;
  result?: { download_url?: string; jira_id?: string; run_id?: string };
  error?: string;
}

export async function getGenerateStatus(runId: string): Promise<GenerateStatus | null> {
  try {
    const res = await fetch(apiUrl(`/api/v1/ai/generate-status/${encodeURIComponent(runId)}`));
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string | null;
  tool_calls?: unknown;
  tool_results?: Record<string, unknown>;
  created_at: string | null;
}

export interface ChatGroundingCitation {
  id: string;
  label: string;
  title?: string;
  uri?: string;
}

export interface ChatGrounding {
  query: string;
  status: 'grounded' | 'partial' | 'abstain' | 'conflict' | string;
  confidence: number;
  reason: string;
  corrected_query?: string;
  correction_applied?: boolean;
  citations?: ChatGroundingCitation[];
  evidence_summary?: {
    evidence_count?: number;
    top_titles?: string[];
  };
  unsupported_points?: string[];
}

export interface SSEEvent {
  type: 'chunk' | 'done' | 'tool' | 'tool_start' | 'error' | 'grounding';
  content?: string;
  message?: string;
  name?: string;
  result?: unknown;
  run_id?: string;
  grounding?: ChatGrounding;
}

function dispatchSseEvent(event: SSEEvent, callbacks: SseCallbacks): void {
  if (event.type === 'chunk' && event.content != null) {
    callbacks.onChunk?.(event.content);
  } else if (event.type === 'done') {
    callbacks.onDone?.();
  } else if (event.type === 'tool' && event.name != null) {
    callbacks.onTool?.(event.name, event.result);
  } else if (event.type === 'tool_start' && event.name != null) {
    callbacks.onToolStart?.(event.name, event.run_id);
  } else if (event.type === 'grounding' && event.grounding != null) {
    callbacks.onGrounding?.(event.grounding);
  } else if (event.type === 'error') {
    callbacks.onError?.(event.message ?? 'Unknown error');
  }
}

export interface SseCallbacks {
  onChunk?: (content: string) => void;
  onDone?: () => void;
  onTool?: (name: string, result: unknown) => void;
  onToolStart?: (name: string, runId?: string) => void;
  onGrounding?: (grounding: ChatGrounding) => void;
  onError?: (message: string) => void;
}

/** Strip CRLF / trim so JSON.parse works on SSE payloads (Windows proxies, some servers). */
function parseSseDataPayload(rawLine: string): SSEEvent | null {
  const line = rawLine.replace(/\r$/, '').trimEnd();
  if (!line.startsWith('data: ')) return null;
  const jsonPart = line.slice(6).trim();
  if (!jsonPart) return null;
  try {
    return JSON.parse(jsonPart) as SSEEvent;
  } catch {
    return null;
  }
}

/**
 * Read newline-delimited SSE frames. If the stream closes without a terminal `done` or `error`
 * event (parse failure, dropped connection), still invoke onDone so the UI can reload messages —
 * fixes "Save & resend" appearing to do nothing when the final frame was not parsed.
 */
async function readChatSseBody(reader: ReadableStreamDefaultReader<Uint8Array>, callbacks: SseCallbacks): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let sawTerminal = false;
  let reading = true;

  const dispatch = (event: SSEEvent) => {
    if (event.type === 'done' || event.type === 'error') {
      sawTerminal = true;
    }
    dispatchSseEvent(event, callbacks);
  };

  // Stream until the browser closes the reader.
  while (reading) {
    const { done, value } = await reader.read();
    if (done) {
      reading = false;
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      const event = parseSseDataPayload(line);
      if (event) dispatch(event);
    }
  }
  if (buffer.length > 0) {
    const event = parseSseDataPayload(buffer);
    if (event) dispatch(event);
  }

  if (!sawTerminal) {
    callbacks.onDone?.();
  }
}

export async function createSession(): Promise<{ session_id: string }> {
  return fetchJson(apiUrl('/api/v1/chat/sessions'), { method: 'POST' });
}

export async function listSessions(limit?: number, offset?: number): Promise<{ sessions: ChatSession[] }> {
  const params = new URLSearchParams();
  if (limit != null) params.set('limit', String(limit));
  if (offset != null) params.set('offset', String(offset));
  const q = params.toString();
  return fetchJson(apiUrl(`/api/v1/chat/sessions${q ? `?${q}` : ''}`));
}

export async function getSession(id: string): Promise<{ session: ChatSession; messages: ChatMessage[] }> {
  return fetchJson(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(id)}`));
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(id)}`), { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
}

/** Delete sessions one-by-one (works on backends that only expose DELETE /sessions/{id}). */
async function deleteAllSessionsIndividually(): Promise<{ status: string; deleted: number }> {
  let deleted = 0;
  const pageSize = 100;
  let hasMore = true;
  while (hasMore) {
    const { sessions } = await listSessions(pageSize, 0);
    if (sessions.length === 0) {
      hasMore = false;
      break;
    }
    for (const s of sessions) {
      await deleteSession(s.id);
      deleted += 1;
    }
    if (sessions.length < pageSize) {
      hasMore = false;
    }
  }
  return { status: 'ok', deleted };
}

/** Delete every chat session and all messages. */
export async function deleteAllSessions(): Promise<{ status: string; deleted: number }> {
  const url = apiUrl('/api/v1/chat/all-sessions');
  const res = await fetch(url, { method: 'DELETE' });
  if (res.ok) {
    return res.json() as Promise<{ status: string; deleted: number }>;
  }
  // Older backends / some proxies return 404 for this path; fall back to per-session DELETE.
  if (res.status === 404) {
    return deleteAllSessionsIndividually();
  }
  const errText = await res.text().catch(() => '');
  let message = errText || res.statusText;
  try {
    const parsed = JSON.parse(errText) as { detail?: string };
    if (typeof parsed.detail === 'string') message = parsed.detail;
  } catch {
    /* keep message */
  }
  throw new Error(message);
}

export async function patchSessionTitle(sessionId: string, title: string): Promise<{ session: ChatSession }> {
  return fetchJson(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function patchUserMessage(
  sessionId: string,
  messageId: string,
  content: string
): Promise<{ messages: ChatMessage[] }> {
  const sid = (sessionId || '').trim();
  const mid = (messageId || '').trim();
  if (!sid || !mid) {
    throw new Error('Session id and message id are required to save an edit.');
  }
  return fetchJson(
    apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sid)}/messages/${encodeURIComponent(mid)}`),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }
  );
}

export async function getMessages(sessionId: string, limit?: number): Promise<{ messages: ChatMessage[] }> {
  const params = limit != null ? `?limit=${limit}` : '';
  return fetchJson(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages${params}`));
}

export interface ChatContext {
  source_page?: string;
  issue_key?: string;
  issue_summary?: string;
}

export interface SendMessageOptions {
  context?: ChatContext;
  /** When true, server appends human-precision rules (concise, less filler). Omit to use server env default. */
  humanPrompts?: boolean;
  /** Abort ongoing stream (Stop button). */
  signal?: AbortSignal;
}

export async function sendMessage(
  sessionId: string,
  content: string,
  callbacks: SseCallbacks,
  options?: SendMessageOptions
): Promise<void> {
  const body: Record<string, unknown> = {
    content,
    context: options?.context ?? undefined,
  };
  if (options?.humanPrompts !== undefined) {
    body.human_prompts = options.humanPrompts;
  }
  const res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }
  try {
    await readChatSseBody(reader, callbacks);
  } finally {
    reader.releaseLock();
  }
}

export async function regenerateAssistant(
  sessionId: string,
  callbacks: SseCallbacks,
  options?: SendMessageOptions
): Promise<void> {
  const body: Record<string, unknown> = {
    context: options?.context ?? undefined,
    human_prompts: options?.humanPrompts,
  };
  const res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/regenerate`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }
  try {
    await readChatSseBody(reader, callbacks);
  } finally {
    reader.releaseLock();
  }
}

/** Dataset job polling (create_job tool) — GET /api/v1/jobs/{id} */
export interface DatasetJobStatus {
  id: string;
  name?: string;
  status: string;
  error_message?: string | null;
  progress_percent?: number | null;
  files_generated?: number | null;
  total_files_estimated?: number | null;
  current_stage?: string | null;
  estimated_time_remaining?: string | null;
  result?: { files_generated?: number; [key: string]: unknown } | null;
}

export async function getDatasetJobStatus(jobId: string): Promise<DatasetJobStatus | null> {
  try {
    const res = await fetch(apiUrl(`/api/v1/jobs/${encodeURIComponent(jobId)}`));
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
