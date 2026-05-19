import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  FileCode2,
  Image as ImageIcon,
  RefreshCw,
  Wrench,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { apiUrl } from '@/utils/api';
import type { ChatDitaAuthoringResult, ChatDitaGenerationOptions, ChatLinkRecommendation } from '@/api/chat';
import {
  splitAuthoringValidation,
  generationOptionPills,
  ditaFileNameFromTitle,
  buildAuthoringGenerationSnapshot,
  summarizeAuthoringGenerationDelta,
  type AuthoringGenerationSnapshot,
} from './authoringResultUtils';
import { AuthoringRegenerateOptions } from './AuthoringRegenerateOptions';

function resolveArtifactUrl(url?: string | null): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  return apiUrl(url);
}

async function downloadArtifact(url: string, filename: string) {
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
}

export interface AuthoringVisualContext {
  screenshotObjectUrl: string | null;
  screenshotFileName?: string | null;
  referenceFileName?: string | null;
  generationOptions?: ChatDitaGenerationOptions | null;
}

export interface AuthoringGenerationSplitReviewProps {
  result: ChatDitaAuthoringResult;
  visualContext?: AuthoringVisualContext | null;
  /** Controlled XML text (preview or user edits). */
  xmlDraft: string;
  onXmlDraftChange: (value: string) => void;
  onRegenerateTopic?: (options: ChatDitaGenerationOptions) => void;
  /** Plain regenerate when options API is not wired (e.g. tests). */
  onRegenerateTopicFallback?: () => void;
}

/**
 * Split-pane generation review: inputs & validation on the left, XML + actions on the right.
 * Stacks on small viewports; expands horizontally on xl+.
 */
