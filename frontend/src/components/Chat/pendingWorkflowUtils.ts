import type {
  ChatAgentExecution,
  ChatAgentPlan,
  ChatApprovalState,
  ChatGenerateDitaPreview,
} from '@/api/chat';

function normalizeStatus(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

/** True when `generate_dita` in this message clearly produced a deliverable bundle. */
export function isGenerateDitaDeliveryComplete(toolResults?: Record<string, unknown> | null): boolean {
  if (!toolResults) return false;
  const gen = toolResults.generate_dita as Record<string, unknown> | undefined;
  if (!gen || typeof gen !== 'object') return false;
  if (gen.error) return false;
  const url = String(gen.download_url || gen.artifact_url || '').trim();
  if (url.length > 0) return true;
  const counts = gen.artifact_counts as Record<string, unknown> | undefined;
  if (counts && Number(counts.total_files ?? 0) > 0) return true;
  if (Array.isArray(gen.representative_files) && gen.representative_files.length > 0) return true;
  if (Array.isArray(gen.bundle_artifacts) && gen.bundle_artifacts.length > 0) return true;
  return false;
}

/**
 * When the server persists `_approval_state` alongside a finished `generate_dita` tool result,
 * the composer would keep showing "approve to generate" even though the bundle is already done.
 * Suppress that stale approval prompt in those cases.
 */
export function workflowApprovalSupersededByResults(toolResults: Record<string, unknown>): boolean {
  const approval = toolResults._approval_state as ChatApprovalState | undefined;
  if (!approval || normalizeStatus(approval.state) !== 'required') return false;

  const pendingRaw = String(approval.pending_tool_name ?? '').trim().toLowerCase();
  const pendingIsGenerateDita = pendingRaw === '' || pendingRaw === 'generate_dita';

  if (pendingIsGenerateDita && isGenerateDitaDeliveryComplete(toolResults)) {
    return true;
  }

  const exec = toolResults._agent_execution as ChatAgentExecution | undefined;
  const execStatus = normalizeStatus(exec?.status);
  if (
    pendingIsGenerateDita &&
    (execStatus === 'completed' ||
      execStatus === 'done' ||
      execStatus === 'succeeded' ||
      execStatus === 'success')
  ) {
    return true;
  }

  const steps = exec?.steps ?? [];
  if (pendingIsGenerateDita && steps.length > 0) {
    const allTerminal = steps.every((step) => {
      const st = normalizeStatus(step.status);
      return st === 'completed' || st === 'skipped';
    });
    if (allTerminal) return true;
  }

  return false;
}

export interface PendingWorkflowGuide {
  kind: 'clarification' | 'review';
  title: string;
  helper: string;
  detail: string;
  placeholder: string;
  suggestedReplies: string[];
}

function normalizeOptions(values: Array<unknown> | undefined): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const value of values || []) {
    const item = String(value || '').trim();
    if (!item) continue;
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(item);
  }
  return normalized;
}

function fallbackClarificationOptions(question: string): string[] {
  const lowered = question.toLowerCase();
  if (lowered.includes('concept') && lowered.includes('task') && lowered.includes('reference')) {
    return ['concept', 'task', 'reference', 'topic'];
  }
  return [];
}

function buildClarificationGuide(preview: ChatGenerateDitaPreview): PendingWorkflowGuide | null {
  const question = String(preview.clarification_question || '').trim();
  if (!preview.clarification_needed && !question) return null;
  const options = normalizeOptions(preview.clarification_request?.options) || [];
  const suggestedReplies = options.length > 0 ? options : fallbackClarificationOptions(question);
  const helper = question || 'I just need one missing DITA detail before I can keep going.';
  const placeholder =
    suggestedReplies.length > 0
      ? `For example: ${suggestedReplies[0]}`
      : 'Type the missing detail...';
  return {
    kind: 'clarification',
    title: 'One quick detail',
    helper,
    detail: 'Reply in one line or tap a button — no need to repeat your full request.',
    placeholder,
    suggestedReplies,
  };
}

function buildApprovalGuide(approval: ChatApprovalState): PendingWorkflowGuide | null {
  if (normalizeStatus(approval.state) !== 'required') return null;
  const suggestedReplies = normalizeOptions(approval.allowed_responses);
  const primary = suggestedReplies[0] || 'approve';
  const helper =
    approval.pending_tool_name === 'generate_dita'
      ? 'The bundle preview is ready. If it looks right, I can generate it now.'
      : String(approval.prompt || '').trim() || `I’m ready to run the next step when you are.`;
  return {
    kind: 'review',
    title: 'Ready when you are',
    helper,
    detail: 'Reply with approve to run it, or type a short change.',
    placeholder: `Type ${primary} to continue, or tell me what to change...`,
    suggestedReplies,
  };
}

