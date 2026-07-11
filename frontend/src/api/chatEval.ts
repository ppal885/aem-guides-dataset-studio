import { apiUrl, fetchJson } from '@/utils/api';

export interface ImprovementHint {
  type: string;
  message: string;
  action?: string;
}

export interface ChatEvalPair {
  session_id: string;
  session_title: string;
  user_message_id: string | null;
  assistant_message_id: string;
  question: string;
  answer: string;
  asked_at: string | null;
  answered_at: string | null;
  rating: 'up' | 'down' | null;
  feedback_comment: string | null;
  quality_score?: number;
  grounding_status?: string;
  confidence?: number | null;
  thin_evidence?: boolean;
  has_conflict?: boolean;
  source_domain?: string | null;
  weak_phrases_detected?: boolean;
  needs_review?: boolean;
  review_status?: string | null;
  langsmith_run_id?: string | null;
  langsmith_trace_url?: string | null;
  improvement_hints?: ImprovementHint[];
}

export interface ChatEvalPairsResponse {
  items: ChatEvalPair[];
  total: number;
  limit: number;
  offset: number;
  search: string;
  rating: string;
  weak_only?: boolean;
}

export interface ChatEvalStats {
  total_pairs: number;
  total_sessions: number;
  rated_pairs: number;
  thumbs_up: number;
  thumbs_down: number;
  unrated_pairs: number;
  avg_quality_score?: number;
  abstain_count?: number;
  needs_review_count?: number;
}

export interface ChatEvalTrendPoint {
  date: string;
  answers: number;
  avg_quality: number;
  abstain_count: number;
  weak_count: number;
}

export interface ChatEvalTrendsResponse {
  days: number;
  series: ChatEvalTrendPoint[];
}

export interface ChatEvalBreakdownItem {
  label: string;
  count: number;
}

export interface ChatEvalBreakdownResponse {
  avg_quality_score: number;
  abstain_rate: number;
  by_grounding_status: ChatEvalBreakdownItem[];
  by_source_domain: ChatEvalBreakdownItem[];
  by_rating: ChatEvalBreakdownItem[];
  confidence_buckets: ChatEvalBreakdownItem[];
}

export async function getChatEvalStats(): Promise<ChatEvalStats> {
  return fetchJson<ChatEvalStats>(apiUrl('/api/v1/chat/eval/stats'));
}

export async function listChatEvalPairs(options?: {
  limit?: number;
  offset?: number;
  search?: string;
  rating?: '' | 'up' | 'down' | 'none';
  weak_only?: boolean;
}): Promise<ChatEvalPairsResponse> {
  const params = new URLSearchParams();
  if (options?.limit != null) params.set('limit', String(options.limit));
  if (options?.offset != null) params.set('offset', String(options.offset));
  if (options?.search?.trim()) params.set('search', options.search.trim());
  if (options?.rating) params.set('rating', options.rating);
  if (options?.weak_only) params.set('weak_only', 'true');
  const qs = params.toString();
  return fetchJson<ChatEvalPairsResponse>(apiUrl(`/api/v1/chat/eval/pairs${qs ? `?${qs}` : ''}`));
}

export async function getChatEvalTrends(days = 30): Promise<ChatEvalTrendsResponse> {
  return fetchJson<ChatEvalTrendsResponse>(apiUrl(`/api/v1/chat/eval/trends?days=${days}`));
}

export async function getChatEvalBreakdown(): Promise<ChatEvalBreakdownResponse> {
  return fetchJson<ChatEvalBreakdownResponse>(apiUrl('/api/v1/chat/eval/breakdown'));
}

export async function promoteChatEvalPair(messageId: string): Promise<{ entry_id: string; created: boolean }> {
  return fetchJson(apiUrl(`/api/v1/chat/eval/pairs/${encodeURIComponent(messageId)}/promote`), {
    method: 'POST',
  });
}

export async function reviewChatEvalPair(
  messageId: string,
  status: 'pass' | 'fail' | 'needs_seed',
): Promise<Record<string, unknown>> {
  return fetchJson(apiUrl(`/api/v1/chat/eval/pairs/${encodeURIComponent(messageId)}/review`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}
