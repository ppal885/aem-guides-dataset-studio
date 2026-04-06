import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Pencil, RefreshCw, RotateCcw, ThumbsUp, ThumbsDown, UserRound, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { apiUrl } from '@/utils/api';
import type { ChatGrounding } from '@/api/chat';
import { AssistantAvatar } from './AssistantAvatar';
import { ChatMarkdown, CHAT_MARKDOWN_PROSE_CLASS } from './ChatMarkdown';
import { DatasetJobStatusCard } from './DatasetJobStatusCard';

interface ChatMessageProps {
  messageId: string;
  sessionId?: string;
  role: 'user' | 'assistant';
  content: string;
  toolResults?: Record<string, unknown>;
  onCopy?: () => void;
  /** User message: open inline edit */
  onSaveEdit?: (messageId: string, newContent: string) => Promise<void>;
  actionDisabled?: boolean;
  /** Last assistant bubble: regenerate reply */
  showRegenerate?: boolean;
  onRegenerate?: () => void;
  /** Error-style assistant bubble: retry (same as regenerate for server) */
  showRetry?: boolean;
  onRetry?: () => void;
}

function verifiedBundleUrlFromTools(toolResults?: Record<string, unknown>): string {
  if (!toolResults) return '';
  const gen = toolResults.generate_dita as Record<string, unknown> | undefined;
  const url = gen?.download_url as string | undefined;
  if (!url) return '';
  return apiUrl(url);
}