export function buildPendingWorkflowGuide(toolResults?: Record<string, unknown> | null): PendingWorkflowGuide | null {
  if (!toolResults) return null;
  const plan = toolResults._agent_plan as ChatAgentPlan | undefined;
  const approval = toolResults._approval_state as ChatApprovalState | undefined;
  const preview = plan?.preview;

  if (preview && (plan?.status === 'clarification_required' || preview.clarification_needed)) {
    return buildClarificationGuide(preview);
  }
  if (approval && !workflowApprovalSupersededByResults(toolResults)) {
    return buildApprovalGuide(approval);
  }
  return null;
}

export type MessageLike = { role: string; id?: string; tool_results?: Record<string, unknown> | null };

function buildToolResultsSourceKey(prefix: string, toolResults: Record<string, unknown>): string {
  const plan = toolResults._agent_plan as ChatAgentPlan | undefined;
  const approval = toolResults._approval_state as ChatApprovalState | undefined;
  const preview = plan?.preview;
  const optionSig = JSON.stringify(approval?.allowed_responses ?? []);
  return [
    prefix,
    String(plan?.status ?? ''),
    preview?.clarification_needed ? '1' : '0',
    String(preview?.clarification_question ?? ''),
    String(approval?.state ?? ''),
    String(approval?.pending_tool_name ?? ''),
    optionSig,
    String(approval?.prompt ?? ''),
  ].join('\x1f');
}

export interface ResolvedPendingWorkflowGuide {
  guide: PendingWorkflowGuide | null;
  /** Stable id for dismiss UI; null when no guide */
  sourceKey: string | null;
}

/**
 * Walk assistant rows newest-first. A review banner from an older row is ignored when a newer
 * assistant message already shows a completed `generate_dita` delivery (common when the backend
 * persists approval on one message and the bundle on another).
 */
function findPendingWorkflowGuideInMessages(messages: MessageLike[]): ResolvedPendingWorkflowGuide {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role !== 'assistant') continue;
    const tr = message.tool_results || null;
    if (!tr) continue;
    const guide = buildPendingWorkflowGuide(tr);
    if (!guide) continue;
    if (guide.kind === 'review') {
      const hasNewerCompletedBundle = messages
        .slice(index + 1)
        .some(
          (m) =>
            m.role === 'assistant' && isGenerateDitaDeliveryComplete(m.tool_results as Record<string, unknown> | null)
        );
      if (hasNewerCompletedBundle) continue;
    }
    const id = message.id ?? `idx:${index}`;
    return { guide, sourceKey: buildToolResultsSourceKey(`msg:${id}`, tr) };
  }
  return { guide: null, sourceKey: null };
}

export function buildPendingWorkflowGuideFromMessages(messages: MessageLike[]): PendingWorkflowGuide | null {
  return findPendingWorkflowGuideInMessages(messages).guide;
}

/** Streaming blob first (in-progress), then persisted thread. */
export function resolvePendingWorkflowGuideWithKey(
  messages: MessageLike[],
  streamingToolResults?: Record<string, unknown> | null
): ResolvedPendingWorkflowGuide {
  if (streamingToolResults && Object.keys(streamingToolResults).length > 0) {
    const live = buildPendingWorkflowGuide(streamingToolResults);
    if (live) {
      return { guide: live, sourceKey: buildToolResultsSourceKey('stream', streamingToolResults) };
    }
    // Finished bundle in the current turn — do not surface an older assistant row's stale approval.
    if (isGenerateDitaDeliveryComplete(streamingToolResults)) {
      return { guide: null, sourceKey: null };
    }
    if (workflowApprovalSupersededByResults(streamingToolResults)) {
      return { guide: null, sourceKey: null };
    }
  }
  return findPendingWorkflowGuideInMessages(messages);
}

/** Streaming blob first (in-progress), then persisted thread. */
export function resolvePendingWorkflowGuide(
  messages: MessageLike[],
  streamingToolResults?: Record<string, unknown> | null
): PendingWorkflowGuide | null {
  return resolvePendingWorkflowGuideWithKey(messages, streamingToolResults).guide;
}
