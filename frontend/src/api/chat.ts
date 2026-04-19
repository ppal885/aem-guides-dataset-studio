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

export interface ChatLlmUsageCall {
  status?: string;
  kind?: string;
  step_name?: string;
  provider?: string;
  model?: string;
  tokens_input?: number | null;
  tokens_output?: number | null;
  latency_ms?: number | null;
  used_fallback?: boolean;
  error_type?: string;
  error?: string;
}

export interface ChatLlmUsage {
  configured_provider?: string;
  configured_provider_label?: string;
  configured_model?: string;
  provider?: string;
  provider_label?: string;
  model?: string;
  available?: boolean;
  llm_used?: boolean;
  path?: string;
  call_count?: number;
  attempt_count?: number;
  steps?: string[];
  fallback_used?: boolean;
  calls?: ChatLlmUsageCall[];
  draft_stage?: {
    llm_draft_used?: boolean;
    path?: string;
    fields?: string[];
    step_name?: string;
    warning?: string;
  };
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
  llm?: ChatLlmUsage;
}

export interface ChatAttachmentMeta {
  asset_id?: string;
  kind: 'image' | 'reference_dita' | 'generated_dita' | string;
  filename: string;
  mime_type?: string;
  size_bytes?: number;
  url?: string;
  storage_path?: string | null;
  content_preview?: string | null;
}

export type ChatStyleStrictness = 'low' | 'medium' | 'high';
export type ChatAuthoringOutputMode =
  | 'xml_only'
  | 'xml_explanation'
  | 'xml_validation'
  | 'xml_style_diff';

/** Task/topic structural mode for reference-guided generation. */
export type ChatAuthoringPattern = 'default' | 'cisco_task' | 'cisco_reference' | 'auto';

/** Single topic vs diagram → map + stub topics. */
export type ChatScreenshotDeliverableMode = 'single_topic' | 'map_hierarchy';

export interface ChatDitaGenerationOptions {
  dita_type?: 'topic' | 'task' | 'concept' | 'reference' | 'map' | null;
  save_path?: string | null;
  file_name?: string | null;
  strict_validation?: boolean;
  style_strictness?: ChatStyleStrictness;
  preserve_prolog?: boolean;
  xref_placeholders?: boolean;
  auto_ids?: boolean;
  output_mode?: ChatAuthoringOutputMode;
  /** default | cisco_task | cisco_reference | auto (infer from reference). */
  authoring_pattern?: ChatAuthoringPattern;
  /** Use reference DOCTYPE line when serializing (also on for cisco_task / cisco_reference). */
  preserve_reference_doctype?: boolean;
  screenshot_deliverable?: ChatScreenshotDeliverableMode;
}

export interface ChatBundleArtifact {
  role: 'map' | 'topic';
  dita_type: string;
  filename: string;
  href: string;
  asset_id?: string | null;
  url?: string | null;
  xml_preview?: string;
}

export interface ChatDitaValidationResult {
  valid: boolean;
  repaired?: boolean;
  quality_score?: number | null;
  validator_errors?: string[];
  validator_warnings?: string[];
  structural_issues?: string[];
  review_issues?: Array<Record<string, unknown>>;
  aem_guides_validation_errors?: string[];
  applied_repairs?: string[];
}

export interface ChatAction {
  key: string;
  label: string;
  url?: string | null;
  description?: string | null;
}

export interface ChatSemanticPlanSection {
  name: string;
  purpose: string;
  details?: string[];
}

export interface ChatSemanticPlan {
  title: string;
  dita_type: 'topic' | 'task' | 'concept' | 'reference' | 'map' | string;
  shortdesc: string;
  audience?: string;
  purpose?: string;
  sections?: ChatSemanticPlanSection[];
  style_notes?: string[];
  source_notes?: string[];
}

export interface ChatLinkRecommendation {
  kind?: string;
  severity?: string;
  summary?: string;
  action?: string;
}