export function ChatMessage({
  messageId,
  sessionId,
  role,
  content,
  toolResults,
  onCopy,
  onSaveEdit,
  actionDisabled,
  showRegenerate,
  onRegenerate,
  showRetry,
  onRetry,
}: ChatMessageProps) {
  const isUser = role === 'user';
  const verifiedUrl = verifiedBundleUrlFromTools(toolResults);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  const submitFeedback = async (rating: 'up' | 'down') => {
    if (feedback === rating) return;
    setFeedback(rating);
    try {
      await fetch(`/api/v1/chat/sessions/${sessionId}/messages/${messageId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating }),
      });
    } catch {
      // silently fail — feedback is non-critical
    }
  };

  const startEdit = () => {
    setDraft(content);
    setSaveError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft(content);
    setSaveError(null);
  };

  const saveEdit = async () => {
    if (!onSaveEdit || !draft.trim()) return;
    setSaveError(null);
    setSaving(true);
    try {
      await onSaveEdit(messageId, draft.trim());
      setEditing(false);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className={cn(
        'group flex gap-3.5 animate-fadeIn',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {isUser ? (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-800 text-white shadow-sm"
          aria-hidden
        >
          <UserRound className="h-4 w-4" strokeWidth={2} />
        </div>
      ) : (
        <AssistantAvatar />
      )}

      <div
        className={cn(
          'min-w-0 w-full max-w-full flex-1 rounded-xl px-5 py-3.5 transition-all duration-200',
          isUser
            ? 'border border-slate-200/80 bg-white text-slate-900 shadow-sm'
            : 'border border-slate-200/60 bg-white text-slate-800 shadow-sm hover:shadow-md'
        )}
      >
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100/80 pb-2">
          <span
            className={cn(
              'text-[10px] font-bold uppercase tracking-[0.14em]',
              isUser ? 'text-slate-500' : 'text-indigo-500'
            )}
          >
            {isUser ? 'You' : 'Assistant'}
          </span>
          <div className="flex items-center gap-0.5">
            {isUser && onSaveEdit && !editing && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-slate-500 opacity-70 hover:opacity-100"
                onClick={startEdit}
                disabled={actionDisabled}
                title="Edit message"
              >
                <Pencil className="h-4 w-4" />
              </Button>
            )}
            {showRegenerate && onRegenerate && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-slate-500 opacity-70 hover:opacity-100"
                onClick={onRegenerate}
                disabled={actionDisabled}
                title="Regenerate reply"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            )}
            {showRetry && onRetry && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-amber-600 opacity-90 hover:opacity-100"
                onClick={onRetry}
                disabled={actionDisabled}
                title="Retry"
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
            )}
            {onCopy && content && !editing && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-slate-500 opacity-70 hover:opacity-100"
                onClick={onCopy}
                title="Copy message"
              >
                <Copy className="h-4 w-4" />
              </Button>
            )}
            {!isUser && sessionId && content && !editing && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    'h-8 w-8 p-0 opacity-70 hover:opacity-100',
                    feedback === 'up' ? 'text-emerald-600 opacity-100' : 'text-slate-500'
                  )}
                  onClick={() => submitFeedback('up')}
                  title="Helpful"
                >
                  <ThumbsUp className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    'h-8 w-8 p-0 opacity-70 hover:opacity-100',
                    feedback === 'down' ? 'text-rose-600 opacity-100' : 'text-slate-500'
                  )}
                  onClick={() => submitFeedback('down')}
                  title="Not helpful"
                >
                  <ThumbsDown className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
          </div>
        </div>

        <div className="text-[0.9375rem] leading-relaxed">
          {isUser ? (
            editing ? (
              <div className="space-y-2">
                {saveError && (
                  <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
                    {saveError}
                  </p>
                )}
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={4}
                  className="w-full resize-y rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-inner focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  disabled={saving}
                />
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={cancelEdit} disabled={saving}>
                    <X className="mr-1 h-3.5 w-3.5" />
                    Cancel
                  </Button>
                  <Button type="button" size="sm" onClick={saveEdit} disabled={saving || !draft.trim()}>
                    Save &amp; resend
                  </Button>
                </div>
              </div>
            ) : (
              <div className="whitespace-pre-wrap break-words text-slate-800">{content}</div>
            )
          ) : (
            <div className={CHAT_MARKDOWN_PROSE_CLASS}>
              <ChatMarkdown content={content} verifiedBundleUrl={verifiedUrl || undefined} />
            </div>
          )}
        </div>
        {toolResults && Object.keys(toolResults).length > 0 && (
          <CollapsibleToolResults toolResults={toolResults} />
        )}
      </div>
    </div>
  );
}

function CollapsibleToolResults({ toolResults }: { toolResults: Record<string, unknown> }) {
  const entries = Object.entries(toolResults);
  // Always show important tools (generate_dita, create_job, _grounding) expanded
  const importantTools = new Set(['generate_dita', 'create_job', '_grounding']);
  const hasImportant = entries.some(([name]) => importantTools.has(name));
  const manyTools = entries.length > 2;
  // Default collapsed when there are many non-important tool results
  const [expanded, setExpanded] = useState(!manyTools || hasImportant);

  // If only 1 tool result, just render directly
  if (entries.length <= 1) {
    return (
      <div className="mt-3 space-y-2 border-t border-slate-200/70 pt-3">
        {entries.map(([name, result]) => (
          <ToolResult key={name} name={name} result={result} />
        ))}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-slate-200/70 pt-3">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors"
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {entries.length} tool results
        {!expanded && (
          <span className="ml-1 text-slate-400">
            ({entries.filter(([, r]) => !(r as Record<string, unknown> | null)?.error).length} succeeded)
          </span>
        )}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {entries.map(([name, result]) => (
            <ToolResult key={name} name={name} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolResult({ name, result }: { name: string; result: unknown }) {
  const r = result as Record<string, unknown> | null;
  if (!r) return null;
  if (name === '_grounding') {
    return <GroundingPanel grounding={r as unknown as ChatGrounding} />;
  }
  const err = r.error as string | undefined;
  if (err) {
    return (
      <div className="rounded-xl border border-red-200/80 bg-red-50/90 p-3 text-xs text-red-700 shadow-sm">
        <span className="font-semibold">{name}</span>: {err}
      </div>
    );
  }
  const downloadUrl = r.download_url as string | undefined;
  const jiraId = r.jira_id as string | undefined;
  const runId = r.run_id as string | undefined;
  const resolutionWarning = r.resolution_warning as string | undefined;
  if (downloadUrl && name === 'generate_dita') {
    const fullUrl = apiUrl(downloadUrl);
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-emerald-200/90 bg-gradient-to-br from-emerald-50 to-green-50/80 p-3 shadow-sm">
        {resolutionWarning && (
          <p className="rounded-lg border border-amber-200 bg-amber-50/90 px-2 py-1.5 text-xs text-amber-900">
            {resolutionWarning}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={fullUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-md shadow-emerald-600/25 transition hover:bg-emerald-700"
          >
            Download DITA Bundle
          </a>
          {jiraId && runId && (
            <span className="text-xs text-slate-500">
              {jiraId} / {String(runId).slice(0, 8)}...
            </span>
          )}
        </div>
        <p className="text-xs text-slate-600">
          You can refine: &quot;Add a concept topic&quot;, &quot;Make steps more detailed&quot;, etc.
        </p>
      </div>
    );
  }
  const jobId = r.job_id as string | undefined;
  if (jobId && name === 'create_job') {
    const initialStatus = (r.status as string | undefined) ?? null;
    const recipeType = (r.recipe_type as string | undefined) ?? null;
    const downloadUrl = (r.download_url as string | undefined) ?? null;
    const jobName =
      (r.job_name as string | undefined) ??
      (recipeType ? `Dataset job: ${recipeType}` : 'Dataset generation in progress');
    return (
      <DatasetJobStatusCard
        jobId={jobId}
        initialStatus={initialStatus}
        recipeType={recipeType}
        downloadUrl={downloadUrl}
        jobName={jobName}
      />
    );
  }
  return (
    <pre className="max-h-24 overflow-auto rounded-lg border border-slate-200 bg-slate-50/90 p-2 text-xs">
      {JSON.stringify(r, null, 2)}
    </pre>
  );
}

function GroundingPanel({ grounding }: { grounding: ChatGrounding }) {
  const status = String(grounding.status || 'partial').toLowerCase();
  const tone =
    status === 'grounded'
      ? 'border-emerald-200 bg-emerald-50/90 text-emerald-900'
      : status === 'partial'
        ? 'border-amber-200 bg-amber-50/90 text-amber-900'
        : 'border-rose-200 bg-rose-50/90 text-rose-900';
  const badge =
    status === 'grounded'
      ? 'Grounded'
      : status === 'partial'
        ? 'Partially grounded'
        : status === 'conflict'
          ? 'Conflicting evidence'
          : 'Grounding limit';
  const citations = grounding.citations ?? [];
  const unsupportedPoints = grounding.unsupported_points ?? [];

  return (
    <div className={cn('rounded-xl border p-3 shadow-sm', tone)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-current/20 bg-white/70 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]">
          {badge}
        </span>
        <span className="text-xs opacity-80">Confidence {Math.round((grounding.confidence ?? 0) * 100)}%</span>
      </div>
      <p className="mt-2 text-sm leading-relaxed">{grounding.reason}</p>
      {grounding.correction_applied && grounding.corrected_query && (
        <p className="mt-2 text-xs opacity-80">
          Retrieval query: <span className="font-medium">{grounding.corrected_query}</span>
        </p>
      )}
      {unsupportedPoints.length > 0 && (
        <div className="mt-3 rounded-lg border border-white/50 bg-white/60 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em]">Not fully verified</p>
          <ul className="mt-1 space-y-1 text-xs leading-relaxed">
            {unsupportedPoints.slice(0, 3).map((point) => (
              <li key={point}>- {point}</li>
            ))}
          </ul>
        </div>
      )}
      {citations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {citations.slice(0, 4).map((citation) => (
            <a
              key={citation.id}
              href={citation.uri || undefined}
              target={citation.uri ? '_blank' : undefined}
              rel={citation.uri ? 'noreferrer' : undefined}
              className="inline-flex max-w-full items-center rounded-full border border-white/60 bg-white/75 px-3 py-1 text-xs font-medium text-current transition hover:bg-white"
            >
              <span className="truncate">{citation.label || citation.title || citation.id}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
