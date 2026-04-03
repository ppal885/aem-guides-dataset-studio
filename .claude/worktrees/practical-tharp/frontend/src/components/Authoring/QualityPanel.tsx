import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertCircle,
  BarChart2,
  BookOpen,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  ExternalLink,
  FileSearch,
  Layers,
  RefreshCw,
  Sparkles,
  Wand2,
} from 'lucide-react'
import type { JiraIssue, GeneratedDita } from '../../pages/AuthoringPage'
import type { ResearchContext } from './QueryPlanPanel'
import { withTenantHeaders } from '@/utils/api'

const API_BASE = '/api/v1'

interface SmartSuggestion {
  id: string
  severity: 'error' | 'warning' | 'info'
  section: string
  title: string
  why: string
  before: string
  after: string
  fix_type: string
  fix_prompt?: string
  confidence: number
  rule_id: string
  impact?: string
  evidence?: string[]
}

interface SuggestionReport {
  total: number
  errors: number
  warnings: number
  suggestions: SmartSuggestion[]
  score_delta: number
  refine_completions: string[]
  error?: string
}

interface Props {
  dita: GeneratedDita | null
  issue: JiraIssue | null
  researchContext?: ResearchContext | null
  onRegenerate?: () => void
  onDitaUpdated?: (dita: GeneratedDita) => void
}

interface FeedbackState {
  tone: 'success' | 'warning' | 'error'
  text: string
}

