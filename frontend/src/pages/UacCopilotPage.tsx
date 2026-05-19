import { useCallback, useMemo, useState } from 'react';
import { ClipboardCheck, Loader2, AlertTriangle, ChevronDown } from 'lucide-react';
import { postUacAnalyze, type UacAnalyzeResponse, type UacAntiRepetitionMeta } from '@/api/uacCopilot';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  parseRiskHighlights,
  parseUacAnswerMarkdown,
  splitUacSections,
} from '@/utils/parseUacAnswer';
import { normalizeJiraKeyInput } from '@/utils/uacJiraKey';

function riskBadgeClass(level: string): string {
  const L = (level || '').toLowerCase();
  if (L === 'high') return 'bg-red-600 text-white border-red-700 hover:bg-red-600';
  if (L === 'medium') return 'bg-amber-500 text-white border-amber-600 hover:bg-amber-500';
  if (L === 'low') return 'bg-emerald-700 text-white border-emerald-800 hover:bg-emerald-700';
  if (L === 'insufficient' || L === 'unspecified') return 'bg-slate-500 text-white border-slate-600 hover:bg-slate-500';
  return 'bg-slate-600 text-white border-slate-700 hover:bg-slate-600';
}

function isLowSimilarConfidence(includeSimilar: boolean, data: UacAnalyzeResponse | null): boolean {
  if (!data || !includeSimilar) return false;
  if (data.insufficient_similar_evidence) return true;
  if (data.uac_ui?.confidence_warnings_card?.insufficient_similar_evidence) return true;
  const n = data.similar_jiras?.length ?? 0;
  if (n === 0) return true;
  const finals = data.similar_jiras?.map((s) => s.scores?.final ?? 0) ?? [];
  const top = Math.max(0, ...finals);
  return top < 0.08;
}

function ClipText({ text, className }: { text: string; className?: string }) {
  const t = (text || '').trim() || '—';
  return (
    <span className={cn('line-clamp-2 text-xs text-slate-700', className)} title={t.length > 80 ? t : undefined}>
      {t}
    </span>
  );
}

