import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';

import { AppPageHeader, AppPageShell } from '@/components/DocsShell';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  getChatEvalBreakdown,
  getChatEvalStats,
  getChatEvalTrends,
  listChatEvalPairs,
  promoteChatEvalPair,
  type ChatEvalBreakdownResponse,
  type ChatEvalPair,
  type ChatEvalStats,
  type ChatEvalTrendsResponse,
} from '@/api/chatEval';

const ChatEvalCharts = lazy(() =>
  import('./ChatEvalCharts').then((module) => ({ default: module.ChatEvalCharts })),
);

const PAGE_SIZE = 25;

const STATUS_COLORS: Record<string, string> = {
  grounded: '#10b981',
  partial: '#f59e0b',
  abstain: '#ef4444',
  conflict: '#a855f7',
  none: '#94a3b8',
};

function formatWhen(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function preview(text: string, max = 180): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max).trim()}…`;
}

function qualityBadgeClass(score?: number): string {
  if (score == null) return 'bg-muted text-muted-foreground';
  if (score >= 75) return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200';
  if (score >= 50) return 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200';
  return 'bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-200';
}

function RatingBadge({ rating }: { rating: ChatEvalPair['rating'] }) {
  if (rating === 'up') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
        <ThumbsUp className="h-3 w-3" aria-hidden />
        Helpful
      </span>
    );
  }
  if (rating === 'down') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-800 dark:bg-rose-950/50 dark:text-rose-200">
        <ThumbsDown className="h-3 w-3" aria-hidden />
        Not helpful
      </span>
    );
  }
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      Unrated
    </span>
  );
}

function GroundingChip({ status }: { status?: string }) {
  const label = status || 'none';
  const color = STATUS_COLORS[label] || STATUS_COLORS.none;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-medium capitalize"
      style={{ backgroundColor: `${color}22`, color }}
    >
      {label}
    </span>
  );
}

function EvalPairRow({
  pair,
  onPromoted,
}: {
  pair: ChatEvalPair;
  onPromoted: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [hintsOpen, setHintsOpen] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [promoteError, setPromoteError] = useState<string | null>(null);

  const hints = pair.improvement_hints ?? [];
  const showHints = hints.length > 0 && (pair.needs_review || (pair.quality_score ?? 100) < 60);

  const handlePromote = async () => {
    setPromoting(true);
    setPromoteError(null);
    try {
      await promoteChatEvalPair(pair.assistant_message_id);
      onPromoted();
    } catch (err) {
      setPromoteError(err instanceof Error ? err.message : 'Promote failed');
    } finally {
      setPromoting(false);
    }
  };

  return (
    <article className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{pair.session_title}</p>
            <RatingBadge rating={pair.rating} />
            {pair.quality_score != null ? (
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${qualityBadgeClass(pair.quality_score)}`}>
                Quality {pair.quality_score}
              </span>
            ) : null}
            <GroundingChip status={pair.grounding_status} />
            {pair.needs_review ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800 dark:bg-orange-950/50 dark:text-orange-200">
                <AlertTriangle className="h-3 w-3" aria-hidden />
                Needs review
              </span>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">{formatWhen(pair.answered_at)}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {pair.langsmith_trace_url ? (
            <a
              href={pair.langsmith_trace_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-8 items-center justify-center rounded-md border border-input bg-background px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              LangSmith
              <ExternalLink className="ml-1.5 h-3.5 w-3.5" aria-hidden />
            </a>
          ) : null}
          <Button type="button" variant="outline" size="sm" disabled={promoting} onClick={() => void handlePromote()}>
            {promoting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
            )}
            <span className="ml-1.5">Promote to learned QA</span>
          </Button>
          <Link
            to={`/chat?session=${encodeURIComponent(pair.session_id)}`}
            className="inline-flex h-8 items-center justify-center rounded-md border border-input bg-background px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            Open chat
            <ExternalLink className="ml-1.5 h-3.5 w-3.5" aria-hidden />
          </Link>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <>
                Collapse
                <ChevronUp className="ml-1 h-4 w-4" aria-hidden />
              </>
            ) : (
              <>
                Expand
                <ChevronDown className="ml-1 h-4 w-4" aria-hidden />
              </>
            )}
          </Button>
        </div>
      </div>

      {promoteError ? <p className="mt-2 text-xs text-destructive">{promoteError}</p> : null}

      <div className="mt-4 space-y-4">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Question</p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
            {expanded ? pair.question || '—' : preview(pair.question || '—')}
          </p>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Answer</p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
            {expanded ? pair.answer || '—' : preview(pair.answer || '—', 260)}
          </p>
        </div>
        {pair.feedback_comment ? (
          <div className="rounded-lg border border-border bg-muted/40 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Feedback note</p>
            <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{pair.feedback_comment}</p>
          </div>
        ) : null}
        {showHints ? (
          <div className="rounded-lg border border-amber-200/60 bg-amber-50/50 px-3 py-2 dark:border-amber-900/40 dark:bg-amber-950/20">
            <button
              type="button"
              className="flex w-full items-center justify-between text-left text-xs font-semibold uppercase tracking-wide text-amber-900 dark:text-amber-200"
              onClick={() => setHintsOpen((v) => !v)}
            >
              Improvement hints
              {hintsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {hintsOpen ? (
              <ul className="mt-2 space-y-2 text-sm text-foreground">
                {hints.map((hint) => (
                  <li key={`${hint.type}-${hint.message.slice(0, 40)}`}>
                    {hint.message}
                    {hint.action ? (
                      <>
                        {' '}
                        <Link to={hint.action} className="font-medium text-primary underline-offset-4 hover:underline">
                          Open settings
                        </Link>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function ChatEvalDashboardPage() {
  const [stats, setStats] = useState<ChatEvalStats | null>(null);
  const [trends, setTrends] = useState<ChatEvalTrendsResponse | null>(null);
  const [breakdown, setBreakdown] = useState<ChatEvalBreakdownResponse | null>(null);
  const [pairs, setPairs] = useState<ChatEvalPair[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [rating, setRating] = useState<'' | 'up' | 'down' | 'none'>('');
  const [weakOnly, setWeakOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsResult, pairsResult, trendsResult, breakdownResult] = await Promise.allSettled([
        getChatEvalStats(),
        listChatEvalPairs({
          limit: PAGE_SIZE,
          offset,
          search,
          rating,
          weak_only: weakOnly,
        }),
        getChatEvalTrends(30),
        getChatEvalBreakdown(),
      ]);

      const failures: string[] = [];
      if (statsResult.status === 'fulfilled') {
        setStats(statsResult.value);
      } else {
        failures.push('stats');
      }
      if (pairsResult.status === 'fulfilled') {
        setPairs(pairsResult.value.items);
        setTotal(pairsResult.value.total);
      } else {
        failures.push('pairs');
      }
      if (trendsResult.status === 'fulfilled') {
        setTrends(trendsResult.value);
      } else {
        setTrends(null);
        failures.push('trends');
      }
      if (breakdownResult.status === 'fulfilled') {
        setBreakdown(breakdownResult.value);
      } else {
        setBreakdown(null);
        failures.push('breakdown');
      }

      if (failures.includes('stats') && failures.includes('pairs')) {
        throw new Error('Could not load evaluation data. Restart the backend to pick up new /chat/eval routes.');
      }
      if (failures.length > 0) {
        setError(
          `Some eval data could not be loaded (${failures.join(', ')}). Restart the backend if charts or quality metrics are missing.`,
        );
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load evaluation dashboard');
    } finally {
      setLoading(false);
    }
  }, [offset, rating, search, weakOnly]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const pageLabel = useMemo(() => {
    if (total === 0) return 'No answers recorded yet';
    const start = offset + 1;
    const end = Math.min(offset + pairs.length, total);
    return `Showing ${start}–${end} of ${total}`;
  }, [offset, pairs.length, total]);

  const applySearch = useCallback(() => {
    setOffset(0);
    setSearch(searchInput.trim());
  }, [searchInput]);

  const abstainPct = useMemo(() => {
    if (!stats?.total_pairs || !stats.abstain_count) return '—';
    return `${Math.round((stats.abstain_count / stats.total_pairs) * 100)}%`;
  }, [stats]);

  return (
    <AppPageShell wide>
      <AppPageHeader
        title="Chat evaluation"
        description="Every question you ask in chat is recorded here with the answer the assistant returned. Review quality, spot weak replies, and open the original conversation."
      >
        <Button type="button" variant="outline" size="sm" onClick={() => void loadDashboard()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}
          <span className="ml-2">Refresh</span>
        </Button>
      </AppPageHeader>

      {error ? (
        <div className="mt-6 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'Recorded Q&A pairs', value: stats?.total_pairs ?? '—' },
          { label: 'Avg quality score', value: stats?.avg_quality_score ?? '—' },
          { label: 'Abstain rate', value: abstainPct },
          { label: 'Needs review', value: stats?.needs_review_count ?? '—' },
        ].map((item) => (
          <Card key={item.label}>
            <CardHeader className="pb-2">
              <CardDescription>{item.label}</CardDescription>
              <CardTitle className="text-2xl">{item.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <Suspense
        fallback={
          <div className="mt-8 flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" aria-hidden />
            Loading charts…
          </div>
        }
      >
        <ChatEvalCharts trends={trends} breakdown={breakdown} />
      </Suspense>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <MessageSquare className="h-5 w-5 text-muted-foreground" aria-hidden />
            Answer history
          </CardTitle>
          <CardDescription>
            Automatically recorded from chat. Thumbs up/down in chat appear here as ratings.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') applySearch();
                }}
                placeholder="Search questions, answers, or session titles"
                className="pl-9"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {([
                ['', 'All'],
                ['up', 'Helpful'],
                ['down', 'Not helpful'],
                ['none', 'Unrated'],
              ] as const).map(([value, label]) => (
                <Button
                  key={value || 'all'}
                  type="button"
                  size="sm"
                  variant={rating === value ? 'default' : 'outline'}
                  onClick={() => {
                    setOffset(0);
                    setRating(value);
                  }}
                >
                  {label}
                </Button>
              ))}
              <Button
                type="button"
                size="sm"
                variant={weakOnly ? 'default' : 'outline'}
                onClick={() => {
                  setOffset(0);
                  setWeakOnly((v) => !v);
                }}
              >
                Weak only
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={applySearch}>
                Search
              </Button>
            </div>
          </div>

          {loading && pairs.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" aria-hidden />
              Loading recorded answers…
            </div>
          ) : pairs.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
              <p className="text-sm font-medium text-foreground">No matching answers yet</p>
              <p className="mt-2 text-sm text-muted-foreground">
                Ask something in{' '}
                <Link to="/chat" className="font-medium text-primary underline-offset-4 hover:underline">
                  AI Chat
                </Link>{' '}
                and it will show up here automatically.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {pairs.map((pair) => (
                <EvalPairRow key={pair.assistant_message_id} pair={pair} onPromoted={() => void loadDashboard()} />
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <p className="text-sm text-muted-foreground">{pageLabel}</p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={loading || offset === 0}
                onClick={() => setOffset((value) => Math.max(value - PAGE_SIZE, 0))}
              >
                Previous
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={loading || offset + PAGE_SIZE >= total}
                onClick={() => setOffset((value) => value + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </AppPageShell>
  );
}

export default ChatEvalDashboardPage;
