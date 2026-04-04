import { useState } from 'react'
import {
  Search, Code2, BookOpen, Bug, Star, Shield,
  Check, X, Edit2, Play, ChevronRight,
  RefreshCw, CheckCircle2, AlertCircle, Plus
} from 'lucide-react'
import { Button } from '../ui/button'
import type { JiraIssue } from '../../pages/AuthoringPage'

const API_BASE = '/api/v1'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ResearchQuery {
  id:       string
  category: string
  query:    string
  purpose:  string
  source:   'rag' | 'tavily' | 'both'
  approved: boolean
}

export interface QueryPlan {
  issue_key:     string
  issue_summary: string
  reasoning:     string
  queries:       ResearchQuery[]
}

export interface QueryResult {
  query_id:    string
  category:    string
  query:       string
  source:      string
  chunks:      string[]
  summary:     string
  urls:        string[]
  error:       string
  duration_ms: number
}

export interface ResearchContext {
  issue_key:    string
  results:      QueryResult[]
  completed_at: string
  total_chunks: number
  sources_used: string[]
}

interface Props {
  issue: JiraIssue
  onResearchComplete: (context: ResearchContext) => void
  onSkip: () => void
}

// ── Category config ───────────────────────────────────────────────────────────

const CATEGORY_CONFIG: Record<string, {
  label: string; color: string; bg: string; border: string; icon: any
}> = {
  dita_elements:  { label: 'DITA Elements',    color: 'text-blue-700',   bg: 'bg-blue-50',   border: 'border-blue-300',  icon: Code2    },
  aem_guides:     { label: 'AEM Guides',        color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-300',icon: BookOpen },
  bugs_fixes:     { label: 'Known Bugs & Fixes',color: 'text-red-700',    bg: 'bg-red-50',    border: 'border-red-300',   icon: Bug      },
  expert_examples:{ label: 'Expert Examples',   color: 'text-green-700',  bg: 'bg-green-50',  border: 'border-green-300', icon: Star     },
  dita_spec:      { label: 'DITA Spec Rules',   color: 'text-amber-700',  bg: 'bg-amber-50',  border: 'border-amber-300', icon: Shield   },
}

const SOURCE_LABELS: Record<string, string> = {
  rag:    'Local RAG',
  tavily: 'Web search',
  both:   'RAG + Web',
}

// ── Main component ────────────────────────────────────────────────────────────

export function QueryPlanPanel({ issue, onResearchComplete, onSkip }: Props) {
  const [plan, setPlan]           = useState<QueryPlan | null>(null)
  const [loading, setLoading]     = useState(false)
  const [executing, setExecuting] = useState(false)
  const [error, setError]         = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText]   = useState('')
  const [results, setResults]     = useState<ResearchContext | null>(null)
  const [execStep, setExecStep]   = useState<string>('')

  // ── Fetch query plan ────────────────────────────────────────────────────────
  const fetchPlan = async () => {
    setLoading(true)
    setError('')
    setResults(null)
    try {
      const res = await fetch(`${API_BASE}/jira/query-plan`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_key: issue.issue_key, issue }),
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setPlan(data)
    } catch (e: any) {
      setError(e.message || 'Failed to generate query plan')
    } finally {
      setLoading(false)
    }
  }

  // ── Toggle query approval ───────────────────────────────────────────────────
  const toggleQuery = (id: string) => {
    if (!plan) return
    setPlan({
      ...plan,
      queries: plan.queries.map(q =>
        q.id === id ? { ...q, approved: !q.approved } : q
      ),
    })
  }

  // ── Edit query text ─────────────────────────────────────────────────────────
  const startEdit = (q: ResearchQuery) => {
    setEditingId(q.id)
    setEditText(q.query)
  }

  const saveEdit = (id: string) => {
    if (!plan || !editText.trim()) return
    setPlan({
      ...plan,
      queries: plan.queries.map(q =>
        q.id === id ? { ...q, query: editText.trim() } : q
      ),
    })
    setEditingId(null)
  }

  // ── Execute approved queries ────────────────────────────────────────────────
  const executeQueries = async () => {
    if (!plan) return
    const approved = plan.queries.filter(q => q.approved)
    if (!approved.length) { setError('Approve at least one query'); return }

    setExecuting(true)
    setError('')

    try {
      // Show progress for each category
      const categories = [...new Set(approved.map(q => q.category))]
      for (const cat of categories) {
        const cfg = CATEGORY_CONFIG[cat]
        setExecStep(cfg?.label || cat)
        await new Promise(r => setTimeout(r, 400)) // visual feedback
      }

      const res = await fetch(`${API_BASE}/jira/execute-queries`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue_key: issue.issue_key,
          queries:   plan.queries,
        }),
      })
      if (!res.ok) throw new Error(`Execution failed: ${res.status}`)
      const data: ResearchContext = await res.json()
      setResults(data)
      setExecStep('')
    } catch (e: any) {
      setError(e.message || 'Research execution failed')
      setExecStep('')
    } finally {
      setExecuting(false)
    }
  }

  // ── Empty state — prompt to generate plan ───────────────────────────────────
  if (!plan && !loading) {
    return (
      <div className="flex flex-col h-full">
        <PanelHeader issue={issue} step="queries" />
        <div className="flex flex-col items-center justify-center flex-1 px-8 text-center">
          <div className="max-w-sm">
            <div className="w-14 h-14 bg-indigo-50 rounded-xl flex items-center justify-center mb-4 mx-auto">
              <Search className="w-7 h-7 text-indigo-500" />
            </div>
            <p className="text-sm font-medium text-gray-800 mb-2">
              Generate research queries first
            </p>
            <p className="text-xs text-gray-500 mb-5 leading-relaxed">
              Before writing DITA, the agent will generate targeted queries
              across 5 categories. You review and approve them before
              any research runs.
            </p>

            <div className="text-left bg-gray-50 rounded-lg p-3 mb-6 space-y-2">
              {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => {
                const Icon = cfg.icon
                return (
                  <div key={key} className="flex items-center gap-2 text-xs text-gray-500">
                    <Icon className={`w-3 h-3 ${cfg.color} flex-shrink-0`} />
                    <span>{cfg.label}</span>
                  </div>
                )
              })}
            </div>

            {error && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2 mb-4">
                {error}
              </p>
            )}

            <div className="flex gap-2 justify-center">
              <Button
                onClick={fetchPlan}
                className="bg-indigo-600 hover:bg-indigo-700 text-white px-6"
              >
                <Search className="w-4 h-4 mr-2" />
                Generate queries
              </Button>
              <Button variant="outline" size="sm" onClick={onSkip} className="text-gray-500 text-xs">
                Skip research
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <PanelHeader issue={issue} step="queries" />
        <div className="flex flex-col items-center justify-center flex-1 gap-4">
          <div className="w-10 h-10 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">Generating research queries...</p>
            <p className="text-xs text-gray-400 mt-1">Analyzing issue content and selecting query strategies</p>
          </div>
        </div>
      </div>
    )
  }

  // ── Results view — after execution ──────────────────────────────────────────
  if (results) {
    const hasChunks = results.total_chunks > 0
    return (
      <div className="flex flex-col h-full">
        <PanelHeader issue={issue} step="results" />

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {/* Summary stats */}
          <div className="flex gap-3">
            <div className="flex-1 bg-green-50 border border-green-200 rounded-lg p-3 text-center">
              <p className="text-xl font-medium text-green-700">{results.total_chunks}</p>
              <p className="text-xs text-green-600">Context chunks</p>
            </div>
            <div className="flex-1 bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
              <p className="text-xl font-medium text-blue-700">{results.results.length}</p>
              <p className="text-xs text-blue-600">Queries executed</p>
            </div>
          </div>

          {/* Sources used */}
          <div className="flex gap-2 flex-wrap">
            {results.sources_used.map(s => (
              <span key={s} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                {s}
              </span>
            ))}
          </div>

          {/* Per-query results */}
          {results.results.map(r => {
            const cfg = CATEGORY_CONFIG[r.category]
            const Icon = cfg?.icon || Search
            const hasContent = r.summary || r.chunks.length > 0
            return (
              <div key={r.query_id} className={`rounded-lg border p-3 ${
                r.error ? 'border-red-200 bg-red-50'
                : hasContent ? `${cfg?.bg || 'bg-gray-50'} ${cfg?.border || 'border-gray-200'}`
                : 'border-gray-200 bg-gray-50 opacity-60'
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon className={`w-3.5 h-3.5 ${cfg?.color || 'text-gray-500'} flex-shrink-0`} />
                  <span className={`text-xs font-medium ${cfg?.color || 'text-gray-600'}`}>
                    {cfg?.label || r.category}
                  </span>
                  {r.error
                    ? <AlertCircle className="w-3 h-3 text-red-500 ml-auto" />
                    : hasContent
                    ? <CheckCircle2 className="w-3 h-3 text-green-500 ml-auto" />
                    : <span className="text-xs text-gray-400 ml-auto">No results</span>
                  }
                  <span className="text-xs text-gray-400">{r.duration_ms}ms</span>
                </div>
                <p className="text-xs text-gray-500 italic mb-1">"{r.query}"</p>
                {r.error && <p className="text-xs text-red-600">{r.error}</p>}
                {r.summary && (
                  <p className="text-xs text-gray-700 leading-relaxed">{r.summary.slice(0, 200)}</p>
                )}
                {!r.summary && r.chunks[0] && (
                  <p className="text-xs text-gray-600 leading-relaxed">{r.chunks[0].slice(0, 200)}</p>
                )}
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
          {hasChunks ? (
            <div className="flex gap-2">
              <Button
                onClick={() => onResearchComplete(results)}
                className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm"
              >
                <CheckCircle2 className="w-4 h-4 mr-2" />
                Use this research → Generate DITA
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setResults(null); fetchPlan() }}
                className="text-xs text-gray-500"
              >
                Re-research
              </Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <p className="text-xs text-red-500 flex-1">No research results found</p>
              <Button size="sm" onClick={() => setResults(null)}>Edit queries</Button>
              <Button size="sm" variant="outline" onClick={onSkip}>Skip research</Button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ── Plan review — main state ────────────────────────────────────────────────
  const approvedCount = plan!.queries.filter(q => q.approved).length

  return (
    <div className="flex flex-col h-full">
      <PanelHeader issue={issue} step="review" />

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {/* Reasoning */}
        {plan!.reasoning && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-3">
            <p className="text-xs font-medium text-indigo-700 mb-1">Query strategy</p>
            <p className="text-xs text-indigo-600 leading-relaxed">{plan!.reasoning}</p>
          </div>
        )}

        {/* Queries */}
        {plan!.queries.map(q => {
          const cfg  = CATEGORY_CONFIG[q.category]
          const Icon = cfg?.icon || Search
          const isEditing = editingId === q.id

          return (
            <div
              key={q.id}
              className={`rounded-lg border overflow-hidden transition-all ${
                q.approved
                  ? `${cfg?.border || 'border-gray-300'} ${cfg?.bg || 'bg-white'}`
                  : 'border-gray-200 bg-gray-50 opacity-60'
              }`}
            >
              {/* Category header */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
                <div className="flex items-center gap-2">
                  <Icon className={`w-3.5 h-3.5 ${cfg?.color || 'text-gray-500'} flex-shrink-0`} />
                  <span className={`text-xs font-medium ${cfg?.color || 'text-gray-600'}`}>
                    {cfg?.label || q.category}
                  </span>
                  <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                    {SOURCE_LABELS[q.source] || q.source}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  {!isEditing && (
                    <button
                      onClick={() => startEdit(q)}
                      className="p-1 text-gray-400 hover:text-gray-600 rounded"
                      title="Edit query"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                  )}
                  <button
                    onClick={() => toggleQuery(q.id)}
                    className={`p-1 rounded transition-colors ${
                      q.approved
                        ? 'text-green-600 hover:text-red-500'
                        : 'text-gray-400 hover:text-green-600'
                    }`}
                    title={q.approved ? 'Remove from research' : 'Add to research'}
                  >
                    {q.approved
                      ? <Check className="w-3.5 h-3.5" />
                      : <X className="w-3.5 h-3.5" />
                    }
                  </button>
                </div>
              </div>

              {/* Query text */}
              <div className="px-3 py-2.5">
                {isEditing ? (
                  <div className="flex gap-2">
                    <input
                      className="flex-1 text-xs border border-blue-300 rounded px-2 py-1 bg-white focus:outline-none focus:border-blue-500"
                      value={editText}
                      onChange={e => setEditText(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') saveEdit(q.id)
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      autoFocus
                    />
                    <button
                      onClick={() => saveEdit(q.id)}
                      className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-xs px-2 py-1 border border-gray-200 rounded hover:bg-gray-50 text-gray-500"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <p className="text-xs text-gray-800 font-mono">{q.query}</p>
                )}
                <p className="text-xs text-gray-500 mt-1 italic">{q.purpose}</p>
              </div>
            </div>
          )
        })}

        {/* Add custom query */}
        <AddQueryRow plan={plan!} onAdd={newQ => setPlan({
          ...plan!,
          queries: [...plan!.queries, newQ],
        })} />
      </div>

      {/* Error */}
      {error && (
        <div className="px-5 pb-2">
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">{error}</p>
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
        {executing ? (
          <div className="flex items-center gap-3 justify-center py-1">
            <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-gray-600">
              Researching: {execStep}...
            </p>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button
              onClick={executeQueries}
              disabled={approvedCount === 0}
              className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-sm"
            >
              <Play className="w-4 h-4 mr-2" />
              Run {approvedCount} quer{approvedCount === 1 ? 'y' : 'ies'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchPlan}
              className="text-xs text-gray-500"
              title="Re-generate queries"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onSkip}
              className="text-xs text-gray-500"
            >
              Skip
            </Button>
          </div>
        )}
        <p className="text-xs text-gray-400 text-center mt-1.5">
          {approvedCount} of {plan!.queries.length} queries selected
        </p>
      </div>
    </div>
  )
}

// ── Panel header ──────────────────────────────────────────────────────────────

function PanelHeader({
  issue,
  step,
}: { issue: JiraIssue; step: 'queries' | 'review' | 'results' }) {
  const labels: Record<string, string> = {
    queries: 'Generate queries',
    review:  'Review queries',
    results: 'Research results',
  }
  return (
    <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
      <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
        {issue.issue_key}
      </span>
      <ChevronRight className="w-3 h-3 text-gray-400" />
      <span className="text-xs font-medium text-gray-700">{labels[step]}</span>
    </div>
  )
}

// ── Add custom query row ──────────────────────────────────────────────────────

function AddQueryRow({
  plan,
  onAdd,
}: { plan: QueryPlan; onAdd: (q: ResearchQuery) => void }) {
  const [adding, setAdding]   = useState(false)
  const [text, setText]       = useState('')
  const [category, setCategory] = useState('aem_guides')

  const handleAdd = () => {
    if (!text.trim()) return
    onAdd({
      id:       `q_custom_${Date.now()}`,
      category,
      query:    text.trim(),
      purpose:  'Custom query added by author',
      source:   QUERY_CATEGORIES_SOURCE[category] || 'both',
      approved: true,
    })
    setText('')
    setAdding(false)
  }

  if (!adding) {
    return (
      <button
        onClick={() => setAdding(true)}
        className="w-full text-xs text-gray-400 border border-dashed border-gray-300 rounded-lg py-2 hover:border-gray-400 hover:text-gray-600 flex items-center justify-center gap-1.5 transition-colors"
      >
        <Plus className="w-3 h-3" />
        Add custom query
      </button>
    )
  }

  return (
    <div className="border border-blue-300 rounded-lg p-3 bg-blue-50/50 space-y-2">
      <select
        value={category}
        onChange={e => setCategory(e.target.value)}
        className="w-full text-xs border border-gray-200 rounded px-2 py-1 bg-white"
      >
        {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => (
          <option key={key} value={key}>{cfg.label}</option>
        ))}
      </select>
      <input
        className="w-full text-xs border border-blue-300 rounded px-2 py-1.5 bg-white focus:outline-none focus:border-blue-500"
        placeholder="Your custom research query..."
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') setAdding(false) }}
        autoFocus
      />
      <div className="flex gap-2">
        <button onClick={handleAdd} className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">
          Add
        </button>
        <button onClick={() => setAdding(false)} className="text-xs px-3 py-1 border border-gray-200 rounded hover:bg-gray-50 text-gray-500">
          Cancel
        </button>
      </div>
    </div>
  )
}

const QUERY_CATEGORIES_SOURCE: Record<string, 'rag' | 'tavily' | 'both'> = {
  dita_elements:   'rag',
  aem_guides:      'tavily',
  bugs_fixes:      'tavily',
  expert_examples: 'rag',
  dita_spec:       'rag',
}