function AntiRepetitionPanel({ meta }: { meta: UacAntiRepetitionMeta }) {
  return (
    <details className="group rounded-xl border border-teal-100 bg-teal-50/20 shadow-sm open:shadow">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold text-slate-800">
        <span>Anti-repetition (structured UAC)</span>
        <ChevronDown className="w-4 h-4 shrink-0 transition group-open:rotate-180 text-slate-500" />
      </summary>
      <div className="border-t border-teal-100/80 px-4 py-3 space-y-2 text-xs text-slate-800">
        <div className="flex flex-wrap gap-2">
          <Badge variant={meta.skipped ? 'secondary' : meta.changed ? 'default' : 'outline'} className="text-[10px]">
            {meta.skipped ? 'skipped' : meta.changed ? 'edited' : 'unchanged'}
          </Badge>
          {meta.markdown_refreshed ? (
            <Badge variant="outline" className="text-[10px]">
              markdown refreshed
            </Badge>
          ) : null}
        </div>
        <ul className="grid gap-1 sm:grid-cols-2 text-[11px]">
          <li>
            <span className="text-slate-500">Scenarios deduped</span>: {meta.scenarios_deduped}
          </li>
          <li>
            <span className="text-slate-500">Scenarios vs memory</span>: {meta.scenarios_rewritten_memory}
          </li>
          <li>
            <span className="text-slate-500">Anchor strengthen</span>: {meta.scenarios_strengthened_anchor}
          </li>
          <li>
            <span className="text-slate-500">Drivers dropped (generic)</span>: {meta.drivers_dropped_generic}
          </li>
          <li>
            <span className="text-slate-500">Drivers rewritten</span>: {meta.drivers_rewritten}
          </li>
          <li>
            <span className="text-slate-500">Clarifications rewritten</span>: {meta.clarifications_rewritten}
          </li>
        </ul>
        {meta.reasons.length > 0 ? (
          <div>
            <span className="text-slate-500 font-semibold block mb-1">Reasons</span>
            <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-slate-700">
              {meta.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}

export function UacCopilotPage() {
  const [jiraKey, setJiraKey] = useState('');
  const [includeSimilar, setIncludeSimilar] = useState(true);
  const [debugMode, setDebugMode] = useState(false);
  const [includeQaHandoff, setIncludeQaHandoff] = useState(false);
  const [maxSimilar, setMaxSimilar] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UacAnalyzeResponse | null>(null);

  const parsed = useMemo(() => {
    if (!result?.uac_answer) {
      return { scenarios: [], missing: [], automation: null, riskHints: [] };
    }
    const sections = splitUacSections(result.uac_answer);
    const { scenarios, missingClarifications, automation } = parseUacAnswerMarkdown(result.uac_answer);
    const riskHints = parseRiskHighlights(sections[2] || '');
    return {
      scenarios,
      missing: missingClarifications,
      automation,
      riskHints,
    };
  }, [result]);

  const lowConfidence = useMemo(
    () => isLowSimilarConfidence(includeSimilar, result),
    [includeSimilar, result]
  );

  const run = useCallback(async () => {
    const key = normalizeJiraKeyInput(jiraKey);
    if (!key) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await postUacAnalyze({
        jira_key: key,
        include_similar: includeSimilar,
        max_similar: Math.min(24, Math.max(0, maxSimilar)),
        debug: debugMode,
        include_qa_handoff: includeQaHandoff,
      });
      setResult(data);
      if (data.error) {
        setError(data.error);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [jiraKey, includeSimilar, maxSimilar, debugMode, includeQaHandoff]);

  const normalizedKey = normalizeJiraKeyInput(jiraKey);

  const classification = result?.classification;
  const ui = result?.uac_ui ?? null;

  const criteriaItems = useMemo(() => {
    // LLM-parsed scenarios are ticket-specific; template rows are generic placeholders.
    if (parsed.scenarios.length > 0) {
      return parsed.scenarios.map((s) => s.scenario.replace(/^[A-Z]+-\d+:\s*/i, '').trim());
    }
    const rows = ui?.must_test_scenario_table?.rows;
    if (rows && rows.length > 0) {
      return rows.map((row) => row.scenario.replace(/^[A-Z]+-\d+:\s*/i, '').trim());
    }
    return [];
  }, [ui, parsed]);

  const similarCards = useMemo(() => {
    if ((ui?.similar_jira_learning_cards?.length ?? 0) > 0) {
      return ui!.similar_jira_learning_cards.map((s) => ({
        key: s.jira_key,
        title: s.title || '',
        why: s.why_relevant || '',
        learned: s.what_we_learned || '',
      }));
    }
    return (result?.similar_jiras || []).map((s) => ({
      key: s.jira_key,
      title: s.summary || s.title || '',
      why: s.why_similar || '',
      learned: s.what_we_learned || '',
    }));
  }, [ui, result]);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-start gap-3">
        <div className="w-12 h-12 bg-teal-100 rounded-xl flex items-center justify-center shrink-0">
          <ClipboardCheck className="w-6 h-6 text-teal-700" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">UAC Copilot</h1>
          <p className="text-sm text-slate-600 mt-1">
            Structured <code className="text-xs bg-slate-100 px-1 rounded">uac_ui</code> view when available—executive
            summary, scenario table, clarifications, dataset hints, and validation. Optional{' '}
            <strong className="font-medium">Extended QA handoff</strong> adds a second LLM pass (smoke vs deep regression,
            sign-off blockers, Jira-style steps). Paste a key or full Jira browse URL.
          </p>
        </div>
      </div>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Analyze ticket</CardTitle>
          <CardDescription>Server uses enrichment-backed classification and an evidence gate on drafts.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1.5 min-w-[200px] flex-1">
              <Label htmlFor="uac-jira-key">Jira key</Label>
              <Input
                id="uac-jira-key"
                placeholder="GUIDES-45800 or https://jira…/browse/GUIDES-45800"
                value={jiraKey}
                onChange={(e) => setJiraKey(e.target.value)}
                className="font-mono"
              />
            </div>
            <div className="space-y-1.5 w-24">
              <Label htmlFor="uac-max-sim">Max similar</Label>
              <Input
                id="uac-max-sim"
                type="number"
                min={0}
                max={24}
                value={maxSimilar}
                onChange={(e) => setMaxSimilar(parseInt(e.target.value, 10) || 0)}
              />
            </div>
            <div className="flex items-center gap-2 pb-2">
              <Switch id="uac-similar" checked={includeSimilar} onCheckedChange={setIncludeSimilar} />
              <Label htmlFor="uac-similar" className="text-sm font-normal cursor-pointer">
                Include similar Jiras
              </Label>
            </div>
            <Button
              className="bg-teal-600 hover:bg-teal-700 text-white"
              onClick={() => void run()}
              disabled={loading || !normalizedKey}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Analyzing…
                </>
              ) : (
                'Run analysis'
              )}
            </Button>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          )}
          {result?.warning && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              {result.warning}
            </div>
          )}
          {lowConfidence && result && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50/80 px-3 py-2 text-sm text-amber-950">
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-700" />
              <span>Low confidence: insufficient similar Jira evidence.</span>
            </div>
          )}
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-4">

          {/* ── Risk badge ── */}
          {ui ? (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-gradient-to-r from-slate-50 to-teal-50/30 px-4 py-3 shadow-sm">
              <Badge className={cn('text-xs font-semibold border', riskBadgeClass(ui.risk_badge.level))}>
                {ui.risk_badge.label}
              </Badge>
              {ui.risk_badge.message ? (
                <span className="text-xs text-slate-700 line-clamp-2" title={ui.risk_badge.message}>
                  {ui.risk_badge.message}
                </span>
              ) : null}
            </div>
          ) : null}

          {/* ── Section 1: Acceptance Criteria ── */}
          <Card className="border-teal-200/60 shadow-sm">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-base">Acceptance Criteria</CardTitle>
              <CardDescription className="text-xs">What must work for this ticket to be accepted.</CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              {criteriaItems.length > 0 ? (
                <ul className="space-y-2">
                  {criteriaItems.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-800">
                      <span className="text-teal-600 mt-0.5 shrink-0 font-bold">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500">No acceptance criteria generated. Check the full analysis below.</p>
              )}
            </CardContent>
          </Card>

          {/* ── Section 2: Similar Jiras ── */}
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-base">Similar Jiras from Knowledge Base</CardTitle>
              <CardDescription className="text-xs">Past tickets the RAG retrieved as relevant to this one.</CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 space-y-3">
              {similarCards.length > 0 ? (
                similarCards.map((card) => (
                  <div key={card.key} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm space-y-1">
                    <p className="font-mono text-sm font-semibold text-teal-800">{card.key}
                      {card.title ? <span className="font-sans font-normal text-slate-700 ml-2">— {card.title}</span> : null}
                    </p>
                    {card.why ? (
                      <p className="text-xs text-slate-700">
                        <span className="font-semibold">Why relevant: </span>{card.why}
                      </p>
                    ) : null}
                    {card.learned ? (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">What we learned: </span>{card.learned}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="text-xs text-slate-500">None found in the knowledge base. Index Jira QA chunks or adjust filters.</p>
              )}
            </CardContent>
          </Card>

          {/* ── Show full analysis (collapsible) ── */}
          <details className="group rounded-xl border border-slate-200 bg-white shadow-sm open:shadow">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold text-slate-700 select-none">
              <span>Show full analysis</span>
              <ChevronDown className="w-4 h-4 shrink-0 transition group-open:rotate-180 text-slate-400" />
            </summary>
            <div className="border-t border-slate-100 px-4 py-4 space-y-4">

              {/* Advanced options (moved from main form) */}
              <div className="flex flex-wrap gap-4 items-center rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
                <span className="font-semibold text-slate-700">Advanced options</span>
                <div className="flex items-center gap-1.5">
                  <Switch id="uac-debug-adv" checked={debugMode} onCheckedChange={setDebugMode} />
                  <Label htmlFor="uac-debug-adv" className="text-xs font-normal cursor-pointer">Debug (retrieval)</Label>
                </div>
                <div className="flex items-center gap-1.5">
                  <Switch id="uac-qa-handoff-adv" checked={includeQaHandoff} onCheckedChange={setIncludeQaHandoff} />
                  <Label htmlFor="uac-qa-handoff-adv" className="text-xs font-normal cursor-pointer">Extended QA handoff (2nd LLM)</Label>
                </div>
                {(debugMode || includeQaHandoff) ? (
                  <span className="text-amber-700 text-[10px]">Re-run analysis to apply changes.</span>
                ) : null}
              </div>

          {ui ? (
            <>
              <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-gradient-to-r from-slate-50 to-teal-50/30 px-4 py-3 shadow-sm">
                <Badge className={cn('text-xs font-semibold border', riskBadgeClass(ui.risk_badge.level))}>
                  {ui.risk_badge.label}
                </Badge>
                {ui.risk_badge.risk_score != null ? (
                  <span className="text-xs text-slate-600">Score: {ui.risk_badge.risk_score}</span>
                ) : null}
                {ui.risk_badge.message ? (
                  <span className="text-xs text-slate-700 line-clamp-2 max-md:w-full" title={ui.risk_badge.message}>
                    {ui.risk_badge.message}
                  </span>
                ) : null}
                {ui.confidence_warnings_card.quality_score != null ? (
                  <Badge variant="outline" className="text-[10px] ml-auto shrink-0">
                    Specificity {ui.confidence_warnings_card.quality_score}/100
                  </Badge>
                ) : null}
                {!ui.confidence_warnings_card.uac_validation_ok ? (
                  <Badge className="text-[10px] shrink-0 bg-amber-600 hover:bg-amber-600 text-white border-amber-700">
                    Validation needs review
                  </Badge>
                ) : null}
              </div>

              <Card className="border-teal-200/60 shadow-sm ring-1 ring-teal-500/10">
                <CardHeader className="py-3 px-4">
                  <CardTitle className="text-base">Executive summary</CardTitle>
                  <CardDescription className="text-xs">Decision-record snapshot for QA / release discussion.</CardDescription>
                </CardHeader>
                <CardContent className="px-4 pb-4 pt-0 space-y-3 text-sm">
                  <p className="text-slate-800 leading-relaxed">{ui.executive_summary_card.summary || '—'}</p>
                  {ui.executive_summary_card.release_risk ? (
                    <div className="rounded-lg bg-amber-50/80 border border-amber-100 px-3 py-2 text-xs text-amber-950">
                      <span className="font-semibold">Release risk: </span>
                      {ui.executive_summary_card.release_risk}
                    </div>
                  ) : null}
                  {(ui.executive_summary_card.decisions_needed_preview?.length ?? 0) > 0 ? (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-1">
                        Decisions needed
                      </p>
                      <ul className="list-disc list-inside space-y-1 text-xs text-slate-800">
                        {ui.executive_summary_card.decisions_needed_preview!.map((d, i) => (
                          <li key={i}>{d}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {(ui.executive_summary_card.qa_commitments_preview?.length ?? 0) > 0 ? (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-1">
                        QA commitments
                      </p>
                      <ul className="list-disc list-inside space-y-1 text-xs text-slate-800">
                        {ui.executive_summary_card.qa_commitments_preview!.map((d, i) => (
                          <li key={i}>{d}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </>
          ) : null}

          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-base">Jira classification</CardTitle>
              <CardDescription className="text-xs">From indexed enrichment (not LLM prose).</CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-slate-100 bg-slate-50/80 p-3 text-sm">
                  <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">Domain</p>
                  <p className="font-medium text-slate-900">
                    {classification?.domain ?? '—'}
                    {classification?.sub_domain ? (
                      <span className="text-slate-500 font-normal"> / {classification.sub_domain}</span>
                    ) : null}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-100 bg-slate-50/80 p-3 text-sm">
                  <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">Type · Status · Priority</p>
                  <p className="text-slate-800">
                    {[classification?.issue_type, classification?.status, classification?.priority].filter(Boolean).join(' · ') ||
                      '—'}
                  </p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(classification?.customer_names || []).slice(0, 12).map((c) => (
                  <Badge key={c} variant="secondary" className="text-[10px] font-normal bg-white border-slate-200">
                    {c}
                  </Badge>
                ))}
                {!(classification?.customer_names || []).length && (
                  <span className="text-xs text-slate-500">No customers in enrichment</span>
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="text-[10px] text-slate-500 w-full">Outputs</span>
                {(classification?.affected_outputs || []).slice(0, 10).map((o) => (
                  <Badge key={o} variant="outline" className="text-[10px] font-normal">
                    {o}
                  </Badge>
                ))}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="text-[10px] text-slate-500 w-full">DITA / entities</span>
                {(classification?.dita_entities || []).slice(0, 12).map((o) => (
                  <Badge key={o} variant="outline" className="text-[10px] font-normal border-teal-200 text-teal-900">
                    {o}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          {result.output_parity ? (
            <Card
              className={cn(
                'border-slate-200 shadow-sm',
                result.output_parity.parity_required && 'border-teal-200/80 ring-1 ring-teal-500/15'
              )}
            >
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">Cross-output parity</CardTitle>
                <CardDescription className="text-xs">
                  {result.output_parity.parity_required
                    ? 'Structured check surfaces where acceptance should match across AEM Guides outputs.'
                    : 'No multi-surface parity signal from current Jira evidence.'}
                </CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-3">
                {(result.output_parity.parity_pairs?.length ?? 0) > 0 ? (
                  <ul className="space-y-2">
                    {result.output_parity.parity_pairs!.map((p, i) => (
                      <li
                        key={i}
                        className="rounded-lg border border-slate-100 bg-slate-50/80 p-2 text-xs text-slate-800"
                      >
                        <span className="font-mono font-semibold text-teal-800">
                          {p.source} → {p.target}
                        </span>
                        <p className="mt-1 text-slate-700 leading-snug">{p.risk}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-slate-500">No directed pairs (insufficient applicable outputs).</p>
                )}
                {(result.output_parity.validation_points?.length ?? 0) > 0 ? (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-1.5">
                      Validation points
                    </p>
                    <ul className="list-disc list-inside space-y-1 text-xs text-slate-700">
                      {result.output_parity.validation_points!.map((pt, i) => (
                        <li key={i}>{pt}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {!ui && parsed.riskHints.length > 0 && (
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">Risk highlights</CardTitle>
                <CardDescription className="text-xs">From model section 2 (citation-bearing bullets).</CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-1.5">
                {parsed.riskHints.map((line, i) => (
                  <div key={i} className="text-xs text-slate-800 border-l-2 border-teal-500/50 pl-2 line-clamp-3" title={line}>
                    {line}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-base">Similar Jira tickets</CardTitle>
              <CardDescription className="text-xs">
                {ui
                  ? 'Structured learning view; aligns with backend uac_ui.similar_jira_learning_cards.'
                  : 'Hybrid retrieval scores and similarity rationale.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 space-y-2">
              {(ui?.similar_jira_learning_cards?.length ?? 0) > 0
                ? ui!.similar_jira_learning_cards.map((s) => {
                    const finals = typeof s.scores?.final === 'number' ? s.scores.final : undefined;
                    return (
                      <div
                        key={s.jira_key}
                        className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm flex flex-col gap-1.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-sm font-semibold text-teal-800">{s.jira_key}</span>
                          <div className="flex flex-wrap gap-1">
                            {s.confidence_score != null ? (
                              <Badge variant="secondary" className="text-[10px]">
                                conf {Number(s.confidence_score).toFixed(2)}
                              </Badge>
                            ) : null}
                            {finals != null ? (
                              <Badge variant="secondary" className="text-[10px]">
                                final {finals.toFixed(3)}
                              </Badge>
                            ) : null}
                          </div>
                        </div>
                        <ClipText text={s.title || ''} className="font-medium" />
                        <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={s.why_relevant}>
                          <span className="font-semibold text-slate-700">Why relevant: </span>
                          {s.why_relevant || '—'}
                        </p>
                        {s.what_we_learned ? (
                          <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={s.what_we_learned}>
                            <span className="font-semibold text-slate-700">Learned: </span>
                            {s.what_we_learned}
                          </p>
                        ) : null}
                      </div>
                    );
                  })
                : (result.similar_jiras || []).length === 0 ? (
                    <p className="text-xs text-slate-500">None retrieved. Index Jira QA chunks or adjust filters.</p>
                  ) : (
                    (result.similar_jiras || []).map((s) => (
                      <div
                        key={s.jira_key}
                        className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm flex flex-col gap-1.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-sm font-semibold text-teal-800">{s.jira_key}</span>
                          <div className="flex flex-wrap gap-1">
                            {s.confidence_score != null ? (
                              <Badge variant="secondary" className="text-[10px]">
                                conf {s.confidence_score.toFixed(2)}
                              </Badge>
                            ) : null}
                            <Badge variant="secondary" className="text-[10px]">
                              final {(s.scores?.final ?? 0).toFixed(3)}
                            </Badge>
                            <Badge variant="outline" className="text-[10px] font-normal">
                              v {(s.scores?.vector ?? 0).toFixed(2)}
                            </Badge>
                          </div>
                        </div>
                        <ClipText text={s.summary || s.title || ''} className="font-medium" />
                        {(s.matching_outputs?.length || s.matching_entities?.length) ? (
                          <p className="text-[10px] text-slate-600 line-clamp-2">
                            {s.matching_outputs?.length ? (
                              <span>
                                <span className="font-semibold text-slate-700">Outputs: </span>
                                {(s.matching_outputs || []).join(', ')}
                              </span>
                            ) : null}
                            {s.matching_outputs?.length && s.matching_entities?.length ? ' · ' : null}
                            {s.matching_entities?.length ? (
                              <span>
                                <span className="font-semibold text-slate-700">Entities: </span>
                                {(s.matching_entities || []).join(', ')}
                              </span>
                            ) : null}
                          </p>
                        ) : null}
                        <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={s.why_similar}>
                          <span className="font-semibold text-slate-700">Similarity: </span>
                          {s.why_similar || '—'}
                        </p>
                        {s.what_we_learned ? (
                          <p className="text-[11px] text-slate-600 leading-snug line-clamp-2" title={s.what_we_learned}>
                            <span className="font-semibold text-slate-700">Learned: </span>
                            {s.what_we_learned}
                          </p>
                        ) : null}
                        {s.document_excerpt ? (
                          <details className="text-[10px] text-slate-500">
                            <summary className="cursor-pointer text-teal-700 font-medium">Chunk excerpt</summary>
                            <pre className="mt-1 whitespace-pre-wrap font-sans text-slate-600 max-h-24 overflow-y-auto">
                              {s.document_excerpt}
                            </pre>
                          </details>
                        ) : null}
                      </div>
                    ))
                  )}
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-base">Must-test scenarios</CardTitle>
              <CardDescription className="text-xs">
                {ui?.must_test_scenario_table?.rows?.length
                  ? 'From structured API (uac_ui.must_test_scenario_table).'
                  : 'Evidence columns split from the model when "current:" / "similar:" markers exist.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 overflow-x-auto">
              {(ui?.must_test_scenario_table?.rows?.length ?? 0) > 0 ? (
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-2 font-semibold">Scenario</th>
                      <th className="py-2 pr-2 font-semibold">Why</th>
                      <th className="py-2 pr-2 font-semibold">Evidence</th>
                      <th className="py-2 pr-2 font-semibold">Layer</th>
                      <th className="py-2 font-semibold">Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ui!.must_test_scenario_table.rows.map((row) => (
                      <tr key={row.id} className="border-b border-slate-100 align-top">
                        <td className="py-2 pr-2">
                          <ClipText text={row.scenario} />
                        </td>
                        <td className="py-2 pr-2">
                          <ClipText text={row.why || ''} />
                        </td>
                        <td className="py-2 pr-2">
                          <ClipText text={row.evidence || ''} />
                        </td>
                        <td className="py-2 pr-2">
                          <Badge variant="outline" className="text-[10px] font-normal whitespace-nowrap">
                            {row.test_layer || '—'}
                          </Badge>
                        </td>
                        <td className="py-2">
                          <Badge variant="secondary" className="text-[10px] font-normal whitespace-nowrap">
                            {row.priority || '—'}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : parsed.scenarios.length === 0 ? (
                <p className="text-xs text-slate-500">No fenced scenarios parsed. See full markdown below.</p>
              ) : (
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-2 font-semibold w-[14%]">Scenario</th>
                      <th className="py-2 pr-2 font-semibold w-[18%]">Why</th>
                      <th className="py-2 pr-2 font-semibold w-[22%]">Current Jira evidence</th>
                      <th className="py-2 pr-2 font-semibold w-[22%]">Similar Jira evidence</th>
                      <th className="py-2 font-semibold w-[10%]">Layer</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.scenarios.map((row, i) => (
                      <tr key={i} className="border-b border-slate-100 align-top">
                        <td className="py-2 pr-2">
                          <ClipText text={row.scenario} />
                        </td>
                        <td className="py-2 pr-2">
                          <ClipText text={row.why} />
                        </td>
                        <td className="py-2 pr-2">
                          <ClipText text={row.currentEvidence} />
                        </td>
                        <td className="py-2 pr-2">
                          <ClipText text={row.similarEvidence} />
                        </td>
                        <td className="py-2">
                          <Badge variant="outline" className="text-[10px] font-normal whitespace-nowrap">
                            {row.testLayer}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-base">Missing clarifications</CardTitle>
              <CardDescription className="text-xs">
                {(ui?.missing_clarification_table?.rows?.length ?? 0) > 0
                  ? 'Structured questions from uac_ui.'
                  : 'Parsed from markdown when structured rows are empty.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 overflow-x-auto">
              {(ui?.missing_clarification_table?.rows?.length ?? 0) > 0 ? (
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-2 font-semibold">Question</th>
                      <th className="py-2 pr-2 font-semibold">Why</th>
                      <th className="py-2 font-semibold">Entity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ui!.missing_clarification_table.rows.map((row) => (
                      <tr key={row.id} className="border-b border-slate-100 align-top">
                        <td className="py-2 pr-2 text-slate-800">{row.question}</td>
                        <td className="py-2 pr-2">
                          <ClipText text={row.why || ''} />
                        </td>
                        <td className="py-2 text-slate-600">{row.related_entity || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : parsed.missing.length === 0 ? (
                <p className="text-xs text-slate-500">None listed.</p>
              ) : (
                <ul className="list-disc pl-4 space-y-1 text-xs text-slate-800">
                  {parsed.missing.map((q, i) => (
                    <li key={i} className="line-clamp-2" title={q}>
                      {q}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {(ui?.automation_strategy_card || parsed.automation) && (
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">Automation fit</CardTitle>
                {ui?.automation_strategy_card ? (
                  <CardDescription className="text-xs">From uac_ui.automation_strategy_card.</CardDescription>
                ) : null}
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 grid gap-2 sm:grid-cols-2 text-xs">
                {ui?.automation_strategy_card ? (
                  <>
                    <div>
                      <span className="text-slate-500">Fit</span>
                      <p className="font-medium text-slate-900">{ui.automation_strategy_card.fit}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Primary layer</span>
                      <p className="font-medium text-slate-900">{ui.automation_strategy_card.primary_test_layer || '—'}</p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-slate-500">Framework / reason</span>
                      <p className="text-slate-800 line-clamp-4 mt-0.5" title={ui.automation_strategy_card.framework}>
                        {ui.automation_strategy_card.framework || '—'}
                      </p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-slate-500">Suggested test name</span>
                      <p className="font-mono text-xs text-teal-900 bg-teal-50/60 rounded px-2 py-1 mt-0.5 inline-block">
                        {ui.automation_strategy_card.suggested_test_name}
                      </p>
                    </div>
                  </>
                ) : parsed.automation ? (
                  <>
                    <div>
                      <span className="text-slate-500">Fit</span>
                      <p className="font-medium text-slate-900">{parsed.automation.fit}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Best layer</span>
                      <p className="font-medium text-slate-900">{parsed.automation.bestLayer}</p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-slate-500">Reason</span>
                      <p className="text-slate-800 line-clamp-3 mt-0.5" title={parsed.automation.reason}>
                        {parsed.automation.reason}
                      </p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-slate-500">Suggested test name</span>
                      <p className="font-mono text-xs text-teal-900 bg-teal-50/60 rounded px-2 py-1 mt-0.5 inline-block">
                        {parsed.automation.suggestedTestName}
                      </p>
                    </div>
                  </>
                ) : null}
              </CardContent>
            </Card>
          )}

          {ui?.dataset_recommendation_card &&
            (ui.dataset_recommendation_card.items.length > 0 ||
              ui.dataset_recommendation_card.hints_from_guardrails.length > 0 ||
              ui.dataset_recommendation_card.insufficient_similar_pool) ? (
            <Card className="border-slate-200 shadow-sm border-dashed">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">Dataset &amp; fixture hints</CardTitle>
                <CardDescription className="text-xs">Grounded recommendations for regression data and fixtures.</CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-2 text-xs">
                {ui.dataset_recommendation_card.insufficient_similar_pool ? (
                  <p className="rounded-md bg-amber-50 border border-amber-100 px-2 py-1.5 text-amber-950">
                    Similar-ticket pool is thin—consider extra labelled content before freezing fixtures.
                  </p>
                ) : null}
                {ui.dataset_recommendation_card.items.map((line, i) => (
                  <p key={i} className="text-slate-800 leading-snug border-l-2 border-teal-400/50 pl-2">
                    {line}
                  </p>
                ))}
                {ui.dataset_recommendation_card.hints_from_guardrails.map((h, i) => (
                  <p key={`g-${i}`} className="text-slate-600">
                    <span className="font-semibold text-slate-700">Guardrail: </span>
                    {h}
                  </p>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {ui?.qa_handoff_card?.requested ? (
            <Card className="border-indigo-200/80 shadow-sm ring-1 ring-indigo-500/10 bg-indigo-50/20">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">QA handoff plan</CardTitle>
                <CardDescription className="text-xs">
                  Second LLM pass on the finalized brief—use for smoke vs deep scope, exit criteria, and pasteable Jira
                  steps. Grounded in the same ticket evidence as the main UAC.
                </CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-3 text-xs">
                {!ui.qa_handoff_card.generated ? (
                  <p className="rounded-md border border-amber-200 bg-amber-50/80 px-2 py-1.5 text-amber-950">
                    {ui.qa_handoff_card.note || 'QA handoff did not complete—check LLM configuration or retry.'}
                  </p>
                ) : null}
                {ui.qa_handoff_card.generated && ui.qa_handoff_card.regression_breadth ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-slate-600">Regression breadth</span>
                    <Badge variant="secondary" className="text-[10px] capitalize">
                      {ui.qa_handoff_card.regression_breadth}
                    </Badge>
                  </div>
                ) : null}
                {(ui.qa_handoff_card.smoke_checks?.length ?? 0) > 0 ? (
                  <div>
                    <p className="font-semibold text-slate-800 mb-1">Smoke / sanity</p>
                    <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                      {ui.qa_handoff_card.smoke_checks!.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(ui.qa_handoff_card.deep_regression_focus?.length ?? 0) > 0 ? (
                  <div>
                    <p className="font-semibold text-slate-800 mb-1">Deep regression focus</p>
                    <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                      {ui.qa_handoff_card.deep_regression_focus!.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(ui.qa_handoff_card.blocking_for_signoff?.length ?? 0) > 0 ? (
                  <div>
                    <p className="font-semibold text-slate-800 mb-1">Blocking before sign-off</p>
                    <ul className="space-y-1.5">
                      {ui.qa_handoff_card.blocking_for_signoff!.map((b, i) => (
                        <li key={i} className="flex flex-wrap items-start gap-2">
                          <Badge variant="outline" className="text-[9px] shrink-0 uppercase">
                            {b.owner_role}
                          </Badge>
                          <span className="text-slate-800">{b.question}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(ui.qa_handoff_card.exit_criteria?.length ?? 0) > 0 ? (
                  <div>
                    <p className="font-semibold text-slate-800 mb-1">Exit criteria</p>
                    <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                      {ui.qa_handoff_card.exit_criteria!.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(ui.qa_handoff_card.exploratory_angles?.length ?? 0) > 0 ? (
                  <div>
                    <p className="font-semibold text-slate-800 mb-1">Exploratory / edge angles</p>
                    <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                      {ui.qa_handoff_card.exploratory_angles!.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {ui.qa_handoff_card.jira_test_script &&
                (ui.qa_handoff_card.jira_test_script.title ||
                  (ui.qa_handoff_card.jira_test_script.steps?.length ?? 0) > 0) ? (
                  <div className="rounded-lg border border-slate-200 bg-white p-3 space-y-2">
                    <p className="font-semibold text-slate-800">Jira test outline</p>
                    {ui.qa_handoff_card.jira_test_script.title ? (
                      <p className="font-medium text-slate-900">{ui.qa_handoff_card.jira_test_script.title}</p>
                    ) : null}
                    {(ui.qa_handoff_card.jira_test_script.preconditions?.length ?? 0) > 0 ? (
                      <div>
                        <span className="text-slate-500">Preconditions</span>
                        <ol className="list-decimal list-inside mt-0.5 space-y-0.5 text-slate-700">
                          {ui.qa_handoff_card.jira_test_script.preconditions!.map((p, i) => (
                            <li key={i}>{p}</li>
                          ))}
                        </ol>
                      </div>
                    ) : null}
                    {(ui.qa_handoff_card.jira_test_script.steps?.length ?? 0) > 0 ? (
                      <div>
                        <span className="text-slate-500">Steps</span>
                        <ol className="list-decimal list-inside mt-0.5 space-y-0.5 text-slate-700">
                          {ui.qa_handoff_card.jira_test_script.steps!.map((p, i) => (
                            <li key={i}>{p}</li>
                          ))}
                        </ol>
                      </div>
                    ) : null}
                    {ui.qa_handoff_card.jira_test_script.expected_result ? (
                      <div>
                        <span className="text-slate-500">Expected</span>
                        <p className="text-slate-800 mt-0.5 whitespace-pre-wrap">
                          {ui.qa_handoff_card.jira_test_script.expected_result}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {ui.qa_handoff_card.qa_lead_note ? (
                  <p className="text-slate-700 border-t border-indigo-100 pt-2 italic">{ui.qa_handoff_card.qa_lead_note}</p>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {ui?.confidence_warnings_card ? (
            <Card
              className={cn(
                'border-slate-200 shadow-sm',
                !ui.confidence_warnings_card.uac_validation_ok && 'border-amber-300 ring-1 ring-amber-200/50'
              )}
            >
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">Confidence &amp; checks</CardTitle>
                <CardDescription className="text-xs">Validation, claim verifier, and guardrails summary.</CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-3 text-xs">
                <div className="flex flex-wrap gap-2">
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[10px]',
                      ui.confidence_warnings_card.uac_validation_ok
                        ? 'border-slate-200'
                        : 'border-red-300 bg-red-50 text-red-900'
                    )}
                  >
                    Validation {ui.confidence_warnings_card.uac_validation_ok ? 'OK' : 'issues'}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    Claims dropped {ui.confidence_warnings_card.claim_verification.dropped_count} · downgraded{' '}
                    {ui.confidence_warnings_card.claim_verification.downgraded_count} · unsupported{' '}
                    {ui.confidence_warnings_card.claim_verification.unsupported_count}
                  </Badge>
                  {ui.confidence_warnings_card.blocked_claims_count > 0 ? (
                    <Badge variant="secondary" className="text-[10px]">
                      Guardrails blocked {ui.confidence_warnings_card.blocked_claims_count}
                    </Badge>
                  ) : null}
                </div>
                {(ui.confidence_warnings_card.uac_validation_errors?.length ?? 0) > 0 ? (
                  <ul className="list-disc list-inside text-amber-900 space-y-0.5">
                    {ui.confidence_warnings_card.uac_validation_errors.slice(0, 8).map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                ) : null}
                {(ui.confidence_warnings_card.guardrails_warnings?.length ?? 0) > 0 ? (
                  <div>
                    <p className="font-semibold text-slate-700 mb-1">Guardrail warnings</p>
                    <ul className="space-y-1 text-slate-700">
                      {ui.confidence_warnings_card.guardrails_warnings.map((w, i) => (
                        <li key={i}>
                          {w.message || w.code || '—'}
                          {w.detail ? <span className="text-slate-500"> — {w.detail}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {(result.dropped_generic_points || []).length > 0 && (
            <Card className="border-amber-200 bg-amber-50/30 shadow-sm">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base text-amber-950">Filtered points (evidence gate)</CardTitle>
                <CardDescription className="text-xs text-amber-900/90">Removed as generic or weakly grounded.</CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-1">
                {result.dropped_generic_points!.map((d, i) => (
                  <div key={i} className="text-[11px] text-amber-950 border-b border-amber-100/80 pb-1 last:border-0">
                    <span className="line-clamp-2" title={d.text}>
                      {d.text}
                    </span>
                    <Badge variant="outline" className="mt-1 text-[9px] font-normal border-amber-300">
                      {d.reason}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {(ui?.debug_accordion?.anti_repetition ?? result.anti_repetition) ? (
            <AntiRepetitionPanel meta={(ui?.debug_accordion?.anti_repetition ?? result.anti_repetition)!} />
          ) : null}

          {ui?.debug_accordion &&
          (ui.debug_accordion.debug_mode ||
            ui.debug_accordion.claim_verification_detail ||
            ui.debug_accordion.uac_guardrails_detail ||
            (ui.debug_accordion.dropped_generic_points?.length ?? 0) > 0 ||
            (ui.debug_accordion.generic_phrases_removed?.length ?? 0) > 0) ? (
            <details className="group rounded-xl border border-violet-100 bg-violet-50/15 shadow-sm open:shadow">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold text-slate-800">
                <span>Pipeline debug (structured)</span>
                <ChevronDown className="w-4 h-4 shrink-0 transition group-open:rotate-180 text-slate-500" />
              </summary>
              <div className="border-t border-violet-100/80 px-4 py-3 space-y-3 text-xs">
                <p className="text-slate-600">
                  Debug mode: <strong>{ui.debug_accordion.debug_mode ? 'on' : 'off'}</strong>
                  {ui.debug_accordion.regeneration_used != null
                    ? ` · regeneration: ${ui.debug_accordion.regeneration_used ? 'yes' : 'no'}`
                    : ''}
                  {ui.debug_accordion.structured_uac_available != null
                    ? ` · structured_uac: ${ui.debug_accordion.structured_uac_available ? 'yes' : 'no'}`
                    : ''}
                </p>
                {ui.debug_accordion.retrieval_debug &&
                typeof ui.debug_accordion.retrieval_debug === 'object' &&
                'note' in ui.debug_accordion.retrieval_debug ? (
                  <p className="text-slate-600 italic">
                    {(ui.debug_accordion.retrieval_debug as { note?: string }).note}
                  </p>
                ) : null}
                {(ui.debug_accordion.generic_phrases_removed?.length ?? 0) > 0 ? (
                  <div>
                    <span className="font-semibold text-slate-700">Generic phrases removed (patterns)</span>
                    <ul className="list-disc pl-4 mt-1 font-mono text-[10px] text-slate-600">
                      {ui.debug_accordion.generic_phrases_removed!.slice(0, 20).map((p, i) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(ui.debug_accordion.dropped_generic_points?.length ?? 0) > 0 ? (
                  <div>
                    <span className="font-semibold text-slate-700">Dropped points (critic/evidence)</span>
                    <ul className="mt-1 space-y-1">
                      {ui.debug_accordion.dropped_generic_points!.map((d, i) => (
                        <li key={i} className="text-slate-700">
                          <span className="line-clamp-2">{d.text}</span>{' '}
                          <Badge variant="outline" className="text-[9px] ml-1">
                            {d.reason}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {ui.debug_accordion.claim_verification_detail ? (
                  <div>
                    <span className="font-semibold text-slate-700">Claim verification (raw)</span>
                    <pre className="mt-1 max-h-40 overflow-auto rounded bg-white border border-slate-100 p-2 text-[10px]">
                      {JSON.stringify(ui.debug_accordion.claim_verification_detail, null, 2)}
                    </pre>
                  </div>
                ) : null}
                {ui.debug_accordion.uac_guardrails_detail ? (
                  <div>
                    <span className="font-semibold text-slate-700">Guardrails (raw)</span>
                    <pre className="mt-1 max-h-40 overflow-auto rounded bg-white border border-slate-100 p-2 text-[10px]">
                      {JSON.stringify(ui.debug_accordion.uac_guardrails_detail, null, 2)}
                    </pre>
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}

          <details className="group rounded-xl border border-slate-200 bg-white shadow-sm open:shadow">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold text-slate-800">
              <span>Retrieval debug</span>
              <ChevronDown className="w-4 h-4 shrink-0 transition group-open:rotate-180 text-slate-500" />
            </summary>
            <div className="border-t border-slate-100 px-4 py-3 space-y-3 text-xs">
              <div>
                <span className="text-slate-500 font-semibold">Query domain</span>
                <p className="font-mono text-slate-800">{result.retrieval_debug?.domain ?? '—'}</p>
              </div>
              <div>
                <span className="text-slate-500 font-semibold">Entities</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(result.retrieval_debug?.entities || []).map((e) => (
                    <Badge key={e} variant="secondary" className="text-[10px] font-normal">
                      {e}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-slate-500 font-semibold">Outputs</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(result.retrieval_debug?.outputs || []).map((e) => (
                    <Badge key={e} variant="outline" className="text-[10px] font-normal">
                      {e}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="overflow-x-auto">
                <span className="text-slate-500 font-semibold block mb-1">Score breakdown</span>
                <table className="w-full text-[11px] border-collapse">
                  <thead>
                    <tr className="border-b text-left text-slate-500">
                      <th className="py-1 pr-2">Key</th>
                      <th className="py-1 pr-2">Final</th>
                      <th className="py-1 pr-2">Vector</th>
                      <th className="py-1 pr-2">Keyword</th>
                      <th className="py-1">Meta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.retrieval_debug?.scores || []).map((sc) => (
                      <tr key={sc.jira_key} className="border-b border-slate-50">
                        <td className="py-1 pr-2 font-mono">{sc.jira_key}</td>
                        <td className="py-1 pr-2">{Number(sc.final).toFixed(4)}</td>
                        <td className="py-1 pr-2">{Number(sc.vector).toFixed(4)}</td>
                        <td className="py-1 pr-2">{Number(sc.keyword).toFixed(4)}</td>
                        <td className="py-1">{Number(sc.metadata).toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </details>

          {result.uac_answer ? (
            <details className="rounded-lg border border-slate-200 bg-slate-50/50">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-600">
                Full UAC markdown (reference)
              </summary>
              <pre className="max-h-64 overflow-auto px-3 pb-3 text-[10px] text-slate-700 whitespace-pre-wrap font-mono">
                {result.uac_answer}
              </pre>
            </details>
          ) : null}

            </div> {/* end full-analysis collapsible body */}
          </details> {/* end full-analysis collapsible */}

        </div>
      )}
    </div>
  );
}

export default UacCopilotPage;
