import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Brain, CheckCircle, Clock3, Database, Download, Loader2, RefreshCw, XCircle } from 'lucide-react';

import { AppPageHeader, AppPageShell } from '@/components/DocsShell';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { apiUrl, fetchJson } from '@/utils/api';

interface ReviewCenterSource {
  source_id: string;
  title: string;
  description: string;
  collection: string;
  chunk_count: number;
  candidate_backlog?: number;
  issue_count?: number | null;
  last_successful_run?: string | null;
  failed_item_count?: number;
  failed_items?: string[];
  populate_via?: string;
  last_error?: string | null;
  extra?: Record<string, unknown>;
}

interface ReviewCenterCandidate {
  id: string;
  prompt: string;
  final_answer: string;
  topic?: string | null;
  tags: string[];
  source_type?: string | null;
  status: string;
  support_count?: number;
  accepted_at?: string | null;
  updated_at?: string | null;
}

interface ReviewCenterStatus {
  generated_at: string;
  chroma_available: boolean;
  sources: ReviewCenterSource[];
  candidate_counts: {
    pending_review: number;
    approved: number;
    rejected: number;
    total: number;
  };
  recent_failures: Array<{
    ts: string;
    source_id: string;
    operation: string;
    error: string;
    failed_items?: string[];
  }>;
  tavily?: {
    configured: boolean;
    chat_enabled: boolean;
    hint?: string | null;
  };
}

interface CandidateResponse {
  items: ReviewCenterCandidate[];
}