export function QualityPanel({ dita, issue, researchContext, onRegenerate, onDitaUpdated }: Props) {
  const [reindexing, setReindexing] = useState(false)
  const [posting, setPosting] = useState(false)
  const [postDone, setPostDone] = useState(false)
  const [suggestions, setSuggestions] = useState<SuggestionReport | null>(null)
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [suggestionsError, setSuggestionsError] = useState('')
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [fixingAll, setFixingAll] = useState(false)
  const [feedback, setFeedback] = useState<FeedbackState | null>(null)
  const [showAllSuggestions, setShowAllSuggestions] = useState(false)
  const [showValidation, setShowValidation] = useState(false)
  const [showContextDetails, setShowContextDetails] = useState(false)
  const [showActions, setShowActions] = useState(false)

  const persistUpdatedXml = useCallback(
    async (xml: string, comment: string) => {
      if (!dita || !onDitaUpdated) {
        return null
      }

      const evaluateResponse = await fetch(`${API_BASE}/ai/evaluate-dita`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          filename: dita.filename,
          content: xml,
        }),
      })
      const evaluated = await evaluateResponse.json()
      if (!evaluateResponse.ok || evaluated.error) {
        throw new Error(evaluated.error || 'Failed to evaluate updated DITA')
      }

      if (issue) {
        await fetch(`${API_BASE}/safety/save-version`, {
          method: 'POST',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            issue_key: issue.issue_key,
            filename: evaluated.filename,
            content: evaluated.content,
            author: 'author',
            action: 'edited',
            comment,
          }),
        })
      }

      onDitaUpdated(evaluated)
      return evaluated as GeneratedDita
    },
    [dita, issue, onDitaUpdated],
  )

  useEffect(() => {
    setFeedback(null)
    setShowAllSuggestions(false)
    setShowValidation(Boolean(dita?.validation?.some(check => !check.passing)))
  }, [dita?.filename, dita?.content])

  const loadSuggestions = useCallback(async () => {
    if (!dita || !issue) {
      setSuggestions(null)
      setSuggestionsError('')
      return
    }

    setSuggestionsLoading(true)
    setSuggestionsError('')
    setFeedback(null)
    try {
      const response = await fetch(`${API_BASE}/smart/analyse`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          xml: dita.content,
          issue,
          research_context: researchContext,
          validation: dita.validation,
          quality_breakdown: dita.quality_breakdown,
        }),
      })
      const data: SuggestionReport = await response.json()
      if (!response.ok || data.error) {
        throw new Error(data.error || 'Failed to analyse smart suggestions')
      }
      setSuggestions(data)
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Failed to analyse smart suggestions'
      setSuggestionsError(message)
      setSuggestions(null)
    } finally {
      setSuggestionsLoading(false)
    }
  }, [dita, issue, researchContext])

  useEffect(() => {
    void loadSuggestions()
  }, [loadSuggestions])

  const handlePostToJira = useCallback(async () => {
    if (!issue || !dita) {
      return
    }
    setPosting(true)
    try {
      await fetch(`${API_BASE}/jira/comment`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          issue_key: issue.issue_key,
          comment: `DITA generated\nFile: ${dita.filename}\nQuality: ${dita.quality_score}/100\nGenerated by AEM Guides Dataset Studio`,
        }),
      })
      setPostDone(true)
      window.setTimeout(() => setPostDone(false), 3000)
    } catch (error) {
      console.error(error)
    } finally {
      setPosting(false)
    }
  }, [dita, issue])

  const handleIndexExample = useCallback(async () => {
    if (!dita) {
      return
    }
    setReindexing(true)
    try {
      await fetch(`${API_BASE}/ai/index-dita-example`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          filename: dita.filename,
          content: dita.content,
          topic_type: dita.dita_type,
        }),
      })
    } catch (error) {
      console.error(error)
    } finally {
      setReindexing(false)
    }
  }, [dita])

  const handleApplySuggestion = useCallback(
    async (suggestion: SmartSuggestion) => {
      if (!dita || !issue) {
        return
      }

      setApplyingId(suggestion.id)
      setSuggestionsError('')
      setFeedback(null)
      try {
        const response = await fetch(`${API_BASE}/smart/apply-fix`, {
          method: 'POST',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          xml: dita.content,
          issue,
          suggestion,
          research_context: researchContext,
          validation: dita.validation,
          quality_breakdown: dita.quality_breakdown,
        }),
      })
        const data = await response.json()
        if (!response.ok || data.error) {
          throw new Error(data.error || 'Failed to apply suggestion')
        }
        const nextXml = typeof data.xml === 'string' ? data.xml.trim() : ''
        if (nextXml && nextXml !== dita.content) {
          const updated = await persistUpdatedXml(nextXml, `Smart suggestion applied: ${suggestion.title}`)
          setFeedback({
            tone: 'success',
            text: updated
              ? `Applied "${suggestion.title}" and refreshed the review state.`
              : `Applied "${suggestion.title}".`,
          })
        } else {
          setFeedback({
            tone: 'warning',
            text: `No XML change was produced for "${suggestion.title}" yet.`,
          })
        }
      } catch (caughtError) {
        const message = caughtError instanceof Error ? caughtError.message : 'Failed to apply suggestion'
        setSuggestionsError(message)
        setFeedback({ tone: 'error', text: message })
      } finally {
        setApplyingId(null)
      }
    },
    [dita, issue, persistUpdatedXml, researchContext],
  )

  const handleFixAll = useCallback(async () => {
    if (!dita || !issue) {
      return
    }

    setFixingAll(true)
    setSuggestionsError('')
    setFeedback(null)
    try {
      const response = await fetch(`${API_BASE}/smart/fix-all`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          xml: dita.content,
          issue,
          research_context: researchContext,
          validation: dita.validation,
          quality_breakdown: dita.quality_breakdown,
        }),
      })
      const data = await response.json()
      if (!response.ok || data.error) {
        throw new Error(data.error || 'Failed to fix suggestions')
      }
      const nextXml = typeof data.xml === 'string' ? data.xml.trim() : ''
      if (nextXml && nextXml !== dita.content) {
        await persistUpdatedXml(nextXml, `Smart suggestions fix-all applied (${data.fixed_count || 0} fixes)`)
        setFeedback({
          tone: 'success',
          text: `Applied ${data.fixed_count || 0} suggestion${data.fixed_count === 1 ? '' : 's'} and refreshed the XML.`,
        })
      } else {
        setFeedback({
          tone: 'warning',
          text: data.fixed_count
            ? 'Suggestions were processed, but the XML did not change.'
            : 'No automatic fixes were available for the current suggestions.',
        })
      }
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Failed to fix suggestions'
      setSuggestionsError(message)
      setFeedback({ tone: 'error', text: message })
    } finally {
      setFixingAll(false)
    }
  }, [dita, issue, persistUpdatedXml, researchContext])

  const suggestionSummary = useMemo(() => {
    if (!suggestions) {
      return null
    }
    return `${suggestions.total} suggestions / +${suggestions.score_delta} possible score`
  }, [suggestions])

  if (!dita) {
    return (
      <div className="p-4">
        <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Quality</p>
        <div className="py-8 text-center">
          <BarChart2 className="mx-auto mb-2 h-8 w-8 text-gray-300" />
          <p className="text-xs text-gray-400">Generate DITA to see quality scoring and validation.</p>
        </div>
      </div>
    )
  }

  const score = dita.quality_score
  const scoreColor = score >= 80 ? 'text-emerald-600' : score >= 60 ? 'text-amber-600' : 'text-red-500'
  const scoreBackground = score >= 80 ? 'bg-emerald-50' : score >= 60 ? 'bg-amber-50' : 'bg-red-50'
  const scoreLabel = score >= 80 ? 'Excellent' : score >= 60 ? 'Good' : 'Needs work'
  const breakdown = dita.quality_breakdown || {
    structure: 0,
    content_richness: 0,
    dita_features: 0,
    aem_readiness: 0,
  }
  const validationFailures = dita.validation?.filter(validation => !validation.passing) || []
  const visibleSuggestions = suggestions?.suggestions.slice(0, showAllSuggestions ? suggestions.suggestions.length : 4) || []
  const hiddenSuggestionCount = Math.max((suggestions?.suggestions.length || 0) - visibleSuggestions.length, 0)
  const reviewStats = [
    { label: 'Suggestions', value: String(suggestions?.total || 0), tone: suggestions?.total ? 'blue' : 'gray' as const },
    {
      label: 'Validation',
      value: validationFailures.length ? `${validationFailures.length} open` : 'Clean',
      tone: validationFailures.length ? 'amber' : 'emerald' as const,
    },
    { label: 'Sources', value: String(dita.sources_used?.length || 0), tone: 'gray' as const },
  ]

  return (
    <div className="space-y-4 p-4 pb-6">
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Review summary</p>
            <p className="mt-1 text-sm font-medium text-slate-900">Focus on the highest-signal fixes first.</p>
          </div>
          <div className={`rounded-2xl px-3 py-2 ${scoreBackground}`}>
            <div className="flex items-baseline gap-1">
              <span className={`text-3xl font-semibold ${scoreColor}`}>{score}</span>
              <span className="text-sm text-slate-400">/100</span>
            </div>
            <p className={`mt-0.5 text-right text-[11px] font-medium ${scoreColor}`}>{scoreLabel}</p>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          {reviewStats.map(stat => (
            <InfoCard key={stat.label} label={stat.label} value={stat.value} tone={stat.tone} />
          ))}
        </div>

        <div className="mt-4 space-y-2">
          <ScoreRow label="Structure" value={breakdown.structure} max={30} />
          <ScoreRow label="Content richness" value={breakdown.content_richness} max={30} />
          <ScoreRow label="DITA features" value={breakdown.dita_features} max={20} />
          <ScoreRow label="AEM readiness" value={breakdown.aem_readiness} max={20} />
        </div>
      </div>

      {feedback ? (
        <InlineNotice tone={feedback.tone} text={feedback.text} />
      ) : null}

      {suggestionsError ? <InlineNotice tone="error" text={suggestionsError} /> : null}

      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Top fixes</p>
            <p className="mt-1 text-sm text-slate-600">
              {suggestionSummary || 'Review the strongest improvements for this topic.'}
            </p>
          </div>
          <button
            onClick={() => void loadSuggestions()}
            disabled={suggestionsLoading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${suggestionsLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {suggestionsLoading ? (
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-500">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            Analysing structure, reuse, validation, and research coverage...
          </div>
        ) : null}

        {!suggestionsLoading && suggestions && suggestions.total === 0 ? (
          <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-700">
            No immediate smart suggestions. The topic looks clean against the current rule set.
          </div>
        ) : null}

        {!suggestionsLoading && suggestions && suggestions.total > 0 ? (
          <div className="mt-3 space-y-3">
            {suggestions.errors + suggestions.warnings > 0 ? (
              <button
                onClick={handleFixAll}
                disabled={fixingAll}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2.5 text-xs font-medium text-violet-700 transition-colors hover:bg-violet-100 disabled:opacity-50"
              >
                {fixingAll ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                {fixingAll ? 'Applying fixes...' : `Apply all high-priority fixes (${suggestions.errors + suggestions.warnings})`}
              </button>
            ) : null}

            {visibleSuggestions.map(suggestion => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                applying={applyingId === suggestion.id}
                onApply={() => void handleApplySuggestion(suggestion)}
              />
            ))}

            {hiddenSuggestionCount > 0 ? (
              <button
                onClick={() => setShowAllSuggestions(current => !current)}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
              >
                {showAllSuggestions ? 'Show fewer suggestions' : `Show ${hiddenSuggestionCount} more suggestion${hiddenSuggestionCount === 1 ? '' : 's'}`}
              </button>
            ) : null}

            {suggestions.refine_completions.length ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Refine ideas</p>
                <div className="flex flex-wrap gap-1.5">
                  {suggestions.refine_completions.slice(0, 5).map(completion => (
                    <span key={completion} className="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600">
                      {completion}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <DetailSection
        title="Validation"
        summary={
          validationFailures.length
            ? `${validationFailures.length} validation item${validationFailures.length === 1 ? '' : 's'} still need attention`
            : 'All current validation checks are passing'
        }
        open={showValidation}
        onToggle={() => setShowValidation(current => !current)}
      >
        <div className="space-y-1.5">
          {dita.validation.map(validation => (
            <ValidationRow key={validation.label} label={validation.label} passing={validation.passing} />
          ))}
        </div>
      </DetailSection>

      <DetailSection
        title="Context"
        summary={
          researchContext
            ? `${researchContext.total_chunks} research chunks, ${dita.sources_used?.length || 0} source groups`
            : `${dita.sources_used?.length || 0} source groups available`
        }
        open={showContextDetails}
        onToggle={() => setShowContextDetails(current => !current)}
      >
        <div className="space-y-3">
          {researchContext ? (
            <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-indigo-700">{researchContext.total_chunks} context chunks</span>
                <span className="text-xs text-indigo-500">{researchContext.results.length} queries</span>
              </div>
              {researchContext.sources_used.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {researchContext.sources_used.map(source => (
                    <span key={source} className="rounded bg-white px-1.5 py-0.5 text-xs text-indigo-600">
                      {source}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {dita.sources_used?.length ? (
            <div className="space-y-2">
              {dita.sources_used.map(source => (
                <div key={`${source.label}-${source.count}`} className="flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
                  <SourceIcon label={source.label} />
                  <span className="flex-1 text-xs text-slate-600">{source.label}</span>
                  <span className="text-xs text-slate-400">{source.count}</span>
                </div>
              ))}
            </div>
          ) : null}

          <div className="border-t border-slate-200 pt-3">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">Output file</p>
            <p className="break-all font-mono text-xs text-slate-600">{dita.filename}</p>
            <p className="mt-1 text-xs text-slate-400">{dita.dita_type} topic / DITA 1.3</p>
          </div>
        </div>
      </DetailSection>

      <DetailSection
        title="Actions"
        summary="Regenerate, post, index, or refresh the review."
        open={showActions}
        onToggle={() => setShowActions(current => !current)}
      >
        <div className="space-y-2">
          {onRegenerate ? (
            <ActionButton icon={<RefreshCw className="h-3 w-3" />} label="Generate again" onClick={onRegenerate} />
          ) : null}
          <ActionButton
            icon={<ExternalLink className="h-3 w-3" />}
            label={postDone ? 'Posted to Jira' : posting ? 'Posting to Jira...' : 'Post summary to Jira'}
            onClick={handlePostToJira}
            disabled={posting}
          />
          <ActionButton
            icon={<FileSearch className="h-3 w-3" />}
            label={reindexing ? 'Indexing example...' : 'Index as example'}
            onClick={handleIndexExample}
            disabled={reindexing}
            tooltip="Add this topic to the example collection for future authoring."
          />
        </div>
      </DetailSection>
    </div>
  )
}

function ScoreRow({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="w-32 text-gray-500">{label}</span>
      <div className="flex items-center gap-2">
        <div className="h-1 w-16 overflow-hidden rounded-full bg-gray-200">
          <div className="h-full rounded-full bg-blue-400" style={{ width: `${(value / max) * 100}%` }} />
        </div>
        <span className="w-8 text-right font-medium text-gray-700">
          {value}/{max}
        </span>
      </div>
    </div>
  )
}

function ValidationRow({ label, passing }: { label: string; passing: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {passing ? (
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
      ) : (
        <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
      )}
      <span className={`text-xs ${passing ? 'text-gray-600' : 'text-amber-700'}`}>{label}</span>
    </div>
  )
}

function SuggestionBadge({ severity }: { severity: SmartSuggestion['severity'] }) {
  const styles: Record<SmartSuggestion['severity'], string> = {
    error: 'bg-red-50 text-red-700',
    warning: 'bg-amber-50 text-amber-700',
    info: 'bg-blue-50 text-blue-700',
  }

  return <span className={`rounded px-2 py-0.5 text-[11px] font-medium capitalize ${styles[severity]}`}>{severity}</span>
}

function SourceIcon({ label }: { label: string }) {
  const normalized = label.toLowerCase()
  if (normalized.includes('experience') || normalized.includes('league')) {
    return <BookOpen className="h-3.5 w-3.5 text-blue-500" />
  }
  if (normalized.includes('spec') || normalized.includes('dita')) {
    return <FileSearch className="h-3.5 w-3.5 text-emerald-500" />
  }
  return <Layers className="h-3.5 w-3.5 text-violet-500" />
}

function ActionButton({
  icon,
  label,
  onClick,
  disabled,
  tooltip,
}: {
  icon: ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
  tooltip?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={tooltip}
      className="flex w-full items-center gap-2 rounded-md border border-gray-200 px-3 py-2 text-left text-xs text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  )
}