export function AuthoringGenerationSplitReview({
  result,
  visualContext,
  xmlDraft,
  onXmlDraftChange,
  onRegenerateTopic,
  onRegenerateTopicFallback,
}: AuthoringGenerationSplitReviewProps) {
  const { validation, blockingIssues, warnings } = useMemo(() => splitAuthoringValidation(result), [result]);
  const [viewMode, setViewMode] = useState<'highlight' | 'source'>('highlight');
  const [copied, setCopied] = useState(false);

  const xmlDisplay = xmlDraft || result.xml_preview || '';
  const pills = useMemo(
    () => generationOptionPills(visualContext?.generationOptions ?? null),
    [visualContext?.generationOptions]
  );

  const prevGenSnapRef = useRef<AuthoringGenerationSnapshot | null>(null);
  const [generationDelta, setGenerationDelta] = useState<{ headline: string; bullets: string[] } | null>(null);

  useEffect(() => {
    const next = buildAuthoringGenerationSnapshot(result, pills);
    const prev = prevGenSnapRef.current;
    if (prev) {
      setGenerationDelta(summarizeAuthoringGenerationDelta(prev, next));
    } else {
      setGenerationDelta(null);
    }
    prevGenSnapRef.current = next;
  }, [result, pills]);

  const semanticSectionNames = useMemo(
    () =>
      (result.semantic_plan?.sections ?? [])
        .map((s) => (typeof s.name === 'string' ? s.name : ''))
        .filter(Boolean),
    [result.semantic_plan?.sections]
  );

  const refSummary = result.reference_summary as Record<string, unknown> | null | undefined;
  const assumptions = (Array.isArray(result.assumptions) ? result.assumptions : []) as string[];
  const linkRecs = (Array.isArray(result.link_recommendations) ? result.link_recommendations : []) as ChatLinkRecommendation[];

  const actions = result.actions || [];
  const openAction = actions.find((a) => a.key === 'open_in_editor' && a.url) || null;

  const handleCopy = useCallback(async () => {
    const text = xmlDisplay.trim();
    if (!text || !navigator.clipboard) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }, [xmlDisplay]);

  const hasErrors = blockingIssues.length > 0 || !validation.valid;

  return (
    <div
      className={cn(
        'flex min-h-[min(85vh,44rem)] w-full min-w-0 flex-col gap-4 rounded-xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50/90 to-teal-50/50 p-3 shadow-sm sm:p-4',
        'xl:flex-row xl:items-stretch xl:gap-0 xl:divide-x xl:divide-emerald-200/60'
      )}
    >
      {/* Left pane */}
      <div className="flex w-full min-w-0 shrink-0 flex-col gap-3 xl:w-[min(100%,22rem)] xl:max-w-sm xl:pr-4">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-800">Generation review</h3>
          <p className="mt-1 text-xs text-slate-600">
            {result.title || 'Generated topic'}{' '}
            <span className="text-slate-400">·</span> {String(result.dita_type || 'topic')}
          </p>
        </div>

        <section className="rounded-lg border border-teal-200/80 bg-white/90 p-2 shadow-sm" aria-labelledby="auth-shot-label">
          <p id="auth-shot-label" className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-teal-950">
            Screenshot
          </p>
          {visualContext?.screenshotObjectUrl ? (
            <div className="overflow-hidden rounded-md border border-slate-200 bg-slate-100">
              <img
                src={visualContext.screenshotObjectUrl}
                alt=""
                className="max-h-48 w-full object-contain object-top"
              />
            </div>
          ) : (
            <div className="flex items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-6">
              <ImageIcon className="h-8 w-8 text-slate-300" aria-hidden />
            </div>
          )}
          <p className="mt-1 truncate text-[11px] text-slate-500" title={visualContext?.screenshotFileName || undefined}>
            {visualContext?.screenshotFileName || 'Thumbnail available for the current browser session only'}
          </p>
        </section>

        <section className="rounded-lg border border-violet-200/80 bg-white/90 p-2 shadow-sm" aria-labelledby="auth-ref-label">
          <p id="auth-ref-label" className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-violet-900">
            Reference topic
          </p>
          {refSummary && Object.keys(refSummary).length > 0 ? (
            <dl className="space-y-1.5 text-[11px] text-slate-700">
              {refSummary.title != null && refSummary.title !== '' && (
                <div>
                  <dt className="font-medium text-slate-500">Title</dt>
                  <dd className="mt-0.5">{String(refSummary.title)}</dd>
                </div>
              )}
              {refSummary.root_type != null && refSummary.root_type !== '' && (
                <div>
                  <dt className="font-medium text-slate-500">Root</dt>
                  <dd className="mt-0.5 font-mono">{String(refSummary.root_type)}</dd>
                </div>
              )}
              {refSummary.structure_summary != null && String(refSummary.structure_summary).trim() !== '' && (
                <div>
                  <dt className="font-medium text-slate-500">Structure</dt>
                  <dd className="mt-0.5 line-clamp-4 text-slate-600">{String(refSummary.structure_summary)}</dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="text-[11px] text-slate-500">No reference topic was attached for this run.</p>
          )}
          {visualContext?.referenceFileName && (
            <p className="mt-2 truncate text-[11px] text-violet-800" title={visualContext.referenceFileName}>
              File: {visualContext.referenceFileName}
            </p>
          )}
        </section>

        {pills.length > 0 && (
          <section className="rounded-lg border border-slate-200 bg-white/90 p-2 shadow-sm">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-600">Options used</p>
            <div className="flex flex-wrap gap-1.5">
              {pills.map((pill) => (
                <span
                  key={pill}
                  className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700"
                >
                  {pill}
                </span>
              ))}
            </div>
          </section>
        )}

        <section
          className={cn(
            'rounded-lg border p-2 shadow-sm',
            hasErrors ? 'border-amber-300 bg-amber-50/95' : 'border-emerald-200 bg-emerald-50/80'
          )}
          role="region"
          aria-label="Validation summary"
        >
          <div className="flex items-start gap-2">
            {hasErrors ? (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
            ) : (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-800">Validation</p>
              <p className="mt-1 text-xs font-medium text-slate-800">
                {validation.valid ? 'Passed — review XML before publishing.' : 'Needs attention before publish.'}
              </p>
              <p className="mt-0.5 text-[11px] capitalize text-slate-600">Status: {result.status}</p>
              {validation.quality_score != null && (
                <p className="text-[11px] text-slate-600">Quality score: {validation.quality_score}</p>
              )}
              {validation.repaired && (
                <p className="text-[11px] text-amber-800">One repair pass was applied server-side.</p>
              )}
            </div>
          </div>
          {blockingIssues.length > 0 && (
            <div className="mt-2 border-t border-amber-200/80 pt-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-red-800">Errors / blocking</p>
              <ul className="mt-1 max-h-32 space-y-1 overflow-y-auto text-[11px] text-red-900" role="list">
                {blockingIssues.map((t, i) => (
                  <li key={`e-${i}`} className="leading-snug">
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {warnings.length > 0 && (
            <div className="mt-2 border-t border-amber-200/60 pt-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-900">Warnings</p>
              <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto text-[11px] text-amber-950/90" role="list">
                {warnings.slice(0, 10).map((t, i) => (
                  <li key={`w-${i}`} className="leading-snug">
                    {t}
                  </li>
                ))}
              </ul>
              {warnings.length > 10 && (
                <p className="mt-1 text-[10px] text-amber-800">+{warnings.length - 10} more on the right</p>
              )}
            </div>
          )}
        </section>

        {result.screenshot_confidence != null && (
          <p className="text-[11px] text-slate-500">
            Screenshot model confidence: {Math.round(Number(result.screenshot_confidence) * 100)}%
          </p>
        )}

        {generationDelta && generationDelta.bullets.length > 0 && (
          <details className="rounded-lg border border-violet-200/80 bg-violet-50/50 px-2 py-1.5 text-[11px] text-violet-950">
            <summary className="cursor-pointer font-semibold text-violet-900">Changes from last run</summary>
            <p className="mt-1 text-violet-900/90">{generationDelta.headline}</p>
            <ul className="mt-1 list-inside list-disc text-violet-900/85">
              {generationDelta.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {/* Right pane */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 xl:pl-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm">
            <button
              type="button"
              className={cn(
                'rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors',
                viewMode === 'highlight' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
              )}
              onClick={() => setViewMode('highlight')}
            >
              Highlighted
            </button>
            <button
              type="button"
              className={cn(
                'rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors',
                viewMode === 'source' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
              )}
              onClick={() => setViewMode('source')}
            >
              Edit source
            </button>
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => void handleCopy()}
              disabled={!xmlDisplay.trim()}
            >
              <Copy className="mr-1.5 h-3.5 w-3.5" />
              {copied ? 'Copied' : 'Copy XML'}
            </Button>
            {onRegenerateTopic && (
              <AuthoringRegenerateOptions
                baselineFromTurn={visualContext?.generationOptions}
                hasReferenceDita={Boolean(visualContext?.referenceFileName)}
                semanticSectionNames={semanticSectionNames}
                onRegenerate={onRegenerateTopic}
              />
            )}
            {!onRegenerateTopic && onRegenerateTopicFallback && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8"
                onClick={onRegenerateTopicFallback}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Regenerate
              </Button>
            )}
            {openAction?.url && (
              <a
                href={resolveArtifactUrl(openAction.url)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center rounded-md border border-emerald-600 bg-emerald-600 px-2.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
              >
                <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
                Open XML
              </a>
            )}
            {result.artifact_url && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() =>
                  void downloadArtifact(
                    resolveArtifactUrl(result.artifact_url || ''),
                    result.title ? ditaFileNameFromTitle(result.title) : 'generated-topic.dita'
                  )
                }
              >
                <Download className="mr-1.5 h-3.5 w-3.5" />
                Download
              </Button>
            )}
          </div>
        </div>

        <div className="flex min-h-0 min-h-[16rem] flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-slate-950 shadow-inner">
          {viewMode === 'highlight' ? (
            <div className="min-h-0 flex-1 overflow-auto">
              {xmlDisplay.trim() ? (
                <SyntaxHighlighter
                  language="xml"
                  style={oneDark}
                  showLineNumbers
                  wrapLongLines={false}
                  customStyle={{
                    margin: 0,
                    borderRadius: 0,
                    fontSize: '0.75rem',
                    lineHeight: 1.5,
                    minHeight: 'min(60vh, 28rem)',
                  }}
                >
                  {xmlDisplay}
                </SyntaxHighlighter>
              ) : (
                <p className="p-4 text-sm text-slate-400">No XML preview returned.</p>
              )}
            </div>
          ) : (
            <textarea
              value={xmlDraft}
              onChange={(e) => onXmlDraftChange(e.target.value)}
              spellCheck={false}
              className="min-h-[min(60vh,28rem)] w-full flex-1 resize-y border-0 bg-slate-900 p-3 font-mono text-[12px] leading-relaxed text-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500/30"
              aria-label="Edit generated DITA XML"
            />
          )}
        </div>

        {(assumptions.length > 0 || linkRecs.length > 0 || warnings.length > 10) && (
          <section
            className="rounded-lg border border-slate-200 bg-white/95 p-3 shadow-sm"
            aria-labelledby="auth-notes-label"
          >
            <p
              id="auth-notes-label"
              className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600"
            >
              <Wrench className="h-3.5 w-3.5" aria-hidden />
              Assumptions &amp; guidance
            </p>
            {assumptions.length > 0 && (
              <ul className="mt-2 space-y-1 text-[11px] text-slate-700" role="list">
                {assumptions.slice(0, 8).map((a, i) => (
                  <li key={`a-${i}`} className="leading-snug">
                    {a}
                  </li>
                ))}
              </ul>
            )}
            {linkRecs.length > 0 && (
              <div className={cn('mt-2', assumptions.length > 0 && 'border-t border-slate-100 pt-2')}>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Link &amp; reuse</p>
                <ul className="mt-1 space-y-1.5 text-[11px] text-slate-700" role="list">
                  {linkRecs.slice(0, 8).map((rec, i) => (
                    <li key={`lr-${i}`} className="leading-snug">
                      <span className="font-medium text-slate-800">[{rec.severity || 'info'}]</span> {rec.summary || ''}
                      {rec.action ? <span className="text-slate-500"> — {rec.action}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {warnings.length > 10 && (
              <div className="mt-2 border-t border-slate-100 pt-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-800">Additional warnings</p>
                <ul className="mt-1 max-h-24 space-y-1 overflow-y-auto text-[11px] text-amber-950" role="list">
                  {warnings.slice(10).map((t, i) => (
                    <li key={`wx-${i}`}>{t}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {result.style_profile_diff_summary && (
          <p className="text-[11px] leading-relaxed text-violet-900">{result.style_profile_diff_summary}</p>
        )}
      </div>
    </div>
  );
}