export interface ChatDitaAuthoringResult {
  status: 'saved' | 'valid' | 'repaired' | 'invalid' | 'error' | string;
  title: string;
  dita_type: 'topic' | 'task' | 'concept' | 'reference' | 'map' | string;
  xml_preview: string;
  validation_result: ChatDitaValidationResult;
  saved_asset_path?: string | null;
  artifact_url?: string | null;
  actions?: ChatAction[];
  message?: string;
  semantic_plan?: ChatSemanticPlan | null;
  image_context?: Record<string, unknown> | null;
  /** First reference summary (compat); prefer when only one reference attachment exists. */
  reference_summary?: Record<string, unknown> | null;
  /** Multi-reference order (future); server may emit alongside reference_summary. */
  reference_summaries?: Record<string, unknown>[];
  assumptions?: string[];
  style_profile_diff_summary?: string | null;
  screenshot_confidence?: number | null;
  explanation?: string | null;
  /** Safe xref/conref guidance — server never invents repository paths. */
  link_recommendations?: ChatLinkRecommendation[];
  debug?: Record<string, unknown>;
  bundle_artifacts?: ChatBundleArtifact[];
}

export interface ChatAgentStep {
  id: string;
  title: string;
  tool_name?: string;
  status?: string;
  approval_required?: boolean;
  summary?: string;
  note?: string;
  error?: string;
}

export interface ChatAgentPlan {
  goal: string;
  mode: string;
  status: string;
  requires_approval?: boolean;
  expected_outputs?: string[];
  resume_tokens?: string[];
  steps?: ChatAgentStep[];
}

export interface ChatAgentExecution {
  status: string;
  current_step_id?: string | null;
  steps?: ChatAgentStep[];
}

export interface ChatApprovalState {
  state: string;
  pending_step_id?: string;
  pending_tool_name?: string;
  prompt?: string;
  affected_artifacts?: string[];
  allowed_responses?: string[];
}

export interface ChatToolSchemaProperty {
  type?: string;
  description?: string;
  enum?: string[];
  items?: { type?: string };
}

export interface ChatToolSchema {
  type?: string;
  properties?: Record<string, ChatToolSchemaProperty>;
  required?: string[];
}

export interface ChatToolCatalogItem {
  name: string;
  slash_alias: string;
  title: string;
  description: string;
  category: string;
  args_schema: ChatToolSchema;
  approval_required: boolean;
  read_only: boolean;
  enabled: boolean;
  primary_arg?: string;
}

export interface ChatToolIntent {
  name: string;
  args: Record<string, unknown>;
  source: 'slash';
}

export interface SSEEvent {
  type: 'chunk' | 'done' | 'tool' | 'tool_start' | 'error' | 'grounding' | 'plan' | 'approval_required' | 'step_status';
  content?: string;
  message?: string;
  name?: string;
  result?: unknown;
  run_id?: string;
  grounding?: ChatGrounding;
  plan?: ChatAgentPlan;
  approval?: ChatApprovalState;
  execution?: ChatAgentExecution;
  step?: ChatAgentStep;
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
  } else if (event.type === 'plan' && event.plan != null) {
    callbacks.onPlan?.(event.plan);
  } else if (event.type === 'approval_required' && event.plan != null && event.approval != null) {
    callbacks.onApprovalRequired?.(event.plan, event.approval);
  } else if (event.type === 'step_status' && event.execution != null) {
    callbacks.onStepStatus?.(event.execution, event.step);
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
  onPlan?: (plan: ChatAgentPlan) => void;
  onApprovalRequired?: (plan: ChatAgentPlan, approval: ChatApprovalState) => void;
  onStepStatus?: (execution: ChatAgentExecution, step?: ChatAgentStep) => void;
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
  toolIntent?: ChatToolIntent;
  attachments?: {
    imageFile?: File | null;
    referenceDitaFile?: File | null;
  };
  generationOptions?: ChatDitaGenerationOptions;
  /** Optional Jira/issue text merged into screenshot authoring (server length-capped). */
  jiraContext?: string | null;
  /** Abort ongoing stream (Stop button). */
  signal?: AbortSignal;
}