function formatTimestamp(value?: string | null): string {
  if (!value) return 'Not run yet';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function SettingsPage() {
  const [status, setStatus] = useState<ReviewCenterStatus | null>(null);
  const [candidates, setCandidates] = useState<ReviewCenterCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [customUrlsText, setCustomUrlsText] = useState('');
  const [customUrlsResult, setCustomUrlsResult] = useState<{ message: string; isError: boolean } | null>(null);

  const loadReviewCenter = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reviewStatus, candidateData] = await Promise.all([
        fetchJson<ReviewCenterStatus>(apiUrl('/api/v1/ai/review-center')),
        fetchJson<CandidateResponse>(apiUrl('/api/v1/ai/review-center/candidates?status=pending_review')),
      ]);
      setStatus(reviewStatus);
      setCandidates(candidateData.items || []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load review center');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReviewCenter();
  }, [loadReviewCenter]);

  const trustedChunkTotal = useMemo(
    () => (status?.sources || []).reduce((sum, source) => sum + (source.chunk_count || 0), 0),
    [status?.sources]
  );

  const setActionBusy = useCallback((key: string, busy: boolean) => {
    setActionLoading(previous => ({ ...previous, [key]: busy }));
  }, []);

  const runSourceAction = useCallback(
    async (sourceId: string) => {
      const key = `reindex:${sourceId}`;
      setActionBusy(key, true);
      setError(null);
      setLastAction(null);
      try {
        const result = await fetchJson<Record<string, unknown>>(
          apiUrl(`/api/v1/ai/review-center/sources/${sourceId}/reindex`),
          { method: 'POST' }
        );
        const indexed = Number(result.indexed ?? result.chunks_stored ?? result.issues_indexed ?? 0);
        const errors = Array.isArray(result.errors) ? result.errors : [];
        setLastAction(
          errors.length > 0
            ? `${sourceId} reindex completed with ${indexed} primary results and ${errors.length} reported issue(s).`
            : `${sourceId} reindex completed successfully.`
        );
        await loadReviewCenter();
      } catch (actionError) {
        setError(actionError instanceof Error ? actionError.message : `Failed to reindex ${sourceId}`);
      } finally {
        setActionBusy(key, false);
      }
    },
    [loadReviewCenter, setActionBusy]
  );

  const runCandidateAction = useCallback(
    async (entryId: string, action: 'approve' | 'reject') => {
      const key = `${action}:${entryId}`;
      setActionBusy(key, true);
      setError(null);
      try {
        await fetchJson(apiUrl(`/api/v1/ai/review-center/candidates/${entryId}/${action}`), {
          method: 'POST',
        });
        setLastAction(`Candidate ${action}d successfully.`);
        await loadReviewCenter();
      } catch (actionError) {
        setError(actionError instanceof Error ? actionError.message : `Failed to ${action} candidate`);
      } finally {
        setActionBusy(key, false);
      }
    },
    [loadReviewCenter, setActionBusy]
  );

  const handleSeedLearnedQa = useCallback(async () => {
    const key = 'seed-learned-qa';
    setActionBusy(key, true);
    setError(null);
    try {
      const result = await fetchJson<{ seed?: { created?: number; updated?: number }; index?: { indexed?: number } }>(
        apiUrl('/api/v1/ai/learned-qa/seed'),
        { method: 'POST' }
      );
      setLastAction(
        `Seeded learned QA (${result.seed?.created ?? 0} created, ${result.seed?.updated ?? 0} updated) and indexed ${result.index?.indexed ?? 0} approved pairs.`
      );
      await loadReviewCenter();
    } catch (seedError) {
      setError(seedError instanceof Error ? seedError.message : 'Failed to seed learned QA');
    } finally {
      setActionBusy(key, false);
    }
  }, [loadReviewCenter, setActionBusy]);

  const handleExportLearnedQa = useCallback(async () => {
    const key = 'export-learned-qa';
    setActionBusy(key, true);
    setError(null);
    try {
      const result = await fetchJson<{ path: string; count: number }>(apiUrl('/api/v1/ai/learned-qa/export'), {
        method: 'POST',
      });
      setLastAction(`Exported ${result.count} approved prompt-answer pairs to ${result.path}.`);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : 'Failed to export learned QA');
    } finally {
      setActionBusy(key, false);
    }
  }, [setActionBusy]);

  const handleIndexCustomUrls = useCallback(async () => {
    const urls = customUrlsText
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.startsWith('http://') || line.startsWith('https://'));

    if (urls.length === 0) {
      setCustomUrlsResult({
        message: 'Enter one valid URL per line starting with http:// or https://.',
        isError: true,
      });
      return;
    }

    const key = 'custom-aem-urls';
    setActionBusy(key, true);
    setCustomUrlsResult(null);
    try {
      const result = await fetchJson<{ chunks_stored?: number; pages_crawled?: number; errors?: string[] }>(
        apiUrl('/api/v1/ai/crawl-aem-guides'),
        {
          method: 'POST',
          body: JSON.stringify({ urls }),
        }
      );
      const errors = result.errors || [];
      setCustomUrlsResult({
        message:
          errors.length > 0
            ? `Indexed ${result.pages_crawled ?? 0} pages with ${result.chunks_stored ?? 0} chunks and ${errors.length} issue(s).`
            : `Indexed ${result.pages_crawled ?? 0} pages and stored ${result.chunks_stored ?? 0} chunks.`,
        isError: errors.length > 0,
      });
      if (errors.length === 0) {
        setCustomUrlsText('');
      }
      await loadReviewCenter();
    } catch (crawlError) {
      setCustomUrlsResult({
        message: crawlError instanceof Error ? crawlError.message : 'Failed to index custom URLs',
        isError: true,
      });
    } finally {
      setActionBusy(key, false);
    }
  }, [customUrlsText, loadReviewCenter, setActionBusy]);

  return (
    <AppPageShell wide className="space-y-8">
      <AppPageHeader
        title="Review Center"
        description="Trusted-source health, learned prompt review, and indexing actions."
      />

      {loading ? (
        <Card>
          <CardContent className="flex items-center gap-3 py-10 text-slate-600">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading review center...
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      {lastAction ? (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">{lastAction}</div>
      ) : null}

      {!loading && status ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-sm text-slate-500">Trusted chunks</div>
                <div className="mt-2 text-3xl font-bold text-slate-900">{trustedChunkTotal}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-sm text-slate-500">Learned prompts</div>
                <div className="mt-2 text-3xl font-bold text-slate-900">{status.candidate_counts.total}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-sm text-slate-500">Pending review</div>
                <div className="mt-2 text-3xl font-bold text-amber-600">{status.candidate_counts.pending_review}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-sm text-slate-500">Failed items logged</div>
                <div className="mt-2 text-3xl font-bold text-rose-600">
                  {(status.sources || []).reduce((sum, source) => sum + (source.failed_item_count || 0), 0)}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl text-slate-900">
                <Database className="h-5 w-5" />
                Source health
              </CardTitle>
              <CardDescription>
                Review trusted-source counts, last successful runs, failure state, and source-specific quick actions.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-2">
              {status.sources.map(source => {
                const busy = Boolean(actionLoading[`reindex:${source.source_id}`]);
                return (
                  <div key={source.source_id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-900">{source.title}</h3>
                        <p className="mt-1 text-sm leading-6 text-slate-600">{source.description}</p>
                      </div>
                      {source.failed_item_count ? (
                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                      ) : (
                        <CheckCircle className="h-5 w-5 text-green-600" />
                      )}
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <div className="text-xs uppercase tracking-wide text-slate-500">Chunks</div>
                        <div className="mt-1 text-lg font-semibold text-slate-900">{source.chunk_count}</div>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <div className="text-xs uppercase tracking-wide text-slate-500">Last successful run</div>
                        <div className="mt-1 text-sm font-medium text-slate-900">{formatTimestamp(source.last_successful_run)}</div>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <div className="text-xs uppercase tracking-wide text-slate-500">Backlog / issues</div>
                        <div className="mt-1 text-sm font-medium text-slate-900">
                          {source.candidate_backlog || source.issue_count || 0}
                        </div>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <div className="text-xs uppercase tracking-wide text-slate-500">Failed items</div>
                        <div className="mt-1 text-sm font-medium text-slate-900">{source.failed_item_count || 0}</div>
                      </div>
                    </div>

                    {source.last_error ? (
                      <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                        <strong className="font-semibold">Last error:</strong> {source.last_error}
                      </div>
                    ) : null}

                    {source.failed_items?.length ? (
                      <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recent failed items</div>
                        <ul className="mt-2 space-y-1 text-sm text-slate-700">
                          {source.failed_items.slice(0, 4).map(item => (
                            <li key={item} className="truncate">{item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button onClick={() => runSourceAction(source.source_id)} disabled={busy}>
                        {busy ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Reindexing
                          </>
                        ) : (
                          <>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Reindex
                          </>
                        )}
                      </Button>
                      {source.source_id === 'learned_qa' ? (
                        <>
                          <Button variant="outline" onClick={handleSeedLearnedQa} disabled={Boolean(actionLoading['seed-learned-qa'])}>
                            {actionLoading['seed-learned-qa'] ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Seeding
                              </>
                            ) : (
                              <>
                                <Brain className="mr-2 h-4 w-4" />
                                Seed curated prompts
                              </>
                            )}
                          </Button>
                          <Button variant="outline" onClick={handleExportLearnedQa} disabled={Boolean(actionLoading['export-learned-qa'])}>
                            {actionLoading['export-learned-qa'] ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Exporting
                              </>
                            ) : (
                              <>
                                <Download className="mr-2 h-4 w-4" />
                                Export approved pairs
                              </>
                            )}
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <Card>
              <CardHeader>
                <CardTitle className="text-xl text-slate-900">Learned prompt review queue</CardTitle>
                <CardDescription>
                  Only approved prompt-answer pairs enter trusted retrieval. Pending chat learnings stay here until reviewed.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {candidates.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600">
                    No pending learned prompts right now.
                  </div>
                ) : (
                  candidates.map(candidate => (
                    <div key={candidate.id} className="rounded-xl border border-slate-200 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">{candidate.prompt}</div>
                          <div className="mt-1 text-xs text-slate-500">
                            {candidate.topic || 'dita_general'} • {candidate.source_type || 'chat_feedback'} • support {candidate.support_count || 1}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => runCandidateAction(candidate.id, 'approve')}
                            disabled={Boolean(actionLoading[`approve:${candidate.id}`])}
                          >
                            {actionLoading[`approve:${candidate.id}`] ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Approve'}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => runCandidateAction(candidate.id, 'reject')}
                            disabled={Boolean(actionLoading[`reject:${candidate.id}`])}
                          >
                            {actionLoading[`reject:${candidate.id}`] ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Reject'}
                          </Button>
                        </div>
                      </div>
                      <div className="mt-3 rounded-lg bg-slate-50 p-3">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Answer preview</div>
                        <pre className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{candidate.final_answer}</pre>
                      </div>
                      {candidate.tags?.length ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {candidate.tags.map(tag => (
                            <span key={tag} className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600">
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-xl text-slate-900">AEM crawl additions</CardTitle>
                  <CardDescription>
                    Add trusted Experience League or related URLs into the AEM Guides knowledge base and keep them for future recrawls.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <textarea
                    value={customUrlsText}
                    onChange={event => setCustomUrlsText(event.target.value)}
                    placeholder="https://experienceleague.adobe.com/en/docs/...\nhttps://experienceleague.adobe.com/en/docs/..."
                    rows={6}
                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
                  />
                  <Button onClick={handleIndexCustomUrls} disabled={Boolean(actionLoading['custom-aem-urls'])}>
                    {actionLoading['custom-aem-urls'] ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Indexing URLs
                      </>
                    ) : (
                      'Index URLs'
                    )}
                  </Button>
                  {customUrlsResult ? (
                    <div
                      className={`rounded-lg px-4 py-3 text-sm ${
                        customUrlsResult.isError ? 'border border-amber-200 bg-amber-50 text-amber-900' : 'border border-green-200 bg-green-50 text-green-700'
                      }`}
                    >
                      {customUrlsResult.message}
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-xl text-slate-900">Recent failures</CardTitle>
                  <CardDescription>Latest source errors and failed items captured for review.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {status.recent_failures.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                      No recent failures logged.
                    </div>
                  ) : (
                    status.recent_failures.slice(0, 8).map((failure, index) => (
                      <div key={`${failure.source_id}-${failure.ts}-${index}`} className="rounded-lg border border-slate-200 p-3">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <Clock3 className="h-4 w-4 text-slate-500" />
                          {failure.source_id} • {failure.operation}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">{formatTimestamp(failure.ts)}</div>
                        <p className="mt-2 text-sm text-slate-700">{failure.error}</p>
                        {failure.failed_items?.length ? (
                          <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
                            {failure.failed_items.slice(0, 3).map(item => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-xl text-slate-900">Runtime notes</CardTitle>
                  <CardDescription>Quick health notes for retrieval behavior.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-slate-700">
                  <div className="flex items-center gap-2">
                    {status.chroma_available ? (
                      <CheckCircle className="h-4 w-4 text-green-600" />
                    ) : (
                      <XCircle className="h-4 w-4 text-amber-600" />
                    )}
                    ChromaDB is {status.chroma_available ? 'available' : 'not available'}.
                  </div>
                  {status.tavily ? (
                    <div className="flex items-start gap-2">
                      {status.tavily.configured ? (
                        <CheckCircle className="mt-0.5 h-4 w-4 text-green-600" />
                      ) : (
                        <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
                      )}
                      <div>
                        Tavily web search is {status.tavily.configured ? 'configured' : 'not configured'}.
                        {status.tavily.hint ? <div className="mt-1 text-xs text-slate-500">{status.tavily.hint}</div> : null}
                      </div>
                    </div>
                  ) : null}
                  <div className="text-xs text-slate-500">
                    Last review-center refresh: {formatTimestamp(status.generated_at)}
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </AppPageShell>
  );
}
