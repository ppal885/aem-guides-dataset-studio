import { useState } from 'react'
import {
  Sparkles, ChevronRight, Plus, Trash2,
  CheckCircle2, Edit2, FileText, Map, Zap
} from 'lucide-react'
import { Button } from '../ui/button'
import type { JiraIssue } from '../../pages/AuthoringPage'

const API_BASE = '/api/v1'

// ── Types ────────────────────────────────────────────────────────────────────

interface PlannedSection {
  element: string
  label: string
  description: string
  required: boolean
  notes: string
}

interface PlannedTopic {
  topic_type: string
  title: string
  filename: string
  rationale: string
  dita_version: string
  key_constructs: string[]
  sections: PlannedSection[]
}

export interface DitaAuthoringPlan {
  issue_key: string
  issue_summary: string
  overall_rationale: string
  ditamap_needed: boolean
  ditamap_title: string
  confidence: number
  rag_sources_used: string[]
  topics: PlannedTopic[]
}

interface Props {
  issue: JiraIssue
  onApprove: (plan: DitaAuthoringPlan) => void
  onSkip: () => void
}

// ── Constants ────────────────────────────────────────────────────────────────

const TOPIC_TYPE_COLORS: Record<string, string> = {
  task:       'bg-green-50 text-green-700 border-green-300',
  concept:    'bg-blue-50 text-blue-700 border-blue-300',
  reference:  'bg-purple-50 text-purple-700 border-purple-300',
  glossentry: 'bg-amber-50 text-amber-700 border-amber-300',
}

const ELEMENT_COLORS: Record<string, string> = {
  shortdesc:  'bg-blue-50 text-blue-700',
  prereq:     'bg-gray-100 text-gray-600',
  context:    'bg-gray-100 text-gray-600',
  steps:      'bg-green-50 text-green-700',
  result:     'bg-green-50 text-green-700',
  section:    'bg-purple-50 text-purple-700',
  example:    'bg-amber-50 text-amber-700',
  note:       'bg-orange-50 text-orange-700',
  conbody:    'bg-blue-50 text-blue-700',
  refbody:    'bg-purple-50 text-purple-700',
  properties: 'bg-purple-50 text-purple-700',
}

const AVAILABLE_SECTIONS: Record<string, string[]> = {
  task:      ['shortdesc', 'prereq', 'context', 'steps', 'result', 'note', 'example'],
  concept:   ['shortdesc', 'conbody', 'section', 'example', 'note'],
  reference: ['shortdesc', 'refbody', 'properties', 'section', 'example'],
}

// ── Main component ────────────────────────────────────────────────────────────

