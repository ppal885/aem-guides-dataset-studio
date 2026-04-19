import { useEffect, useState } from 'react';
import { Copy, Download, FileCode2, Image as ImageIcon, Pencil, RefreshCw, RotateCcw, ThumbsDown, ThumbsUp, UserRound, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { apiUrl } from '@/utils/api';
import type {
  ChatAgentExecution,
  ChatAgentPlan,
  ChatApprovalState,
  ChatAttachmentMeta,
  ChatDitaAuthoringResult,
  ChatDitaGenerationOptions,
  ChatGenerateDitaPreview,
  ChatGrounding,
  ChatLlmUsage,
} from '@/api/chat';
import { AssistantAvatar } from './AssistantAvatar';
import { ChatMarkdown, CHAT_MARKDOWN_PROSE_CLASS } from './ChatMarkdown';
import { DatasetJobStatusCard } from './DatasetJobStatusCard';
import {
  AuthoringGenerationSplitReview,
  type AuthoringVisualContext,
} from '@/components/Authoring/AuthoringGenerationSplitReview';
import { extractToolDisplayMeta, KNOWN_FIRST_PARTY_TOOLS } from './toolResultUtils';

interface ChatMessageProps {
  messageId: string;
  sessionId?: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string | null;
  toolResults?: Record<string, unknown>;
  /** When this assistant message is the latest screenshot authoring result, show thumbnail + options used. */
  authoringVisualContext?: AuthoringVisualContext | null;
  onCopy?: () => void;
  /** User message: open inline edit */
  onSaveEdit?: (messageId: string, newContent: string) => Promise<void>;
  actionDisabled?: boolean;
  /** Last assistant bubble: regenerate reply */
  showRegenerate?: boolean;
  onRegenerate?: () => void;
  /** Authoring result: regenerate with generation_options payload */
  onRegenerateAuthoring?: (options: ChatDitaGenerationOptions) => void;
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

function resolveArtifactUrl(url?: string | null): string {
  if (!url) return '';
  return url.startsWith('/') ? apiUrl(url) : url;
}

function downloadArtifact(url: string, filename?: string): void {
  if (!url) return;
  const anchor = document.createElement('a');
  anchor.href = url;
  if (filename) {
    anchor.download = filename;
  }
  anchor.rel = 'noreferrer';
  anchor.target = '_blank';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function decodeSvgDataUrl(url?: string | null): string {
  const value = String(url || '').trim();
  if (!value.toLowerCase().startsWith('data:image/svg+xml')) return '';
  const commaIndex = value.indexOf(',');
  if (commaIndex < 0) return '';
  const metadata = value.slice(0, commaIndex).toLowerCase();
  const payload = value.slice(commaIndex + 1);
  try {
    if (metadata.includes(';base64')) {
      return window.atob(payload);
    }
    return decodeURIComponent(payload);
  } catch {
    return '';
  }
}

function inferSvgMarkup(record: Record<string, unknown>, ...candidates: Array<string | undefined>): string {
  const direct = String(record.inline_svg || record.preview_svg || '').trim();
  if (direct.startsWith('<svg')) return direct;
  for (const candidate of candidates) {
    const decoded = decodeSvgDataUrl(candidate);
    if (decoded.startsWith('<svg')) return decoded;
  }
  return '';
}

function InlineSvgPreview({
  svg,
  title,
  className,
}: {
  svg: string;
  title: string;
  className?: string;
}) {
  return (
    <div
      role="img"
      aria-label={title}
      className={cn('w-full overflow-auto rounded-lg border bg-white', className)}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function coerceToolWarnings(result: Record<string, unknown>): string[] {
  const warnings = result.warnings;
  if (Array.isArray(warnings)) {
    return warnings.map((item) => String(item || '').trim()).filter(Boolean);
  }
  if (typeof warnings === 'string' && warnings.trim()) {
    return [warnings.trim()];
  }
  return [];
}

function ToolLead({
  result,
  className,
}: {
  result: Record<string, unknown>;
  className?: string;
}) {
  const summary = String(result.summary || '').trim();
  const warnings = coerceToolWarnings(result);
  if (!summary && warnings.length === 0) return null;

  return (
    <div className={cn('mb-2 space-y-2', className)}>
      {summary && (
        <p className="text-xs leading-5 text-slate-700">
          {summary}
        </p>
      )}
      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.slice(0, 2).map((warning) => (
            <div
              key={warning}
              className="rounded-lg border border-amber-200 bg-amber-50/90 px-2.5 py-1.5 text-[11px] leading-5 text-amber-900"
            >
              {warning}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function friendlyLlmPath(path?: string): string {
  switch (String(path || '').trim().toLowerCase()) {
    case 'tool_only':
      return 'Tools answered this directly';
    case 'tool_plus_llm':
      return 'Tools + LLM synthesis';
    case 'deterministic_only':
      return 'Deterministic generator only';
    case 'deterministic_plus_llm_draft':
      return 'Deterministic generator + LLM drafting';
    case 'llm_fallback_generation':
      return 'LLM fallback generation';
    default:
      return String(path || '').trim().replace(/_/g, ' ') || 'LLM path';
  }
}

function LlmUsagePanel({
  llm,
  className,
}: {
  llm?: ChatLlmUsage | null;
  className?: string;
}) {
  if (!llm || (!llm.path && !llm.configured_provider && !llm.provider)) return null;
  const provider = String(llm.provider_label || llm.provider || llm.configured_provider_label || llm.configured_provider || '').trim();
  const model = String(llm.model || llm.configured_model || '').trim();
  const steps = Array.isArray(llm.steps)
    ? llm.steps.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const draftFields = Array.isArray(llm.draft_stage?.fields)
    ? llm.draft_stage?.fields?.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  return (
    <div className={cn('rounded-lg border border-white/70 bg-white/80 px-3 py-2', className)}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">AI usage</p>
      <div className="mt-1 space-y-1 text-xs text-slate-700">
        {llm.path && (
          <p>
            <span className="font-semibold text-slate-900">Path:</span> {friendlyLlmPath(llm.path)}
          </p>
        )}
        {provider && (
          <p>
            <span className="font-semibold text-slate-900">Provider:</span> {provider}
            {model ? ` · ${model}` : ''}
          </p>
        )}
        {typeof llm.call_count === 'number' && (
          <p>
            <span className="font-semibold text-slate-900">Successful calls:</span> {llm.call_count}
            {typeof llm.attempt_count === 'number' ? ` / ${llm.attempt_count} attempt${llm.attempt_count === 1 ? '' : 's'}` : ''}
          </p>
        )}
        {steps.length > 0 && (
          <p>
            <span className="font-semibold text-slate-900">Steps:</span> {steps.join(', ')}
          </p>
        )}
        {draftFields.length > 0 && (
          <p>
            <span className="font-semibold text-slate-900">Drafted fields:</span> {draftFields.join(', ')}
          </p>
        )}
        {llm.draft_stage?.warning && (
          <p className="text-amber-700">{String(llm.draft_stage.warning)}</p>
        )}
      </div>
    </div>
  );
}

function formatBytes(value?: number): string {
  if (!value || value <= 0) return '';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function ChatMessage({
  messageId,
  sessionId,
  role,
  content,
  createdAt,
  toolResults,
  authoringVisualContext,
  onCopy,
  onSaveEdit,
  actionDisabled,
  showRegenerate,
  onRegenerate,
  onRegenerateAuthoring,
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
              isUser ? 'text-slate-500' : 'text-teal-600'
            )}
          >
            {isUser ? 'You' : 'Assistant'}
          </span>
          {createdAt && (
            <span className="text-[10px] text-slate-400 tabular-nums">
              {new Date(createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
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
                    feedback === 'up' ? 'text-teal-700 opacity-100' : 'text-slate-500'
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
                {feedback && (
                  <span className={cn(
                    'text-[10px] font-medium animate-fadeIn',
                    feedback === 'up' ? 'text-teal-600' : 'text-amber-500'
                  )}>
                    {feedback === 'up' ? 'Thanks!' : 'Noted'}
                  </span>
                )}
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
                  className="w-full resize-y rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-inner focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
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
          <div className="mt-3 space-y-2 border-t border-slate-200/70 pt-3">
            {Object.entries(toolResults)
              .sort(([a], [b]) => {
                const order = ['_agent_plan', '_approval_state', '_agent_execution', '_grounding'];
                const ai = order.indexOf(a);
                const bi = order.indexOf(b);
                const av = ai === -1 ? order.length : ai;
                const bv = bi === -1 ? order.length : bi;
                return av - bv;
              })
              .map(([name, result]) => (
              <ToolResult
                key={name}
                name={name}
                result={result}
                authoringOnRegenerate={showRegenerate ? onRegenerate : undefined}
                authoringOnRegenerateWithOptions={
                  showRegenerate && onRegenerateAuthoring ? onRegenerateAuthoring : undefined
                }
                authoringVisualContext={
                  name === 'generate_dita_from_attachments' ? authoringVisualContext : undefined
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ToolResult({
  name,
  result,
  authoringOnRegenerate,
  authoringOnRegenerateWithOptions,
  authoringVisualContext,
}: {
  name: string;
  result: unknown;
  /** When this is the last assistant message, wire chat regenerate for DITA authoring. */
  authoringOnRegenerate?: () => void;
  authoringOnRegenerateWithOptions?: (options: ChatDitaGenerationOptions) => void;
  authoringVisualContext?: AuthoringVisualContext | null;
}) {
  const r = result as Record<string, unknown> | null;
  if (!r) return null;
  if (name === '_agent_plan') {
    return <AgentPlanPanel plan={r as unknown as ChatAgentPlan} />;
  }
  if (name === '_approval_state') {
    return <ApprovalStatePanel approval={r as unknown as ChatApprovalState} />;
  }
  if (name === '_agent_execution') {
    return <AgentExecutionPanel execution={r as unknown as ChatAgentExecution} />;
  }
  if (name === '_grounding') {
    return <GroundingPanel grounding={r as unknown as ChatGrounding} />;
  }
  if (name === '_attachments') {
    return <AttachmentMetadataPanel attachments={r as unknown as ChatAttachmentMeta[]} />;
  }
  if (name === '_generation_options') {
    return <GenerationOptionsPanel options={r as unknown as ChatDitaGenerationOptions} />;
  }
  const err = r.error as string | undefined;
  if (err) {
    return (
      <div className="rounded-xl border border-red-200/80 bg-red-50/90 p-3 text-xs text-red-700 shadow-sm">
        <span className="font-semibold">{name}</span>: {err}
      </div>
    );
  }
  if (name === 'generate_xml_flowchart') {
    return <FlowchartResultPanel result={r} />;
  }
  if (name === 'generate_image') {
    return <ImageGenerationPanel result={r} />;
  }
  if (name === 'generate_dita_from_attachments') {
    return (
      <AttachmentAuthoringResultPanel
        result={r as unknown as ChatDitaAuthoringResult}
        onRegenerateTopic={authoringOnRegenerateWithOptions}
        onRegenerateTopicFallback={authoringOnRegenerate}
        visualContext={authoringVisualContext}
      />
    );
  }
  const downloadUrl = r.download_url as string | undefined;
  const jiraId = r.jira_id as string | undefined;
  const runId = r.run_id as string | undefined;
  const resolutionWarning = r.resolution_warning as string | undefined;
  if (downloadUrl && name === 'generate_dita') {
    const fullUrl = apiUrl(downloadUrl);
    const bundleSummary = String(r.bundle_summary || r.summary || '').trim();
    const artifactCounts = (r.artifact_counts as Record<string, unknown> | undefined) || {};
    const contractSummary = (r.contract_summary as Record<string, unknown> | undefined) || {};
    const contractCompliance = (r.contract_compliance as Record<string, unknown> | undefined) || {};
    const buildValidation = (r.build_validation as Record<string, unknown> | undefined) || {};
    const llmUsage = (r.llm_usage as ChatLlmUsage | undefined) || undefined;
    const representativeFiles = Array.isArray(r.representative_files)
      ? r.representative_files.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const requiredElements = Array.isArray(contractCompliance.required_elements)
      ? contractCompliance.required_elements.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const requiredAttributes = Array.isArray(contractCompliance.required_attributes)
      ? contractCompliance.required_attributes.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const requiredMetadata = Array.isArray(contractCompliance.required_metadata)
      ? contractCompliance.required_metadata.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const contractIssues = Array.isArray(contractCompliance.issues)
      ? contractCompliance.issues.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const buildIssues = Array.isArray(buildValidation.issues)
      ? buildValidation.issues.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const totalFiles = Number(artifactCounts.total_files || 0);
    const mapFiles = Number(artifactCounts.map_files || 0);
    const topicFiles = Number(artifactCounts.topic_files || 0);
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-teal-200 bg-teal-50/50 p-4 shadow-sm ring-1 ring-teal-900/5">
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
            className="inline-flex items-center rounded-lg bg-teal-700 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800"
          >
            Download DITA Bundle
          </a>
          {jiraId && runId && (
            <span className="text-xs text-slate-500">
              {jiraId} / {String(runId).slice(0, 8)}...
            </span>
          )}
        </div>
        {bundleSummary && (
          <p className="text-sm font-medium text-teal-950">{bundleSummary}</p>
        )}
          {(contractSummary.bundle_type || contractSummary.topic_family || contractSummary.subject || contractSummary.content_mode || contractSummary.glossary_usage_mode) && (
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2">
              <p className="text-xs font-semibold text-slate-800">Generation contract</p>
              <div className="mt-1 grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                {contractSummary.bundle_type && (
                  <p><span className="font-semibold text-slate-900">Bundle type:</span> {String(contractSummary.bundle_type).replace(/_/g, ' ')}</p>
              )}
              {contractSummary.topic_family && (
                <p><span className="font-semibold text-slate-900">Topic family:</span> {String(contractSummary.topic_family)}</p>
              )}
              {contractSummary.subject && (
                <p><span className="font-semibold text-slate-900">Subject:</span> {String(contractSummary.subject)}</p>
              )}
                {contractSummary.include_map !== undefined && (
                  <p><span className="font-semibold text-slate-900">Includes map:</span> {contractSummary.include_map ? 'yes' : 'no'}</p>
                )}
                {contractSummary.content_mode && (
                  <p><span className="font-semibold text-slate-900">Content mode:</span> {String(contractSummary.content_mode).replace(/_/g, ' ')}</p>
                )}
                {contractSummary.glossary_usage_mode && (
                  <p><span className="font-semibold text-slate-900">Glossary linkage:</span> {String(contractSummary.glossary_usage_mode).replace(/_/g, ' ')}</p>
                )}
              </div>
            </div>
          )}
        <LlmUsagePanel llm={llmUsage} />
        {(totalFiles > 0 || mapFiles > 0 || topicFiles > 0) && (
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2 text-xs text-slate-700">
              <div className="font-semibold text-slate-900">Total files</div>
              <div className="mt-1">{totalFiles || 'Unknown'}</div>
            </div>
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2 text-xs text-slate-700">
              <div className="font-semibold text-slate-900">Map files</div>
              <div className="mt-1">{mapFiles}</div>
            </div>
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2 text-xs text-slate-700">
              <div className="font-semibold text-slate-900">Topic files</div>
              <div className="mt-1">{topicFiles}</div>
            </div>
          </div>
        )}
        {representativeFiles.length > 0 && (
          <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Representative files</p>
            <ul className="mt-1 space-y-1 text-xs text-slate-700">
              {representativeFiles.slice(0, 6).map((file) => (
                <li key={file}>- {file}</li>
              ))}
            </ul>
          </div>
        )}
          {(requiredElements.length > 0 || requiredAttributes.length > 0 || requiredMetadata.length > 0 || contractIssues.length > 0 || buildValidation.status) && (
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Contract compliance</p>
              <div className="mt-1 space-y-2 text-xs text-slate-700">
                {requiredElements.length > 0 && (
                  <p>
                  <span className="font-semibold text-slate-900">Required tags:</span>{' '}
                  {requiredElements.map((item) => `<${item}>`).join(', ')}
                </p>
              )}
                {requiredAttributes.length > 0 && (
                  <p>
                    <span className="font-semibold text-slate-900">Required attributes:</span>{' '}
                    {requiredAttributes.map((item) => `@${item}`).join(', ')}
                  </p>
                )}
                {requiredMetadata.length > 0 && (
                  <p>
                    <span className="font-semibold text-slate-900">Required metadata:</span>{' '}
                    {requiredMetadata.join(', ')}
                  </p>
                )}
                {buildValidation.status && (
                  <p>
                    <span className="font-semibold text-slate-900">Build validation:</span>{' '}
                    {String(buildValidation.status).replace(/_/g, ' ')}
                    {buildValidation.validator ? ` (${String(buildValidation.validator)})` : ''}
                  </p>
                )}
                {contractIssues.length > 0 && (
                  <ul className="space-y-1 text-rose-700">
                    {contractIssues.map((issue) => (
                      <li key={issue}>- {issue}</li>
                    ))}
                  </ul>
                )}
                {buildIssues.length > 0 && (
                  <ul className="space-y-1 text-amber-700">
                    {buildIssues.map((issue) => (
                      <li key={issue}>- {issue}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
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
  // review_dita_xml — quality score + validation summary
  if (name === 'review_dita_xml' && r.quality_score !== undefined) {
    const score = r.quality_score as number;
    const ditaType = (r.dita_type as string) || 'unknown';
    const rawValidation = (r.validation_issues as Array<Record<string, unknown>>) || [];
    const normalizedValidation = (r.normalized_validation_issues as Array<Record<string, unknown>>) || [];
    const validation = normalizedValidation.length > 0
      ? normalizedValidation
      : rawValidation
          .map((v) => {
            const label = String(v.label || v.rule_id || v.message || 'DITA validation check').trim();
            const passing = Boolean(v.passing);
            return {
              label,
              severity: passing ? 'pass' : 'error',
              passing,
              message: passing ? `${label.replace(/\s+present$/i, '')} is present.` : `${label.replace(/\s+present$/i, '')} is missing.`,
              recommendation: '',
            };
          })
          .filter((v) => !v.passing);
    const suggestions = (r.suggestions as Record<string, unknown>) || {};
    const rawSuggestionItems = (suggestions.suggestions as Array<Record<string, unknown>>) || [];
    const normalizedSuggestions = ((r.normalized_suggestions as Array<Record<string, unknown>>) || rawSuggestionItems)
      .map((item) => ({
        title: String(item.title || item.rule_id || 'Improve DITA quality').trim(),
        severity: String(item.severity || 'info').trim(),
        description: String(item.description || item.why || '').trim(),
        recommendation: String(item.recommendation || item.after || item.fix_prompt || '').trim(),
        impact: String(item.impact || '').trim(),
      }))
      .filter((item) => item.title || item.description || item.recommendation);
    const priorityFixes = ((r.priority_fixes as Array<Record<string, unknown>>) || [])
      .map((item) => ({
        title: String(item.title || item.recommendation || 'Improve DITA quality').trim(),
        severity: String(item.severity || 'info').trim(),
        recommendation: String(item.recommendation || '').trim(),
        impact: String(item.impact || item.reason || '').trim(),
      }))
      .filter((item) => item.title || item.recommendation || item.impact);
    const reviewCounts = (r.review_counts as Record<string, unknown>) || {};
    const totalSuggestions = normalizedSuggestions.length || (suggestions.total as number) || 0;
    const errors = (reviewCounts.errors as number) || (suggestions.errors as number) || validation.filter((v) => String(v.severity) === 'error').length || 0;
    const warnings = (reviewCounts.warnings as number) || (suggestions.warnings as number) || validation.filter((v) => String(v.severity) === 'warning').length || 0;
    const toolWarnings = coerceToolWarnings(r);
    const documentProfile = (r.document_profile as Record<string, unknown> | undefined) || {};
    const reviewScope = String(r.review_scope || '').trim();
    const reviewScopeExplanation = String(r.review_scope_explanation || '').trim();
    const rootElement = String(documentProfile.root_element || ditaType || '').trim();
    const elementCount = Number(documentProfile.element_count || 0);
    const lineCount = Number(documentProfile.line_count || 0);
    const largeDocument = Boolean(documentProfile.large_document);
    const topTags = Array.isArray(documentProfile.top_tags)
      ? (documentProfile.top_tags as Array<Record<string, unknown>>)
          .map((item) => `${String(item.tag || '').trim()} (${Number(item.count || 0)})`)
          .filter(Boolean)
      : [];
    const reviewSummary = String(r.review_summary || r.summary || '').trim();
    const scoreGuidance = String(r.score_improvement_guidance || '').trim();
    const scoreBg = score >= 80 ? 'bg-teal-50 border-teal-200' : score >= 60 ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200';
    const scoreText = score >= 80 ? 'text-teal-700' : score >= 60 ? 'text-amber-600' : 'text-red-600';
    return (
      <div className={`rounded-xl border p-3 shadow-sm ${scoreBg}`}>
        <div className="flex items-center gap-3 mb-2">
          <div className={`text-2xl font-bold ${scoreText}`}>{score}</div>
          <div>
            <div className="text-sm font-medium text-slate-700">Quality Score</div>
            <div className="text-xs text-slate-500">Type: {ditaType}</div>
          </div>
        </div>
        {reviewSummary && (
          <p className="mb-2 text-xs leading-relaxed text-slate-700">{reviewSummary}</p>
        )}
        {(reviewScope || rootElement || elementCount > 0 || toolWarnings.length > 0) && (
          <div className="mb-3 rounded-lg border border-white/70 bg-white/75 p-2 text-xs text-slate-700">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-800">Review scope</span>
              {reviewScope && (
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-600">
                  {reviewScope.replace(/_/g, ' ')}
                </span>
              )}
              {largeDocument && (
                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-700">
                  large XML
                </span>
              )}
            </div>
            {reviewScopeExplanation && <p className="mt-1 leading-relaxed">{reviewScopeExplanation}</p>}
            {(rootElement || elementCount > 0 || lineCount > 0) && (
              <p className="mt-1 text-slate-600">
                {[rootElement ? `Root: <${rootElement}>` : '', elementCount > 0 ? `${elementCount} elements` : '', lineCount > 0 ? `${lineCount} lines` : '']
                  .filter(Boolean)
                  .join(' | ')}
              </p>
            )}
            {topTags.length > 0 && (
              <p className="mt-1 text-slate-500">Most common tags: {topTags.slice(0, 5).join(', ')}</p>
            )}
            {toolWarnings.length > 0 && (
              <div className="mt-2 space-y-1">
                {toolWarnings.slice(0, 3).map((warning) => (
                  <p key={warning} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-amber-900">
                    {warning}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
        {(errors > 0 || warnings > 0 || totalSuggestions > 0) && (
          <div className="flex gap-3 text-xs">
            {errors > 0 && <span className="text-red-600 font-medium">{errors} error{errors !== 1 ? 's' : ''}</span>}
            {warnings > 0 && <span className="text-amber-600 font-medium">{warnings} warning{warnings !== 1 ? 's' : ''}</span>}
            {totalSuggestions > 0 && <span className="text-slate-500">{totalSuggestions} suggestion{totalSuggestions !== 1 ? 's' : ''}</span>}
          </div>
        )}
        {priorityFixes.length > 0 && (
          <div className="mt-3 rounded-lg border border-white/70 bg-white/70 p-2">
            <div className="mb-1 text-xs font-semibold text-slate-700">What to improve first</div>
            <div className="space-y-1.5">
              {priorityFixes.slice(0, 4).map((fix, i) => (
                <div key={i} className="text-xs text-slate-700">
                  <span className={fix.severity === 'error' ? 'font-semibold text-red-700' : fix.severity === 'warning' ? 'font-semibold text-amber-700' : 'font-semibold text-slate-700'}>
                    {fix.title}
                  </span>
                  {(fix.recommendation || fix.impact) && (
                    <span className="text-slate-600">: {[fix.recommendation, fix.impact].filter(Boolean).join(' ')}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {validation.length > 0 && (
          <div className="mt-3 max-h-40 overflow-auto text-xs text-slate-700 space-y-1.5">
            <div className="font-semibold text-slate-700">Validation findings</div>
            {validation.slice(0, 6).map((v, i) => (
              <div key={i} className="rounded-md bg-white/70 p-2">
                <div className="font-medium">{String(v.message || v.label || 'DITA validation finding')}</div>
                {v.recommendation && (
                  <div className="mt-0.5 text-slate-600">Fix: {String(v.recommendation)}</div>
                )}
                {v.impact && (
                  <div className="mt-0.5 text-slate-500">Impact: {String(v.impact)}</div>
                )}
              </div>
            ))}
            {validation.length > 6 && (
              <div className="text-slate-500 italic">...and {validation.length - 6} more</div>
            )}
          </div>
        )}
        {scoreGuidance && (
          <p className="mt-3 text-xs font-medium text-slate-700">{scoreGuidance}</p>
        )}
        {normalizedSuggestions.length > 0 && (
          <details open className="mt-3 rounded-lg border border-white/70 bg-white/70 p-2 text-xs text-slate-700">
            <summary className="cursor-pointer font-semibold text-slate-800 hover:underline">
              Show detailed suggestions
            </summary>
            <div className="mt-2 space-y-2">
              {normalizedSuggestions.slice(0, 8).map((suggestion, i) => (
                <div key={i} className="border-t border-slate-100 pt-2 first:border-t-0 first:pt-0">
                  <div className="font-medium">{suggestion.title}</div>
                  {suggestion.description && <div className="mt-0.5 text-slate-600">{suggestion.description}</div>}
                  {suggestion.recommendation && <div className="mt-0.5 text-slate-600">Recommended fix: {suggestion.recommendation}</div>}
                  {suggestion.impact && <div className="mt-0.5 text-slate-500">Impact: {suggestion.impact}</div>}
                </div>
              ))}
              {normalizedSuggestions.length > 8 && (
                <div className="text-slate-500 italic">...and {normalizedSuggestions.length - 8} more suggestions</div>
              )}
            </div>
          </details>
        )}
      </div>
    );
  }
  // get_job_status — reuse DatasetJobStatusCard
  if (name === 'get_job_status' && r.id) {
    return (
      <DatasetJobStatusCard
        jobId={r.id as string}
        initialStatus={(r.status as string) ?? null}
        recipeType={null}
        downloadUrl={(r.download_url as string) ?? null}
        jobName={(r.name as string) ?? 'Dataset job'}
      />
    );
  }
  // find_recipes — recipe list cards
  if (name === 'find_recipes' && r.recipes) {
    const recipes = r.recipes as Array<Record<string, unknown>>;
    return (
      <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
        <div className="text-xs font-medium text-teal-900 mb-2">
          {recipes.length} matching recipe{recipes.length !== 1 ? 's' : ''}
        </div>
        <ToolLead result={r} />
        <div className="space-y-1.5">
          {recipes.map((rec, i) => (
            <div key={i} className="text-xs">
              <span className="font-mono font-medium text-teal-800">{String(rec.recipe_id)}</span>
              {rec.description && (
                <span className="text-slate-600 ml-1.5">&mdash; {String(rec.description).slice(0, 120)}</span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }
  // lookup_aem_guides — teal-themed doc cards with clickable URLs
  if (name === 'lookup_aem_guides' && r.results) {
    const results = r.results as Array<Record<string, unknown>>;
    return (
      <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
        <div className="text-xs font-medium text-teal-900 mb-2">
          {results.length} AEM Guides doc{results.length !== 1 ? 's' : ''} found
        </div>
        <ToolLead result={r} />
        <div className="space-y-1.5">
          {results.slice(0, 5).map((doc, i) => (
            <div key={i} className="text-xs">
              <a href={String(doc.url)} target="_blank" rel="noreferrer"
                 className="font-medium text-teal-800 hover:underline">
                {String(doc.title || doc.url).slice(0, 100)}
              </a>
            </div>
          ))}
        </div>
      </div>
    );
  }
  // search_tenant_knowledge — purple-themed knowledge base results
  if (name === 'search_tenant_knowledge') {
    const results = (r.results as Array<Record<string, unknown>>) || [];
    const indexedCount = (r.indexed_doc_count as number) || 0;
    if (results.length === 0) {
      return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
          {r.message ? String(r.message) : `No matching results (${indexedCount} docs indexed)`}
        </div>
      );
    }
    return (
      <div className="rounded-xl border border-purple-200/80 bg-purple-50/50 p-3 shadow-sm">
        <div className="text-xs font-medium text-purple-800 mb-2">
          {results.length} result{results.length !== 1 ? 's' : ''} from knowledge base ({indexedCount} docs)
        </div>
        <ToolLead result={r} />
        <div className="space-y-1.5">
          {results.slice(0, 5).map((rec, i) => (
            <div key={i} className="text-xs">
              {rec.label && <span className="font-medium text-purple-700">{String(rec.label)}</span>}
              {rec.doc_type && <span className="ml-1 text-purple-400">({String(rec.doc_type)})</span>}
            </div>
          ))}
        </div>
      </div>
    );
  }
  // lookup_output_preset — teal-themed output config card
  if (name === 'lookup_output_preset' && (r.seed_results || r.doc_results)) {
    const seeds = (r.seed_results as Array<Record<string, unknown>>) || [];
    const docs = (r.doc_results as Array<Record<string, unknown>>) || [];
    const outType = r.output_type as string;
    return (
      <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <div className="text-xs font-medium text-teal-800">Output Configuration</div>
          {outType && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-100 text-teal-700 font-medium">
              {outType.replace('_', ' ')}
            </span>
          )}
        </div>
        <ToolLead result={r} />
        <div className="space-y-1 text-xs">
          {seeds.slice(0, 3).map((s, i) => (
            <div key={i} className="text-slate-600">
              <span className="font-mono text-teal-700">{String(s.element_name)}</span>
            </div>
          ))}
          {docs.length > 0 && (
            <div className="mt-1.5 pt-1.5 border-t border-teal-100">
              {docs.slice(0, 2).map((d, i) => (
                <a key={i} href={String(d.url)} target="_blank" rel="noreferrer"
                   className="block text-teal-700 hover:underline text-xs">
                  {String(d.title || d.url).slice(0, 80)}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }
  // list_jobs — job history table
  if (name === 'list_jobs' && r.jobs) {
    const jobs = r.jobs as Array<Record<string, unknown>>;
    const total = (r.total_count as number) || jobs.length;
    return (
      <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
        <div className="text-xs font-medium text-teal-900 mb-2">
          {total} job{total !== 1 ? 's' : ''} found
        </div>
        <ToolLead result={r} />
        <div className="space-y-1.5 max-h-48 overflow-auto">
          {jobs.map((j, i) => {
            const st = String(j.status || 'unknown');
            const stColor =
              st === 'completed'
                ? 'text-teal-800 bg-teal-50 border border-teal-200/80'
                : st === 'running'
                  ? 'text-teal-900 bg-white border border-teal-300'
                  : st === 'failed'
                    ? 'text-red-600 bg-red-50 border border-red-200/80'
                    : 'text-amber-700 bg-amber-50 border border-amber-200/80';
            return (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={`px-1.5 py-0.5 rounded font-medium text-[10px] ${stColor}`}>{st}</span>
                <span className="font-medium text-slate-700 truncate flex-1">{String(j.name || j.id)}</span>
                {j.progress_percent !== null && j.progress_percent !== undefined && (
                  <span className="text-slate-400">{String(j.progress_percent)}%</span>
                )}
                {j.created_at && (
                  <span className="text-slate-400 text-[10px]">{String(j.created_at).slice(0, 10)}</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }
  // fix_dita_xml — fixed XML result card
  if (name === 'fix_dita_xml') {
    const changed = r.changed as boolean;
    const summary = r.change_summary as string;
    const score = r.quality_score as number | undefined;
    const fixedXml = r.fixed_xml as string;
    const borderColor = changed ? 'border-teal-200 bg-teal-50/60' : 'border-slate-200 bg-slate-50';
    return (
      <div className={`rounded-xl border p-3 shadow-sm ${borderColor}`}>
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium ${changed ? 'text-teal-800' : 'text-slate-500'}`}>
            {changed ? '✅ Fix Applied' : 'No changes needed'}
          </span>
          {score !== undefined && (
            <span className={`text-xs font-bold ${score >= 80 ? 'text-teal-700' : score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
              Score: {score}
            </span>
          )}
        </div>
        {summary && <p className="text-xs text-slate-600 mb-2">{summary}</p>}
        {changed && fixedXml && (
          <details className="text-xs">
            <summary className="cursor-pointer text-teal-800 font-medium hover:underline">Show fixed XML</summary>
            <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-white border border-teal-100 p-2 text-[11px] font-mono whitespace-pre-wrap">
              {String(fixedXml).slice(0, 3000)}
            </pre>
          </details>
        )}
      </div>
    );
  }
  // lookup_dita_attribute / attribute-aware lookup_dita_spec — attribute detail card
  if (name === 'lookup_dita_attribute' && Array.isArray(r.attributes) && r.attributes.length > 1) {
    const attrs = (r.attributes as Array<Record<string, unknown>>)
      .filter((item) => item && typeof item === 'object')
      .slice(0, 6);
    return (
      <div className="rounded-xl border border-slate-300/80 bg-slate-50/50 p-3 shadow-sm">
        <div className="mb-2 flex items-center gap-2">
          <div className="text-sm font-bold text-slate-800">DITA attributes</div>
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-700">
            {attrs.length} matched
          </span>
        </div>
        {r.summary && <p className="mb-3 text-xs leading-5 text-slate-700">{String(r.summary)}</p>}
        <div className="space-y-2">
          {attrs.map((item, index) => {
            const attrName = String(item.attribute_name || '').trim();
            const values = Array.isArray(item.all_valid_values) ? (item.all_valid_values as string[]) : [];
            const elements = Array.isArray(item.supported_elements) ? (item.supported_elements as string[]) : [];
            const usageContexts = Array.isArray(item.usage_contexts) ? (item.usage_contexts as string[]) : [];
            const commonMistakes = Array.isArray(item.common_mistakes) ? (item.common_mistakes as string[]) : [];
            const examples = Array.isArray(item.correct_examples) ? (item.correct_examples as string[]) : [];
            const textContent = String(item.text_content || '').trim();
            const textPreview = textContent.slice(0, 220);
            const hasMoreText = textContent.length > 220;
            return (
              <div key={`${attrName}-${index}`} className="rounded-lg border border-slate-200 bg-white/80 p-2.5">
                <div className="text-xs font-bold text-slate-800">@{attrName}</div>
                {textContent && (
                  <div className="mt-1">
                    <p className="text-[11px] leading-5 text-slate-600 whitespace-pre-wrap">
                      {textPreview}
                      {hasMoreText ? '…' : ''}
                    </p>
                    {hasMoreText && (
                      <details className="mt-1 text-[11px]">
                        <summary className="cursor-pointer font-semibold text-slate-700 hover:underline">
                          Show full guidance
                        </summary>
                        <div className="mt-1 whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50/60 p-2 leading-5 text-slate-700">
                          {textContent}
                        </div>
                      </details>
                    )}
                  </div>
                )}
                {values.length > 0 && (
                  <div className="mt-2">
                    <span className="text-[10px] font-semibold uppercase text-slate-500">Valid values</span>
                    <div className="mt-0.5 text-[11px] text-slate-600">
                      {values.slice(0, 8).join(', ')}
                      {values.length > 8 ? `, +${values.length - 8} more` : ''}
                    </div>
                  </div>
                )}
                {elements.length > 0 && (
                  <div className="mt-1.5">
                    <span className="text-[10px] font-semibold uppercase text-slate-500">Supported on</span>
                    <div className="mt-0.5 text-[11px] text-slate-600">
                      {elements.slice(0, 8).join(', ')}
                      {elements.length > 8 ? `, +${elements.length - 8} more` : ''}
                    </div>
                  </div>
                )}
                {usageContexts.length > 0 && (
                  <div className="mt-2">
                    <span className="text-[10px] font-semibold uppercase text-slate-500">Used for</span>
                    <ul className="mt-1 space-y-1 text-[11px] text-slate-600">
                      {usageContexts.slice(0, 2).map((context) => (
                        <li key={context} className="flex gap-1.5">
                          <span className="mt-1 h-1.5 w-1.5 rounded-full bg-slate-300" />
                          <span>{context}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {commonMistakes.length > 0 && (
                  <div className="mt-2 rounded-md border border-amber-200 bg-amber-50/80 px-2 py-1.5">
                    <span className="text-[10px] font-semibold uppercase text-amber-700">Watch out</span>
                    <p className="mt-0.5 text-[11px] leading-5 text-amber-900">
                      {commonMistakes[0]}
                    </p>
                  </div>
                )}
                {examples.length > 0 && (
                  <details className="mt-2 text-[11px]">
                    <summary className="cursor-pointer font-semibold text-slate-700 hover:underline">
                      Show example
                    </summary>
                    <pre className="mt-1.5 overflow-auto rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-[10px] leading-4 text-slate-700">
                      {examples[0]}
                    </pre>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }
  if ((name === 'lookup_dita_attribute' || name === 'lookup_dita_spec') && r.attribute_name) {
    const attrName = r.attribute_name as string;
    const values = (r.all_valid_values as string[]) || [];
    const elements = (r.supported_elements as string[]) || [];
    const combos = (r.combination_attributes as string[]) || [];
    const scenarios = (r.default_scenarios as string[]) || [];
    const usageContexts = (r.usage_contexts as string[]) || [];
    const commonMistakes = (r.common_mistakes as string[]) || [];
    const examples = (r.correct_examples as string[]) || [];
    const textContent = String(r.text_content || '').trim();
    const textPreview = textContent.slice(0, 320);
    const hasMoreText = textContent.length > 320;
    return (
      <div className="rounded-xl border border-slate-300/80 bg-slate-50/50 p-3 shadow-sm">
        <div className="mb-2 flex items-center gap-2">
          <div className="text-sm font-bold text-slate-800">@{attrName}</div>
          {name === 'lookup_dita_spec' && (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-700">
              via spec lookup
            </span>
          )}
        </div>
        {textContent && (
          <div className="mb-2">
            <p className="text-xs leading-5 text-slate-700 whitespace-pre-wrap">
              {textPreview}
              {hasMoreText ? '…' : ''}
            </p>
            {hasMoreText && (
              <details className="mt-1 text-xs">
                <summary className="cursor-pointer font-semibold text-slate-700 hover:underline">
                  Show full guidance
                </summary>
                <div className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white/90 p-2 text-[11px] leading-5 text-slate-700">
                  {textContent}
                </div>
              </details>
            )}
          </div>
        )}
        {values.length > 0 && (
          <div className="mb-1.5">
            <span className="text-[10px] font-semibold text-slate-500 uppercase">Valid values</span>
            <div className="flex flex-wrap gap-1 mt-0.5">
              {values.slice(0, 20).map((v, i) => (
                <span key={i} className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[11px] font-mono">{v}</span>
              ))}
              {values.length > 20 && <span className="text-[10px] text-slate-400">+{values.length - 20} more</span>}
            </div>
          </div>
        )}
        {elements.length > 0 && (
          <div className="mb-1.5">
            <span className="text-[10px] font-semibold text-slate-500 uppercase">Supported on</span>
            <div className="text-xs text-slate-600 mt-0.5">{elements.slice(0, 15).join(', ')}{elements.length > 15 ? `, +${elements.length - 15} more` : ''}</div>
          </div>
        )}
        {combos.length > 0 && (
          <div className="mb-1.5">
            <span className="text-[10px] font-semibold text-slate-500 uppercase">Combines with</span>
            <div className="text-xs text-slate-600 mt-0.5">{combos.join(', ')}</div>
          </div>
        )}
        {usageContexts.length > 0 && (
          <div className="mb-1.5">
            <span className="text-[10px] font-semibold text-slate-500 uppercase">Used for</span>
            <ul className="mt-1 space-y-1 text-xs text-slate-600">
              {usageContexts.slice(0, 3).map((context) => (
                <li key={context} className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-slate-300" />
                  <span>{context}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {scenarios.length > 0 && (
          <div>
            <span className="text-[10px] font-semibold text-slate-500 uppercase">Typical scenarios</span>
            <div className="mt-0.5 text-xs text-slate-600">
              {scenarios.slice(0, 3).join(' | ')}
            </div>
          </div>
        )}
        {commonMistakes.length > 0 && (
          <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50/90 px-2.5 py-2">
            <div className="text-[10px] font-semibold uppercase text-amber-700">Watch out</div>
            <ul className="mt-1 space-y-1 text-xs leading-5 text-amber-900">
              {commonMistakes.slice(0, 2).map((mistake) => (
                <li key={mistake} className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-amber-500" />
                  <span>{mistake}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {examples.length > 0 && (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer font-semibold text-slate-700 hover:underline">Show example</summary>
            <pre className="mt-1.5 max-h-56 overflow-auto rounded-lg border border-slate-200 bg-white/90 p-2 text-[11px] leading-5 text-slate-700">
              {examples[0]}
            </pre>
          </details>
        )}
      </div>
    );
  }
  if (name === 'lookup_dita_spec' && r.element_name) {
    const elementName = String(r.element_name || '').trim();
    const queryType = String(r.query_type || '').trim();
    const contentModelSummary = String(r.content_model_summary || '').trim();
    const placementSummary = String(r.placement_summary || '').trim();
    const allowedChildren = Array.isArray(r.allowed_children) ? (r.allowed_children as string[]) : [];
    const parentElements = Array.isArray(r.parent_elements) ? (r.parent_elements as string[]) : [];
    const supportedAttributes = Array.isArray(r.supported_attributes) ? (r.supported_attributes as string[]) : [];
    const textContent = String(r.text_content || '').trim();
    const textPreview = textContent.slice(0, 320);
    const hasMoreText = textContent.length > 320;
    const sources = Array.isArray(r.sources)
      ? (r.sources as Array<Record<string, unknown>>).filter((item) => item && typeof item === 'object')
      : [];
    return (
      <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <div className="text-sm font-bold text-teal-900">{`<${elementName}>`}</div>
          <span className="rounded bg-teal-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-800">
            {queryType === 'content_model' ? 'content model' : queryType === 'placement' ? 'placement' : 'element'}
          </span>
        </div>
        <ToolLead result={r} />
        {(contentModelSummary || placementSummary) && (
          <div className="mb-2 rounded-lg border border-teal-100 bg-white/80 px-2.5 py-2 text-xs leading-5 text-slate-700">
            {contentModelSummary || placementSummary}
          </div>
        )}
        {allowedChildren.length > 0 && (
          <div className="mb-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-700">
              Allowed children
            </div>
            <div className="flex flex-wrap gap-1.5">
              {allowedChildren.slice(0, 12).map((child) => (
                <span
                  key={child}
                  className="rounded-full border border-teal-200 bg-white/90 px-2 py-0.5 text-[11px] font-medium text-teal-900"
                >
                  {child}
                </span>
              ))}
            </div>
          </div>
        )}
        {parentElements.length > 0 && (
          <div className="mb-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-700">
              Can appear inside
            </div>
            <div className="text-xs text-slate-600">{parentElements.slice(0, 12).join(', ')}</div>
          </div>
        )}
        {supportedAttributes.length > 0 && (
          <div className="mb-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-700">
              Common attributes
            </div>
            <div className="text-xs text-slate-600">{supportedAttributes.slice(0, 12).join(', ')}</div>
          </div>
        )}
        {textContent && (
          <div className="mb-2">
            <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-700">
              Spec excerpt
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-700 whitespace-pre-wrap">
              {textPreview}
              {hasMoreText ? '…' : ''}
            </p>
            {hasMoreText && (
              <details className="mt-1 text-xs">
                <summary className="cursor-pointer font-semibold text-teal-800 hover:underline">
                  Show full excerpt
                </summary>
                <div className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-teal-100 bg-white/90 p-2 text-[11px] leading-5 text-slate-700">
                  {textContent}
                </div>
              </details>
            )}
          </div>
        )}
        {sources.length > 0 && (
          <div className="border-t border-teal-100 pt-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-700">
              Sources
            </div>
            <div className="space-y-1.5">
              {sources.slice(0, 4).map((source, index) => {
                const label = String(source.label || source.title || source.url || source.uri || '').trim();
                const url = String(source.url || source.uri || '').trim();
                const snippet = String(source.snippet || '').trim();
                return url ? (
                  <a
                    key={`${label}-${index}`}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-[11px] text-teal-800 hover:underline"
                  >
                    <span className="font-medium">{label || url}</span>
                    {snippet && <span className="block text-slate-500">{snippet}</span>}
                  </a>
                ) : (
                  <div key={`${label}-${index}`} className="text-[11px] text-slate-700">
                    <span className="font-medium">{label}</span>
                    {snippet && <span className="block text-slate-500">{snippet}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }
  // list_indexed_pdfs — PDF knowledge base card
  if (name === 'list_indexed_pdfs') {
    const docs = (r.documents as Array<Record<string, unknown>>) || [];
    if (docs.length === 0) {
      return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
          {r.message ? String(r.message) : 'No PDFs indexed.'}
        </div>
      );
    }
    return (
      <div className="rounded-xl border border-rose-200/80 bg-rose-50/50 p-3 shadow-sm">
        <div className="text-xs font-medium text-rose-800 mb-2">
          {docs.length} indexed PDF{docs.length !== 1 ? 's' : ''}
        </div>
        <ToolLead result={r} />
        <div className="space-y-1.5 max-h-40 overflow-auto">
          {docs.map((d, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[10px] font-medium">{String(d.doc_type || 'pdf')}</span>
              <span className="font-medium text-slate-700 truncate flex-1">{String(d.label || d.filename)}</span>
              <span className="text-slate-400 text-[10px]">{String(d.chunks || 0)} chunks</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  // generate_native_pdf_config — PDF config guidance card
  if (name === 'generate_native_pdf_config') {
    const seeds = (r.seed_results as Array<Record<string, unknown>>) || [];
    const docs = (r.doc_results as Array<Record<string, unknown>>) || [];
    const normalizedSources = ((r.sources as Array<Record<string, unknown>>) || []).filter(Boolean);
    const evidence = (((r.evidence as Array<Record<string, unknown>>) || docs).filter(Boolean).length > 0
      ? (((r.evidence as Array<Record<string, unknown>>) || docs).filter(Boolean))
      : normalizedSources);
    const cfgType = String(r.config_type || '').trim();
    const configArea = String(r.config_area || '').trim();
    const shortAnswer = String(r.short_answer || r.summary || '').trim();
    const recommendedActions = ((r.recommended_actions as unknown[]) || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    const relevantSettings = ((r.relevant_settings as unknown[]) || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    const snippets = ((r.xml_or_css_snippets as unknown[]) || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    const commonMistakes = ((r.common_mistakes as unknown[]) || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    const warnings = ((r.warnings as unknown[]) || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    const seedSignals = ((r.seed_signals as unknown[]) || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    const hasStructuredGuidance =
      Boolean(shortAnswer) ||
      recommendedActions.length > 0 ||
      relevantSettings.length > 0 ||
      snippets.length > 0 ||
      commonMistakes.length > 0 ||
      evidence.length > 0 ||
      warnings.length > 0;

    if (hasStructuredGuidance) {
      return (
        <div className="rounded-2xl border border-orange-200/80 bg-gradient-to-br from-orange-50 via-amber-50/80 to-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-orange-900">Native PDF Configuration</div>
            {configArea && (
              <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-orange-700">
                {configArea.replace(/_/g, ' ')}
              </span>
            )}
            {!configArea && cfgType && (
              <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-orange-700">
                {cfgType.replace(/_/g, ' ')}
              </span>
            )}
          </div>

          {shortAnswer && (
            <p className="mb-3 text-sm leading-6 text-slate-700">
              {shortAnswer}
            </p>
          )}

          {recommendedActions.length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-orange-600">
                Recommended actions
              </div>
              <ul className="space-y-1 text-xs text-slate-700">
                {recommendedActions.slice(0, 4).map((action, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-orange-400" />
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {relevantSettings.length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-orange-600">
                Relevant settings
              </div>
              <div className="flex flex-wrap gap-1.5">
                {relevantSettings.slice(0, 6).map((setting) => (
                  <span
                    key={setting}
                    className="rounded-full border border-orange-200 bg-white/80 px-2.5 py-1 text-[11px] font-medium text-orange-800"
                  >
                    {setting}
                  </span>
                ))}
              </div>
            </div>
          )}

          {snippets.length > 0 && (
            <div className="mb-3 space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-orange-600">
                Example snippet
              </div>
              {snippets.slice(0, 2).map((snippet, i) => (
                <pre
                  key={i}
                  className="overflow-auto rounded-xl border border-orange-100 bg-white/90 p-3 text-[11px] leading-5 text-slate-800"
                >
                  {snippet}
                </pre>
              ))}
            </div>
          )}

          {commonMistakes.length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-orange-600">
                Common mistakes
              </div>
              <ul className="space-y-1 text-xs text-slate-700">
                {commonMistakes.slice(0, 3).map((mistake, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-amber-500" />
                    <span>{mistake}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {warnings.length > 0 && (
            <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs text-amber-900">
              {warnings[0]}
            </div>
          )}

          {(evidence.length > 0 || seedSignals.length > 0 || seeds.length > 0) && (
            <div className="border-t border-orange-100 pt-3">
              {evidence.length > 0 && (
                <>
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-orange-600">
                    Sources
                  </div>
                  <div className="space-y-1.5">
                    {evidence.slice(0, 3).map((doc, i) => (
                      <a
                        key={i}
                        href={String(doc.url || doc.uri || '')}
                        target="_blank"
                        rel="noreferrer"
                        className="block text-xs text-orange-700 hover:underline"
                      >
                        {String(doc.title || doc.label || doc.url || doc.uri).slice(0, 100)}
                        {String(doc.snippet || '').trim() && (
                          <span className="mt-0.5 block text-[11px] text-slate-500">
                            {String(doc.snippet).slice(0, 160)}
                          </span>
                        )}
                      </a>
                    ))}
                  </div>
                </>
              )}
              {seedSignals.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {seedSignals.slice(0, 5).map((signal) => (
                    <span
                      key={signal}
                      className="rounded-full bg-orange-100/80 px-2 py-0.5 text-[10px] font-medium text-orange-700"
                    >
                      {signal}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      );
    }

    if (seeds.length > 0 || docs.length > 0) {
      return (
        <div className="rounded-xl border border-orange-200/80 bg-orange-50/50 p-3 shadow-sm">
          <div className="mb-2 flex items-center gap-2">
            <div className="text-xs font-medium text-orange-800">Native PDF Configuration</div>
            {cfgType && (
              <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-medium text-orange-700">
                {cfgType.replace('_', ' ')}
              </span>
            )}
          </div>
          <div className="space-y-1 text-xs">
            {seeds.slice(0, 3).map((s, i) => (
              <div key={i} className="text-slate-600">
                <span className="font-mono text-orange-700">{String(s.element_name)}</span>
              </div>
            ))}
            {docs.length > 0 && (
              <div className="mt-1.5 border-t border-orange-100 pt-1.5">
                {docs.slice(0, 3).map((d, i) => (
                  <a key={i} href={String(d.url)} target="_blank" rel="noreferrer"
                     className="block text-xs text-orange-700 hover:underline">
                    {String(d.title || d.url).slice(0, 80)}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      );
    }
  }
  // browse_dataset — dataset structure or file content
  if (name === 'browse_dataset') {
    // File content mode
    if (r.file_path && r.content) {
      return (
        <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-teal-900">{String(r.file_path).split('/').pop()}</span>
            {r.truncated && <span className="text-[10px] text-amber-600">(truncated)</span>}
            <span className="text-[10px] text-slate-400">{String(r.size_bytes)} bytes</span>
          </div>
          <ToolLead result={r} />
          <pre className="max-h-48 overflow-auto rounded-lg bg-white border border-teal-100 p-2 text-[11px] font-mono whitespace-pre-wrap">
            {String(r.content).slice(0, 3000)}
          </pre>
        </div>
      );
    }
    // Structure mode
    const files = (r.files as string[]) || [];
    const totalFiles = (r.total_files as number) || files.length;
    const totalDirs = (r.total_directories as number) || 0;
    return (
      <div className="rounded-xl border border-teal-200/80 bg-teal-50/50 p-3 shadow-sm">
        <div className="text-xs font-medium text-teal-900 mb-2">
          Dataset: {totalFiles} file{totalFiles !== 1 ? 's' : ''}, {totalDirs} director{totalDirs !== 1 ? 'ies' : 'y'}
        </div>
        <ToolLead result={r} />
        <div className="max-h-40 overflow-auto text-[11px] font-mono text-slate-600 space-y-0.5">
          {files.slice(0, 30).map((f, i) => (
            <div key={i} className="truncate">{String(f)}</div>
          ))}
          {files.length > 30 && (
            <div className="text-slate-400 italic">...and {totalFiles - 30} more files</div>
          )}
        </div>
      </div>
    );
  }
  const genericMeta = extractToolDisplayMeta(name, r);
  if (genericMeta && KNOWN_FIRST_PARTY_TOOLS.has(name)) {
    const toneClass =
      genericMeta.status === 'error'
        ? 'border-red-200/80 bg-red-50/80'
        : genericMeta.status === 'warning'
          ? 'border-amber-200/80 bg-amber-50/80'
          : 'border-slate-200/80 bg-slate-50/80';
    const badgeClass =
      genericMeta.status === 'error'
        ? 'bg-red-100 text-red-700'
        : genericMeta.status === 'warning'
          ? 'bg-amber-100 text-amber-700'
          : 'bg-teal-100 text-teal-800';
    return (
      <div className={cn('rounded-xl border p-3 shadow-sm', toneClass)}>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <div className="text-xs font-semibold text-slate-800">{genericMeta.title}</div>
          <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]', badgeClass)}>
            {genericMeta.kind}
          </span>
        </div>
        {genericMeta.summary && (
          <p className="text-xs leading-5 text-slate-700">{genericMeta.summary}</p>
        )}
        {genericMeta.warnings.length > 0 && (
          <div className="mt-2 space-y-1">
            {genericMeta.warnings.slice(0, 2).map((warning) => (
              <div
                key={warning}
                className="rounded-lg border border-amber-200 bg-white/80 px-2.5 py-1.5 text-[11px] text-amber-900"
              >
                {warning}
              </div>
            ))}
          </div>
        )}
        {genericMeta.sources.length > 0 && (
          <div className="mt-3 border-t border-slate-200/70 pt-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
              Sources
            </div>
            <div className="space-y-1.5">
              {genericMeta.sources.slice(0, 4).map((source, index) => {
                const label = String(source.label || source.title || source.url || source.uri || '').trim();
                const url = String(source.url || source.uri || '').trim();
                const snippet = String(source.snippet || '').trim();
                return url ? (
                  <a
                    key={`${label}-${index}`}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-[11px] text-slate-700 hover:text-slate-900 hover:underline"
                  >
                    <span className="font-medium">{label || url}</span>
                    {snippet && <span className="block text-slate-500">{snippet}</span>}
                  </a>
                ) : (
                  <div key={`${label}-${index}`} className="text-[11px] text-slate-700">
                    <span className="font-medium">{label}</span>
                    {snippet && <span className="block text-slate-500">{snippet}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }
  if (KNOWN_FIRST_PARTY_TOOLS.has(name)) {
    return (
      <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 p-3 text-xs text-slate-600 shadow-sm">
        <div className="font-semibold text-slate-800">{name.replace(/_/g, ' ')}</div>
        <p className="mt-1">This tool ran, but it did not return a normalized summary yet.</p>
      </div>
    );
  }
  // Default: JSON fallback
  return (
    <pre className="max-h-24 overflow-auto rounded-lg border border-slate-200 bg-slate-50/90 p-2 text-xs">
      {JSON.stringify(r, null, 2)}
    </pre>
  );
}

function AttachmentMetadataPanel({ attachments }: { attachments: ChatAttachmentMeta[] }) {
  if (!Array.isArray(attachments) || attachments.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 shadow-sm">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
        Attached assets
      </div>
      <div className="space-y-2">
        {attachments.map((attachment, index) => {
          const isImage = attachment.kind === 'image';
          return (
            <div
              key={`${attachment.filename}-${index}`}
              className={cn(
                'flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs',
                isImage ? 'border-teal-200 bg-teal-50 text-teal-900' : 'border-slate-300 bg-slate-50 text-slate-900'
              )}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {isImage ? <ImageIcon className="h-3.5 w-3.5" /> : <FileCode2 className="h-3.5 w-3.5" />}
                  <span className="truncate font-medium">{attachment.filename}</span>
                </div>
                <p className="mt-1 text-[11px] opacity-80">
                  {attachment.kind.replace(/_/g, ' ')}
                  {attachment.mime_type ? ` · ${attachment.mime_type}` : ''}
                  {attachment.size_bytes ? ` · ${formatBytes(attachment.size_bytes)}` : ''}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GenerationOptionsPanel({ options }: { options: ChatDitaGenerationOptions }) {
  const pills = [
    options.dita_type ? `type: ${options.dita_type}` : '',
    options.style_strictness ? `style: ${options.style_strictness}` : '',
    options.output_mode ? `output: ${options.output_mode}` : '',
    options.file_name ? `file: ${options.file_name}` : '',
    options.save_path ? `save: ${options.save_path}` : '',
    options.strict_validation === false ? 'strict validation: off' : 'strict validation: on',
    options.preserve_prolog ? 'prolog: on' : '',
    options.xref_placeholders ? 'xref placeholders: on' : '',
    options.auto_ids === false ? 'auto ids: off' : '',
  ].filter(Boolean);

  if (pills.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white/80 p-3 shadow-sm">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
        Generation options
      </div>
      <div className="flex flex-wrap gap-2">
        {pills.map((pill) => (
          <span
            key={pill}
            className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-700"
          >
            {pill}
          </span>
        ))}
      </div>
    </div>
  );
}

function AttachmentAuthoringResultPanel({
  result,
  onRegenerateTopic,
  onRegenerateTopicFallback,
  visualContext,
}: {
  result: ChatDitaAuthoringResult;
  onRegenerateTopic?: (options: ChatDitaGenerationOptions) => void;
  /** When options-based regen is unavailable, header-style regenerate only. */
  onRegenerateTopicFallback?: () => void;
  visualContext?: AuthoringVisualContext | null;
}) {
  const actions = result.actions || [];
  const savedAction = actions.find((action) => action.key === 'saved_to_aem') || null;

  const [xmlDraft, setXmlDraft] = useState(result.xml_preview || '');
  useEffect(() => {
    setXmlDraft(result.xml_preview || '');
  }, [result.xml_preview]);

  return (
    <div className="rounded-xl border border-teal-200/80 bg-gradient-to-br from-teal-50 to-teal-50/70 p-3 shadow-sm sm:p-4">
      {(result.message || result.explanation || savedAction?.description || result.saved_asset_path) && (
        <div className="mb-3 rounded-lg border border-teal-100 bg-white/70 px-3 py-2 text-xs text-slate-700">
          {savedAction?.description && (
            <p>
              <span className="font-semibold text-slate-800">Saved to AEM:</span> {savedAction.description}
            </p>
          )}
          {!savedAction?.description && result.saved_asset_path && (
            <p>
              <span className="font-semibold text-slate-800">Saved path:</span> {result.saved_asset_path}
            </p>
          )}
          {result.message && <p className="mt-1 leading-relaxed">{result.message}</p>}
          {result.explanation && <p className="mt-1 leading-relaxed text-slate-600">{result.explanation}</p>}
        </div>
      )}

      <AuthoringGenerationSplitReview
        result={result}
        visualContext={visualContext}
        xmlDraft={xmlDraft}
        onXmlDraftChange={setXmlDraft}
        onRegenerateTopic={onRegenerateTopic}
        onRegenerateTopicFallback={onRegenerateTopicFallback}
      />
    </div>
  );
}

function FlowchartResultPanel({ result }: { result: Record<string, unknown> }) {
  const initialPreviewState = Boolean(
    String(result.preview_svg_data_url || '').trim() || String(result.preview_svg || '').trim()
  );
  const [view, setView] = useState<'preview' | 'mermaid'>(
    initialPreviewState ? 'preview' : 'mermaid'
  );
  const [copied, setCopied] = useState(false);

  const title = String(result.title || 'DITA flowchart');
  const mermaid = String(result.mermaid || '');
  const previewUrl = resolveArtifactUrl(String(result.preview_svg_data_url || ''));
  const previewSvg = inferSvgMarkup(result, previewUrl);
  const hasRenderedPreview = Boolean(previewSvg || previewUrl);
  const mermaidDownloadUrl = resolveArtifactUrl(String(result.mermaid_data_url || ''));
  const previewDownloadName = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'dita-flowchart'}.svg`;
  const mermaidDownloadName = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'dita-flowchart'}.mmd`;
  const diagramKind = String(result.diagram_kind || 'diagram');
  const nodeCount = Number(result.node_count || 0);
  const edgeCount = Number(result.edge_count || 0);
  const visibleNodeCount = Number(result.visible_node_count || nodeCount);
  const visibleEdgeCount = Number(result.visible_edge_count || edgeCount);
  const totalNodeCount = Number(result.total_node_count || visibleNodeCount);
  const totalEdgeCount = Number(result.total_edge_count || visibleEdgeCount);
  const omittedNodeCount = Number(result.omitted_node_count || 0);
  const omittedEdgeCount = Number(result.omitted_edge_count || 0);
  const isSimplified = Boolean(result.is_simplified || omittedNodeCount > 0 || omittedEdgeCount > 0);
  const displayMode = String(result.display_mode || (isSimplified ? 'structure_overview' : 'complete_diagram'));
  const previewFocus = String(result.preview_focus || '').trim();
  const structureSummary = String(result.structure_summary || result.summary || '').trim();
  const flowWarnings = coerceToolWarnings(result);
  const legend = Array.isArray(result.legend)
    ? (result.legend as Array<Record<string, unknown>>)
        .map((item) => String(item.label || item.kind || '').trim())
        .filter(Boolean)
    : [];
  const xmlProfile = (result.xml_profile as Record<string, unknown> | undefined) || {};
  const rootElement = String(xmlProfile.root_element || '').trim();
  const elementCount = Number(xmlProfile.element_count || 0);
  const lineCount = Number(xmlProfile.line_count || 0);
  const message = String(result.message || '');

  const handleCopy = async () => {
    if (!mermaid || !navigator.clipboard) return;
    await navigator.clipboard.writeText(mermaid);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <div className="rounded-xl border border-teal-200/80 bg-gradient-to-br from-teal-50 to-teal-50/80 p-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-teal-200 bg-white/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-teal-800">
              {isSimplified ? 'Structure overview' : 'XML flowchart'}
            </span>
            <span className="text-xs text-teal-800/80">{diagramKind}</span>
            <span className="text-xs text-slate-500">
              {visibleNodeCount === totalNodeCount ? `${visibleNodeCount} nodes` : `${visibleNodeCount} of ${totalNodeCount} nodes`}
            </span>
            <span className="text-xs text-slate-500">
              {visibleEdgeCount === totalEdgeCount ? `${visibleEdgeCount} edges` : `${visibleEdgeCount} of ${totalEdgeCount} edges`}
            </span>
            {displayMode && (
              <span className="text-xs text-slate-500">{displayMode.replace(/_/g, ' ')}</span>
            )}
          </div>
          <p className="mt-2 text-sm font-semibold text-slate-900">{title}</p>
          {(structureSummary || message) && (
            <p className="mt-1 text-xs leading-relaxed text-slate-600">{structureSummary || message}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {hasRenderedPreview ? (
            <Button
              type="button"
              variant={view === 'preview' ? 'default' : 'outline'}
              size="sm"
              className="h-8"
              onClick={() => setView('preview')}
            >
              <ImageIcon className="mr-1.5 h-3.5 w-3.5" />
              Rendered SVG
            </Button>
          ) : (
            <span className="inline-flex h-8 items-center rounded-lg border border-amber-200 bg-amber-50 px-3 text-xs font-medium text-amber-800">
              SVG preview unavailable
            </span>
          )}
          <Button
            type="button"
            variant={view === 'mermaid' ? 'default' : 'outline'}
            size="sm"
            className="h-8"
            onClick={() => setView('mermaid')}
          >
            <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
            Mermaid source
          </Button>
        </div>
      </div>

      {(flowWarnings.length > 0 || previewFocus || rootElement || legend.length > 0) && (
        <div className="mt-3 rounded-xl border border-white/70 bg-white/75 p-3 text-xs text-slate-700">
          {previewFocus && (
            <p>
              <span className="font-semibold text-slate-900">Preview focus:</span> {previewFocus}
            </p>
          )}
          {(rootElement || elementCount > 0 || lineCount > 0) && (
            <p className="mt-1 text-slate-600">
              {[rootElement ? `Root: <${rootElement}>` : '', elementCount > 0 ? `${elementCount} elements` : '', lineCount > 0 ? `${lineCount} lines` : '']
                .filter(Boolean)
                .join(' | ')}
            </p>
          )}
          {legend.length > 0 && (
            <p className="mt-1 text-slate-500">Legend: {legend.slice(0, 6).join(', ')}</p>
          )}
          {flowWarnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {flowWarnings.slice(0, 3).map((warning) => (
                <p key={warning} className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-amber-900">
                  {warning}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 rounded-xl border border-white/70 bg-white/80 p-3">
        {view === 'preview' && hasRenderedPreview ? (
          <div className="space-y-3">
            {previewSvg ? (
              <InlineSvgPreview
                svg={previewSvg}
                title={`${title} flowchart preview`}
                className="max-h-[30rem] border-teal-100"
              />
            ) : (
              <img
                src={previewUrl}
                alt={`${title} flowchart preview`}
                className="max-h-[28rem] w-full rounded-lg border border-teal-100 bg-white object-contain"
              />
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={handleCopy} disabled={!mermaid}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                {copied ? 'Copied' : 'Copy Mermaid'}
              </Button>
              {mermaidDownloadUrl && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => downloadArtifact(mermaidDownloadUrl, mermaidDownloadName)}
                >
                  <Download className="mr-1.5 h-3.5 w-3.5" />
                  Download .mmd
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => downloadArtifact(previewUrl, previewDownloadName)}
              >
                <Download className="mr-1.5 h-3.5 w-3.5" />
                Download SVG
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {!hasRenderedPreview && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                This result did not include a rendered SVG preview. The Mermaid source below is still available.
              </div>
            )}
            <pre className="max-h-80 overflow-auto rounded-lg border border-slate-200 bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-300">
              {mermaid || 'No Mermaid source was returned.'}
            </pre>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={handleCopy} disabled={!mermaid}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                {copied ? 'Copied' : 'Copy Mermaid'}
              </Button>
              {mermaidDownloadUrl && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => downloadArtifact(mermaidDownloadUrl, mermaidDownloadName)}
                >
                  <Download className="mr-1.5 h-3.5 w-3.5" />
                  Download .mmd
                </Button>
              )}
              {hasRenderedPreview && (
                <Button type="button" variant="outline" size="sm" onClick={() => setView('preview')}>
                  <ImageIcon className="mr-1.5 h-3.5 w-3.5" />
                  Show rendered SVG
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ImageGenerationPanel({ result }: { result: Record<string, unknown> }) {
  const artifacts = Array.isArray(result.artifacts)
    ? (result.artifacts as Array<Record<string, unknown>>)
    : [];
  const provider = String(result.provider || 'unknown');
  const model = String(result.model || '');
  const warning = String(result.warning || '');
  const message = String(result.message || '');
  const style = String(result.style || '');

  return (
    <div className="rounded-xl border border-teal-200/80 bg-gradient-to-br from-teal-50 to-slate-50/90 p-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-teal-200 bg-white/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-teal-800">
              Image generation
            </span>
            <span className="text-xs text-teal-800/80">{provider}</span>
            {model && <span className="text-xs text-slate-500">{model}</span>}
            <span className="text-xs text-slate-500">{artifacts.length} artifact{artifacts.length === 1 ? '' : 's'}</span>
          </div>
          {message && <p className="mt-2 text-sm font-medium text-slate-900">{message}</p>}
          {style && <p className="mt-1 text-xs text-slate-500">Style: {style}</p>}
        </div>
      </div>

      {warning && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900">
          {warning}
        </p>
      )}

      {artifacts.length > 0 ? (
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {artifacts.map((artifact, index) => {
            const href = resolveArtifactUrl(
              String(artifact.data_url || artifact.url || artifact.thumbnail_url || '')
            );
            const inlineSvg = inferSvgMarkup(artifact, href);
            const isSvg = String(artifact.mime_type || '').toLowerCase().includes('svg');
            const title = String(
              artifact.title || artifact.download_name || `Generated image ${index + 1}`
            );
            const downloadName = String(artifact.download_name || `chat-image-${index + 1}`);
            const width = typeof artifact.width === 'number' ? artifact.width : null;
            const height = typeof artifact.height === 'number' ? artifact.height : null;
            const dimensions =
              width && height
                ? `${String(width)} x ${String(height)}`
                : '';
            return (
              <div key={String(artifact.id || index)} className="rounded-xl border border-white/70 bg-white/80 p-3 shadow-sm">
                <div className="overflow-hidden rounded-lg border border-teal-100 bg-slate-100">
                  {inlineSvg ? (
                    <InlineSvgPreview
                      svg={inlineSvg}
                      title={title}
                      className="h-64 border-teal-100"
                    />
                  ) : href ? (
                    <img src={href} alt={title} className="h-64 w-full object-contain" />
                  ) : (
                    <div className="flex h-64 items-center justify-center text-sm text-slate-500">
                      Preview unavailable
                    </div>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">{title}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {[String(artifact.mime_type || ''), dimensions, isSvg ? 'inline preview ready' : ''].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                  {href && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => downloadArtifact(href, downloadName)}
                    >
                      <Download className="mr-1.5 h-3.5 w-3.5" />
                      Download
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white/80 px-3 py-3 text-sm text-slate-500">
          No image artifacts were returned.
        </div>
      )}
    </div>
  );
}

function AgentPlanPanel({ plan }: { plan: ChatAgentPlan }) {
  const steps = plan.steps ?? [];
  const requiresApproval = Boolean(plan.requires_approval);
  const preview = plan.preview as ChatGenerateDitaPreview | undefined;
  const friendlyGoal =
    plan.mode === 'generate_dita_preview'
      ? plan.status === 'clarification_required'
        ? 'I mapped your request into a DITA bundle, but I still need one detail from you.'
        : 'I mapped your request into a DITA bundle and it is ready for review.'
      : plan.goal;
  const clarificationOptions =
    Array.isArray(preview?.clarification_request?.options) && preview?.clarification_request?.options.length > 0
      ? preview.clarification_request.options
      : [];
  return (
    <div className="rounded-xl border border-teal-200/80 bg-gradient-to-br from-teal-50 to-teal-50/80 p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-teal-200 bg-white/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-teal-800">
          Preview
        </span>
        <span className="text-xs text-teal-800/80">
          {plan.status === 'clarification_required'
            ? 'waiting for one reply'
            : plan.mode === 'generate_dita_preview'
              ? 'ready to review'
              : plan.mode?.replace('_', ' ') || 'multi step'}
        </span>
      </div>
      <p className="mt-2 text-sm font-medium leading-6 text-slate-800">{friendlyGoal}</p>
      {Array.isArray(plan.expected_outputs) && plan.expected_outputs.length > 0 && (
        <div className="mt-3 rounded-lg border border-white/70 bg-white/70 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Expected output</p>
          <ul className="mt-1 space-y-1 text-xs text-slate-600">
            {plan.expected_outputs.slice(0, 4).map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
      )}
      {preview && (
        <div className="mt-3 rounded-lg border border-white/70 bg-white/80 px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">What I understood</p>
            {preview.bundle_type && (
              <span className="rounded-full border border-teal-100 bg-teal-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-teal-800">
                {preview.bundle_type.replace(/_/g, ' ')}
              </span>
            )}
          </div>
          {preview.summary && <p className="mt-2 text-sm text-slate-800">{preview.summary}</p>}
          {(preview.subject || preview.topic_family || preview.include_map || preview.content_mode || preview.glossary_usage_mode) && (
            <div className="mt-3 grid gap-2 text-xs text-slate-700 md:grid-cols-3">
              {preview.subject && (
                <div className="rounded-lg border border-white/80 bg-slate-50/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Subject</p>
                  <p className="mt-1">{preview.subject}</p>
                </div>
              )}
              {preview.topic_family && (
                <div className="rounded-lg border border-white/80 bg-slate-50/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Topic family</p>
                  <p className="mt-1">{preview.topic_family}</p>
                </div>
              )}
              <div className="rounded-lg border border-white/80 bg-slate-50/80 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Map included</p>
                <p className="mt-1">{preview.include_map ? 'Yes' : 'No'}</p>
              </div>
              {preview.content_mode && (
                <div className="rounded-lg border border-white/80 bg-slate-50/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Content mode</p>
                  <p className="mt-1">{String(preview.content_mode).replace(/_/g, ' ')}</p>
                </div>
              )}
              {preview.glossary_usage_mode && preview.glossary_usage_mode !== 'standalone' && (
                <div className="rounded-lg border border-white/80 bg-slate-50/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Glossary linkage</p>
                  <p className="mt-1">{String(preview.glossary_usage_mode).replace(/_/g, ' ')}</p>
                </div>
              )}
            </div>
          )}
          {preview.family_decision && (
            <div className="mt-3 rounded-lg border border-teal-100 bg-teal-50/70 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-teal-900">Family decision</p>
              <div className="mt-1 grid gap-2 text-xs text-teal-950 md:grid-cols-3">
                {preview.family_decision.requested && <p>Requested: {preview.family_decision.requested}</p>}
                {preview.family_decision.inferred && <p>Inferred: {preview.family_decision.inferred}</p>}
                {preview.family_decision.resolved && <p>Resolved: {preview.family_decision.resolved}</p>}
              </div>
              {preview.family_decision.reason && (
                <p className="mt-2 text-xs text-teal-900">{preview.family_decision.reason}</p>
              )}
            </div>
          )}
          {Array.isArray(preview.artifacts) && preview.artifacts.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Planned artifacts</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {preview.artifacts.map((artifact, index) => (
                  <li key={`${artifact.label || artifact.kind || 'artifact'}-${index}`}>- {artifact.label || artifact.kind}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.required_elements) && preview.required_elements.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Required DITA tags</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {preview.required_elements.map((item) => (
                  <li key={`elt-${item.name}`}>- &lt;{item.name}&gt; {item.scope ? `(${item.scope})` : ''}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.required_attributes) && preview.required_attributes.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Required attributes</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {preview.required_attributes.map((item) => (
                  <li key={`attr-${item.attribute_name}`}>
                    - @{item.attribute_name}
                    {Array.isArray(item.required_values) && item.required_values.length > 0
                      ? `="${item.required_values.join(' ')}"`
                      : ''}
                    {item.scope ? ` (${item.scope})` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.required_metadata) && preview.required_metadata.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Required prolog metadata</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {preview.required_metadata.map((item) => (
                  <li key={`meta-${item.field_name}`}>
                    - {item.field_name}
                    {item.value ? `=${item.value}` : ''}
                    {item.scope ? ` (${item.scope})` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.assumptions) && preview.assumptions.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Assumptions</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {preview.assumptions.map((item) => (
                  <li key={item}>- {item}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.influence_inputs) && preview.influence_inputs.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Influenced by</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {preview.influence_inputs.map((item) => (
                  <li key={item}>- {item.replace(/_/g, ' ')}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.warnings) && preview.warnings.length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/90 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-amber-800">Warnings</p>
              <ul className="mt-1 space-y-1 text-xs text-amber-900">
                {preview.warnings.map((item) => (
                  <li key={item}>- {item}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(preview.conflicts) && preview.conflicts.length > 0 && (
            <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50/90 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-rose-800">Constraint conflicts</p>
              <ul className="mt-1 space-y-1 text-xs text-rose-900">
                {preview.conflicts.map((item, index) => (
                  <li key={`${item.message}-${index}`}>- {item.message}</li>
                ))}
              </ul>
            </div>
          )}
            {preview.clarification_question && (
              <div className="mt-3 rounded-lg border border-slate-300 bg-slate-50/90 px-3 py-2 text-xs text-slate-900">
                <p className="font-semibold uppercase tracking-[0.08em] text-slate-700">One quick detail</p>
                <p className="mt-1">{preview.clarification_question}</p>
                <p className="mt-2 text-[11px] text-slate-800">
                  A short reply is enough. You do not need to repeat the whole request.
                </p>
                {clarificationOptions.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {clarificationOptions.map((option) => (
                      <span
                        key={option}
                        className="rounded-full border border-slate-300 bg-white/80 px-2.5 py-1 text-[11px] font-semibold text-slate-800"
                      >
                        {option}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
        </div>
      )}
      {steps.length > 0 && (
        <div className="mt-3 space-y-2">
          {steps.map((step, index) => {
            const status = String(step.status || 'pending').toLowerCase();
            const gateType = String(step.gate_type || '').toLowerCase();
            const tone =
              status === 'completed'
                ? 'border-teal-200 bg-teal-50/80 text-teal-950'
                : status === 'running'
                  ? 'border-teal-200 bg-teal-50/80 text-teal-950'
                  : status === 'skipped'
                    ? 'border-slate-200 bg-slate-50 text-slate-700'
                    : status === 'failed'
                      ? 'border-red-200 bg-red-50/80 text-red-900'
                      : 'border-slate-200 bg-white/80 text-slate-700';
            return (
                <div key={step.id || `${step.title}-${index}`} className={cn('rounded-lg border px-3 py-2', tone)}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.08em]">Step {index + 1}</span>
                    {step.approval_required && (
                      <span className="rounded-full border border-current/20 bg-white/70 px-2 py-0.5 text-[10px] font-medium uppercase">
                        {gateType === 'review' ? 'Review' : 'Approval'}
                      </span>
                    )}
                    <span className="text-[10px] uppercase tracking-[0.08em] opacity-75">{status.replace('_', ' ')}</span>
                  </div>
                <p className="mt-1 text-sm font-medium">{step.title}</p>
                {step.summary && <p className="mt-1 text-xs opacity-80">{step.summary}</p>}
                {step.note && <p className="mt-1 text-xs opacity-75">Note: {step.note}</p>}
                {step.error && <p className="mt-1 text-xs font-medium">{step.error}</p>}
              </div>
            );
          })}
        </div>
      )}
      {requiresApproval && Array.isArray(plan.resume_tokens) && plan.resume_tokens.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">
          Try: {plan.resume_tokens.join(' or ')}
        </p>
      )}
    </div>
  );
}

function ApprovalStatePanel({ approval }: { approval: ChatApprovalState }) {
  if (!approval.state) return null;
  const pending = approval.state === 'required';
  const review = String(approval.kind || '').toLowerCase() === 'review';
  return (
    <div
      className={cn(
        'rounded-xl border p-3 shadow-sm',
        pending
          ? 'border-amber-200 bg-amber-50/90 text-amber-950'
          : 'border-slate-200 bg-slate-50 text-slate-700'
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-current/20 bg-white/75 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]">
          {pending ? (review ? 'Ready when you are' : 'Waiting for your reply') : approval.state.replace('_', ' ')}
        </span>
        {approval.pending_tool_name && (
          <span className="text-xs opacity-80">Next step: {approval.pending_tool_name.replace(/_/g, ' ')}</span>
        )}
      </div>
        {approval.prompt && <p className="mt-2 text-sm leading-relaxed">{approval.prompt}</p>}
        {pending && (
          <p className="mt-2 text-xs opacity-85">
            A short reply is enough here. You do not need to paste the original request again.
          </p>
        )}
        {Array.isArray(approval.affected_artifacts) && approval.affected_artifacts.length > 0 && (
          <div className="mt-3 rounded-lg border border-white/60 bg-white/70 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em]">Affected artifacts</p>
          <ul className="mt-1 space-y-1 text-xs">
            {approval.affected_artifacts.map((artifact) => (
              <li key={artifact}>- {artifact}</li>
            ))}
          </ul>
        </div>
      )}
        {Array.isArray(approval.allowed_responses) && approval.allowed_responses.length > 0 && (
          <div className="mt-3">
            <p className="text-xs opacity-80">Quick replies</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {approval.allowed_responses.map((response) => (
                <span
                  key={response}
                  className="rounded-full border border-current/20 bg-white/80 px-2.5 py-1 text-[11px] font-semibold"
                >
                  {response}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
}

function AgentExecutionPanel({ execution }: { execution: ChatAgentExecution }) {
  const steps = execution.steps ?? [];
  if (steps.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
          Execution
        </span>
        <span className="text-xs font-medium text-slate-600">Status {execution.status || 'running'}</span>
      </div>
      <div className="mt-3 space-y-2">
        {steps.map((step) => {
          const isCurrent = execution.current_step_id && execution.current_step_id === step.id;
          const status = String(step.status || 'pending').toLowerCase();
          const dotTone =
            status === 'completed'
              ? 'bg-teal-500'
              : status === 'running'
                ? 'bg-teal-500'
                : status === 'failed'
                  ? 'bg-red-500'
                  : status === 'skipped'
                    ? 'bg-slate-400'
                    : 'bg-slate-300';
          return (
            <div key={step.id || step.title} className="flex gap-3 rounded-lg border border-white/70 bg-white/75 px-3 py-2">
              <div className="mt-1 flex flex-col items-center">
                <span className={cn('h-2.5 w-2.5 rounded-full', dotTone)} />
                <span className="mt-1 min-h-4 text-[10px] uppercase tracking-[0.08em] text-slate-400">
                  {isCurrent ? 'Now' : ''}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-slate-800">{step.title}</p>
                  <span className="text-[10px] uppercase tracking-[0.08em] text-slate-400">
                    {status.replace('_', ' ')}
                  </span>
                </div>
                {step.summary && <p className="mt-1 text-xs text-slate-600">{step.summary}</p>}
                {step.note && <p className="mt-1 text-xs text-slate-500">Note: {step.note}</p>}
                {step.error && <p className="mt-1 text-xs font-medium text-red-700">{step.error}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GroundingPanel({ grounding }: { grounding: ChatGrounding }) {
  const status = String(grounding.status || 'partial').toLowerCase();
  const tone =
    status === 'grounded'
      ? 'border-teal-200 bg-teal-50/90 text-teal-950'
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
  const llm = grounding.llm;

  return (
    <div className={cn('rounded-xl border p-3 shadow-sm', tone)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-current/20 bg-white/70 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]">
          {badge}
        </span>
        <span className="text-xs opacity-80">Confidence {Math.round((grounding.confidence ?? 0) * 100)}%</span>
      </div>
      <p className="mt-2 text-sm leading-relaxed">{grounding.reason}</p>
      <LlmUsagePanel llm={llm} className="mt-3 border-white/50 bg-white/60" />
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