export async function sendMessage(
  sessionId: string,
  content: string,
  callbacks: SseCallbacks,
  options?: SendMessageOptions
): Promise<void> {
  const imageFile = options?.attachments?.imageFile ?? null;
  const referenceDitaFile = options?.attachments?.referenceDitaFile ?? null;
  const hasAuthoringAttachments = Boolean(imageFile);

  let res: Response;
  if (hasAuthoringAttachments) {
    const formData = new FormData();
    formData.append('content', content);
    if (options?.context) {
      formData.append('context', JSON.stringify(options.context));
    }
    if (options?.humanPrompts !== undefined) {
      formData.append('human_prompts', String(options.humanPrompts));
    }
    if (options?.generationOptions?.dita_type) {
      formData.append('dita_type', String(options.generationOptions.dita_type));
    }
    if (options?.generationOptions?.save_path) {
      formData.append('save_path', String(options.generationOptions.save_path));
    }
    if (options?.generationOptions?.file_name) {
      formData.append('file_name', String(options.generationOptions.file_name));
    }
    if (options?.generationOptions?.strict_validation !== undefined) {
      formData.append('strict_validation', String(options.generationOptions.strict_validation));
    }
    if (options?.generationOptions?.style_strictness) {
      formData.append('style_strictness', String(options.generationOptions.style_strictness));
    }
    if (options?.generationOptions?.preserve_prolog !== undefined) {
      formData.append('preserve_prolog', String(options.generationOptions.preserve_prolog));
    }
    if (options?.generationOptions?.xref_placeholders !== undefined) {
      formData.append('xref_placeholders', String(options.generationOptions.xref_placeholders));
    }
    if (options?.generationOptions?.auto_ids !== undefined) {
      formData.append('auto_ids', String(options.generationOptions.auto_ids));
    }
    if (options?.generationOptions?.output_mode) {
      formData.append('output_mode', String(options.generationOptions.output_mode));
    }
    if (options?.generationOptions?.authoring_pattern) {
      formData.append('authoring_pattern', String(options.generationOptions.authoring_pattern));
    }
    if (options?.generationOptions?.preserve_reference_doctype !== undefined) {
      formData.append('preserve_reference_doctype', String(options.generationOptions.preserve_reference_doctype));
    }
    if (options?.generationOptions?.screenshot_deliverable) {
      formData.append('screenshot_deliverable', String(options.generationOptions.screenshot_deliverable));
    }
    const jc = (options?.jiraContext ?? '').trim();
    if (jc) {
      formData.append('jira_context', jc);
    }
    formData.append('image_attachment', imageFile);
    if (referenceDitaFile) {
      formData.append('reference_dita', referenceDitaFile);
    }
    res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages/authoring`), {
      method: 'POST',
      body: formData,
      signal: options?.signal,
    });
  } else {
    const body: Record<string, unknown> = {
      content,
      context: options?.context ?? undefined,
    };
    if (options?.humanPrompts !== undefined) {
      body.human_prompts = options.humanPrompts;
    }
    if (options?.toolIntent) {
      body.tool_intent = options.toolIntent;
    }
    res = await fetch(apiUrl(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options?.signal,
    });
  }
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

export async function listChatTools(): Promise<{ tools: ChatToolCatalogItem[] }> {
  return fetchJson(apiUrl('/api/v1/chat/tools'));
}

/** JSON body shape for POST /regenerate (snake_case for FastAPI). */
function generationOptionsToApiPayload(opts: ChatDitaGenerationOptions): Record<string, unknown> {
  return {
    dita_type: opts.dita_type ?? null,
    save_path: opts.save_path ?? null,
    file_name: opts.file_name ?? null,
    strict_validation: opts.strict_validation,
    style_strictness: opts.style_strictness,
    preserve_prolog: opts.preserve_prolog,
    xref_placeholders: opts.xref_placeholders,
    auto_ids: opts.auto_ids,
    output_mode: opts.output_mode,
    authoring_pattern: opts.authoring_pattern,
    preserve_reference_doctype: opts.preserve_reference_doctype,
    screenshot_deliverable: opts.screenshot_deliverable,
  };
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
  if (options?.generationOptions) {
    body.generation_options = generationOptionsToApiPayload(options.generationOptions);
  }
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

/** Fetch suggested prompts from backend (if available). */
export async function getSuggestedPrompts(): Promise<string[]> {
  try {
    const res = await fetch(apiUrl('/api/v1/chat/suggested-prompts'));
    if (!res.ok) return [];
    const data = await res.json();
    return data.prompts || data || [];
  } catch {
    return [];
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