export function PlanningPanel({ issue, onApprove, onSkip }: Props) {
  const [plan, setPlan]         = useState<DitaAuthoringPlan | null>(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [editingTopic, setEditingTopic] = useState<number | null>(null)

  const fetchPlan = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/jira/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_key: issue.issue_key, issue }),
      })
      if (!res.ok) throw new Error('Planning failed')
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setPlan(data)
    } catch (e: any) {
      setError(e.message || 'Failed to create plan')
    } finally {
      setLoading(false)
    }
  }

  const updateTopic = (i: number, patch: Partial<PlannedTopic>) => {
    if (!plan) return
    const topics = [...plan.topics]
    topics[i] = { ...topics[i], ...patch }
    setPlan({ ...plan, topics })
  }

  const removeSection = (topicIdx: number, sectionIdx: number) => {
    if (!plan) return
    const topics = [...plan.topics]
    topics[topicIdx].sections = topics[topicIdx].sections.filter((_, i) => i !== sectionIdx)
    setPlan({ ...plan, topics })
  }

  const addSection = (topicIdx: number, element: string) => {
    if (!plan) return
    const topics = [...plan.topics]
    const already = topics[topicIdx].sections.some(s => s.element === element)
    if (already) return
    topics[topicIdx].sections.push({
      element,
      label: element.replace(/_/g, ' '),
      description: `Content for ${element}`,
      required: false,
      notes: '',
    })
    setPlan({ ...plan, topics })
  }

  const removeTopic = (i: number) => {
    if (!plan) return
    setPlan({ ...plan, topics: plan.topics.filter((_, idx) => idx !== i) })
  }

  // ── Empty state ─────────────────────────────────────────────────────────────
  if (!plan && !loading) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
              {issue.issue_key}
            </span>
            <ChevronRight className="w-3 h-3 text-gray-400" />
            <span className="text-xs text-gray-500">Planning</span>
          </div>
          <p className="text-base font-medium text-gray-900">{issue.summary}</p>
        </div>

        <div className="flex flex-col items-center justify-center flex-1 px-8 text-center">
          <div className="max-w-sm">
            <div className="w-14 h-14 bg-amber-50 rounded-xl flex items-center justify-center mb-4 mx-auto">
              <Sparkles className="w-7 h-7 text-amber-500" />
            </div>
            <p className="text-sm font-medium text-gray-800 mb-2">
              Plan before generating
            </p>
            <p className="text-xs text-gray-500 mb-2 leading-relaxed">
              The planning agent will analyze <strong>{issue.issue_key}</strong> and suggest:
            </p>
            <ul className="text-xs text-gray-500 text-left mb-6 space-y-1.5 bg-gray-50 rounded-lg p-3">
              <li className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                Which DITA topic type to use (task/concept/reference)
              </li>
              <li className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                Which sections to include and why
              </li>
              <li className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                DITA constructs needed (keyref, conref, etc.)
              </li>
              <li className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                Whether multiple topics or a ditamap is needed
              </li>
            </ul>
            <div className="flex gap-2 justify-center">
              <Button
                onClick={fetchPlan}
                className="bg-amber-500 hover:bg-amber-600 text-white px-5"
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Create Plan
              </Button>
              <Button
                variant="outline"
                onClick={onSkip}
                className="text-gray-500 text-xs"
              >
                Skip planning
              </Button>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Uses RAG + DITA spec — no generation yet
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
        <div className="text-center">
          <p className="text-sm font-medium text-gray-700">Planning...</p>
          <div className="flex flex-col gap-1.5 mt-3 text-xs text-gray-400">
            <PlanStep label="Analyzing Jira issue type" done />
            <PlanStep label="Querying DITA spec rules" loading />
            <PlanStep label="Detecting DITA constructs" />
            <PlanStep label="Building topic structure" />
          </div>
        </div>
      </div>
    )
  }

  // ── Error ───────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-8 text-center">
        <p className="text-sm text-red-600 mb-4">{error}</p>
        <div className="flex gap-2">
          <Button onClick={fetchPlan} size="sm">Retry</Button>
          <Button variant="outline" size="sm" onClick={onSkip}>Skip planning</Button>
        </div>
      </div>
    )
  }

  if (!plan) return null

  // ── Plan ready for review ───────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
            {issue.issue_key}
          </span>
          <ChevronRight className="w-3 h-3 text-gray-400" />
          <span className="text-xs font-medium text-gray-700">Review Plan</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded font-medium ${
            plan.confidence >= 0.8 ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'
          }`}>
            {Math.round(plan.confidence * 100)}% confidence
          </span>
          {plan.rag_sources_used.length > 0 && (
            <span className="text-xs text-gray-400">
              via {plan.rag_sources_used.join(', ')}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {/* Overall rationale */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
          <div className="flex items-center gap-1.5 mb-1">
            <Zap className="w-3.5 h-3.5 text-amber-600" />
            <span className="text-xs font-medium text-amber-700">Planning rationale</span>
          </div>
          <p className="text-xs text-amber-800 leading-relaxed">{plan.overall_rationale}</p>
        </div>

        {/* Ditamap notice */}
        {plan.ditamap_needed && (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2.5">
            <Map className="w-3.5 h-3.5 text-blue-600" />
            <div>
              <p className="text-xs font-medium text-blue-700">Ditamap will be generated</p>
              <p className="text-xs text-blue-600">{plan.ditamap_title}</p>
            </div>
          </div>
        )}

        {/* Topic cards */}
        {plan.topics.map((topic, topicIdx) => (
          <div
            key={topicIdx}
            className="border border-gray-200 rounded-lg overflow-hidden"
          >
            {/* Topic header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5 text-gray-500" />
                <span className={`text-xs font-medium px-2 py-0.5 rounded border ${
                  TOPIC_TYPE_COLORS[topic.topic_type] || 'bg-gray-100 text-gray-600 border-gray-300'
                }`}>
                  {topic.topic_type}
                </span>
                {editingTopic === topicIdx ? (
                  <input
                    className="text-sm font-medium text-gray-900 border-b border-blue-400 bg-transparent focus:outline-none"
                    value={topic.title}
                    onChange={e => updateTopic(topicIdx, { title: e.target.value })}
                    onBlur={() => setEditingTopic(null)}
                    autoFocus
                  />
                ) : (
                  <span className="text-sm font-medium text-gray-900">{topic.title}</span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setEditingTopic(topicIdx)}
                  className="p-1 text-gray-400 hover:text-gray-600 rounded"
                  title="Edit title"
                >
                  <Edit2 className="w-3 h-3" />
                </button>
                {plan.topics.length > 1 && (
                  <button
                    onClick={() => removeTopic(topicIdx)}
                    className="p-1 text-gray-400 hover:text-red-500 rounded"
                    title="Remove topic"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Rationale */}
            <div className="px-4 py-2 border-b border-gray-100 bg-white">
              <p className="text-xs text-gray-500 italic">{topic.rationale}</p>
              <p className="text-xs text-gray-400 mt-0.5">→ {topic.filename}</p>
            </div>

            {/* Key constructs */}
            {topic.key_constructs.length > 0 && (
              <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-2 flex-wrap">
                <span className="text-xs text-gray-400">Constructs:</span>
                {topic.key_constructs.map(c => (
                  <span key={c} className="text-xs font-mono px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                    {c}
                  </span>
                ))}
              </div>
            )}

            {/* Sections */}
            <div className="px-4 py-3 space-y-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                Sections ({topic.sections.length})
              </p>
              {topic.sections.map((section, secIdx) => (
                <div key={secIdx} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className={`text-xs font-mono px-1.5 py-0.5 rounded flex-shrink-0 ${
                      ELEMENT_COLORS[section.element] || 'bg-gray-100 text-gray-600'
                    }`}>
                      {section.element}
                    </span>
                    <span className="text-xs text-gray-600 truncate">{section.description}</span>
                    {section.required && (
                      <span className="text-xs text-red-400 flex-shrink-0">required</span>
                    )}
                  </div>
                  {!section.required && (
                    <button
                      onClick={() => removeSection(topicIdx, secIdx)}
                      className="text-gray-300 hover:text-red-400 flex-shrink-0"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              ))}

              {/* Add section */}
              <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-gray-100">
                <span className="text-xs text-gray-400 mr-1">Add:</span>
                {(AVAILABLE_SECTIONS[topic.topic_type] || [])
                  .filter(el => !topic.sections.some(s => s.element === el))
                  .map(el => (
                    <button
                      key={el}
                      onClick={() => addSection(topicIdx, el)}
                      className="text-xs px-1.5 py-0.5 rounded border border-dashed border-gray-300 text-gray-400 hover:border-blue-400 hover:text-blue-500 flex items-center gap-0.5"
                    >
                      <Plus className="w-2.5 h-2.5" />
                      {el}
                    </button>
                  ))
                }
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer — approve or regenerate */}
      <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
        <div className="flex gap-2">
          <Button
            onClick={() => onApprove(plan)}
            className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm"
            disabled={plan.topics.length === 0}
          >
            <CheckCircle2 className="w-4 h-4 mr-2" />
            Approve plan & generate DITA
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchPlan}
            className="text-gray-500 text-xs"
          >
            Replan
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onSkip}
            className="text-gray-500 text-xs"
          >
            Skip
          </Button>
        </div>
        <p className="text-xs text-gray-400 text-center mt-2">
          Generation will follow this plan exactly
        </p>
      </div>
    </div>
  )
}

function PlanStep({ label, done, loading }: { label: string; done?: boolean; loading?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {done
        ? <CheckCircle2 className="w-3 h-3 text-green-500" />
        : loading
        ? <div className="w-3 h-3 border border-amber-500 border-t-transparent rounded-full animate-spin" />
        : <div className="w-3 h-3 rounded-full border border-gray-300" />
      }
      <span className={done ? 'text-gray-600' : loading ? 'text-amber-600' : 'text-gray-400'}>
        {label}
      </span>
    </div>
  )
}
