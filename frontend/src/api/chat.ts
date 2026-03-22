/**
 * Chat API client - sessions, messages, streaming.
 */
import { apiUrl, fetchJson, getTenantId, withTenantHeaders } from '@/utils/api';

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

export interface ChatNotice {
  code?: string;
  level?: 'info' | 'warning' | 'error';
  title?: string;
  message?: string;
}

export interface SSEEvent {
  type: 'chunk' | 'done' | 'tool' | 'tool_start' | 'error' | 'notice';
  content?: string;
  message?: string;
  name?: string;
  result?: unknown;
  run_id?: string;
  code?: string;
  level?: 'info' | 'warning' | 'error';
  title?: string;
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

export async function branchSessionFromMessage(
  sessionId: string,
  messageId: string
): Promise<{ session: ChatSession; messages: ChatMessage[] }> {
  return fetchJson(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/branches`), {
    method: 'POST',
    headers: withTenantHeaders({ 'Content-Type': 'application/json' }, getTenantId()),
    body: JSON.stringify({ message_id: messageId }),
  });
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(id)}`), { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
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

export async function sendMessage(
  sessionId: string,
  content: string,
  callbacks: {
    onChunk?: (content: string) => void;
    onDone?: () => void;
    onTool?: (name: string, result: unknown) => void;
    onToolStart?: (name: string, runId?: string) => void;
    onNotice?: (notice: ChatNotice) => void;
    onError?: (message: string) => void;
  },
  context?: ChatContext
): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`), {
    method: 'POST',
    headers: withTenantHeaders({ 'Content-Type': 'application/json' }, getTenantId()),
    body: JSON.stringify({ content, context: context ?? undefined }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }
  const decoder = new TextDecoder();
  let buffer = '';
  let reading = true;
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
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6)) as SSEEvent;
          if (event.type === 'chunk' && event.content != null) {
            callbacks.onChunk?.(event.content);
          } else if (event.type === 'done') {
            callbacks.onDone?.();
          } else if (event.type === 'tool' && event.name != null) {
            callbacks.onTool?.(event.name, event.result);
          } else if (event.type === 'tool_start' && event.name != null) {
            callbacks.onToolStart?.(event.name, event.run_id);
          } else if (event.type === 'notice') {
            callbacks.onNotice?.({
              code: event.code,
              level: event.level,
              title: event.title,
              message: event.message,
            });
          } else if (event.type === 'error') {
            callbacks.onError?.(event.message ?? 'Unknown error');
          }
        } catch {
          /* ignore parse errors */
        }
      }
    }
  }
  if (buffer.startsWith('data: ')) {
    try {
      const event = JSON.parse(buffer.slice(6)) as SSEEvent;
      if (event.type === 'chunk' && event.content != null) {
        callbacks.onChunk?.(event.content);
      } else if (event.type === 'done') {
        callbacks.onDone?.();
      } else if (event.type === 'tool' && event.name != null) {
        callbacks.onTool?.(event.name, event.result);
      } else if (event.type === 'tool_start' && event.name != null) {
        callbacks.onToolStart?.(event.name, event.run_id);
      } else if (event.type === 'notice') {
        callbacks.onNotice?.({
          code: event.code,
          level: event.level,
          title: event.title,
          message: event.message,
        });
      } else if (event.type === 'error') {
        callbacks.onError?.(event.message ?? 'Unknown error');
      }
    } catch {
      /* ignore */
    }
  }
}
