/**
 * IntentPanel — shown between issue selection and research.
 *
 * This is the NEW step 0 in the flow:
 *   Select issue → Confirm intent → Research → Generate → Review → Publish
 *
 * What it does:
 * 1. AI suggests 2-3 authoring intents with confidence scores
 * 2. Shows the transformed title (not the Jira summary)
 * 3. Author can edit the title inline
 * 4. Author picks intent + clicks Confirm → research starts with correct brief
 *
 * Place at: frontend/src/components/Authoring/IntentPanel.tsx
 */

import { useState, useEffect, useRef } from 'react'
import {
  Wrench, BookOpen, FileText, Database, Tag,
  ChevronRight, Edit2, Check, ArrowRight, Info
} from 'lucide-react'
import { Button } from '../ui/button'
import type { JiraIssue } from '../../pages/AuthoringPage'

const API_BASE = '/api/v1'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface IntentSuggestion {
  intent_type:  string
  label:        string
  description:  string
  dita_type:    string
  confidence:   number
  reasoning:    string
  is_primary:   boolean
}

export interface AuthoringIntent {
  intent_type:      string
  dita_type:        string
  audience:         string
  dita_title:       string
  jira_title:       string
  context_content:  string
  solution_hints:   string[]
  result_content:   string
  version_note:     string
  generation_brief: string
  sections:         string[]
  confidence:       number
  reasoning:        string
}

interface Props {
  issue:             JiraIssue
  researchContext?:  string
  onConfirmed:       (intent: AuthoringIntent) => void
  onBack:            () => void
}

// ── Intent icons ──────────────────────────────────────────────────────────────

const INTENT_ICONS: Record<string, any> = {
  troubleshooting_task: Wrench,
  feature_concept:      BookOpen,
  configuration_task:   FileText,
  api_reference:        Database,
  release_note:         Tag,
  glossentry:           Tag,
}

const INTENT_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  troubleshooting_task: { bg: '#EAF3DE', border: '#97C459', text: '#3B6D11', badge: 'bg-green-100 text-green-800' },
  feature_concept:      { bg: '#EEEDFE', border: '#AFA9EC', text: '#3C3489', badge: 'bg-purple-100 text-purple-800' },
  configuration_task:   { bg: '#E6F1FB', border: '#85B7EB', text: '#0C447C', badge: 'bg-blue-100 text-blue-800' },
  api_reference:        { bg: '#FAEEDA', border: '#FAC775', text: '#633806', badge: 'bg-amber-100 text-amber-800' },
  release_note:         { bg: '#FCEBEB', border: '#F09595', text: '#A32D2D', badge: 'bg-red-100 text-red-800' },
  glossentry:           { bg: '#F1EFE8', border: '#D3D1C7', text: '#444441', badge: 'bg-gray-100 text-gray-800' },
}

// ── Main component ────────────────────────────────────────────────────────────

export function IntentPanel({ issue, researchContext, onConfirmed, onBack }: Props) {
  const [suggestions,    setSuggestions]    = useState<IntentSuggestion[]>([])
  const [selectedIntent, setSelectedIntent] = useState<string>('')
  const [suggestedTitle, setSuggestedTitle] = useState('')
  const [editedTitle,    setEditedTitle]    = useState('')
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [loading,        setLoading]        = useState(true)
  const [confirming,     setConfirming]     = useState(false)
  const [error,          setError]          = useState('')
  const titleRef = useRef<HTMLInputElement>(null)

  // ── Fetch intent suggestions ──────────────────────────────────────────────
  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      setError('')
      try {
        const res  = await window.fetch(`${API_BASE}/intent/suggest`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ issue_key: issue.issue_key, issue }),
        })
        const data = await res.json()
        if (data.error) throw new Error(data.error)

        setSuggestions(data.suggestions || [])
        setSuggestedTitle(data.suggested_title || issue.summary)
        setEditedTitle(data.suggested_title || issue.summary)

        // Auto-select primary suggestion
        const primary = (data.suggestions || []).find((s: IntentSuggestion) => s.is_primary)
        if (primary) setSelectedIntent(primary.intent_type)

      } catch (e: any) {
        setError(e.message)
        setSuggestedTitle(issue.summary)
        setEditedTitle(issue.summary)
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [issue.issue_key])

  // ── Live title preview when intent changes ────────────────────────────────
  const handleIntentChange = async (intentType: string) => {
    setSelectedIntent(intentType)
    if (!isEditingTitle) {
      try {
        const res = await window.fetch(`${API_BASE}/intent/preview-title`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ summary: issue.summary, intent_type: intentType }),
        })
        const data = await res.json()
        if (data.title) {
          setSuggestedTitle(data.title)
          setEditedTitle(data.title)
        }
      } catch {}
    }
  }

  // ── Confirm intent ────────────────────────────────────────────────────────
  const handleConfirm = async () => {
    if (!selectedIntent) return
    setConfirming(true)
    setError('')
    try {
      const res = await window.fetch(`${API_BASE}/intent/confirm`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          issue,
          chosen_intent:    selectedIntent,
          custom_title:     editedTitle.trim() !== suggestedTitle ? editedTitle.trim() : '',
          research_context: researchContext || '',
        }),
      })
      const data: AuthoringIntent = await res.json()
      if ((data as any).error) throw new Error((data as any).error)
      onConfirmed(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setConfirming(false)
    }
  }

  const selectedSuggestion = suggestions.find(s => s.intent_type === selectedIntent)
  const colors = INTENT_COLORS[selectedIntent] || INTENT_COLORS['configuration_task']

  // ── Loading ───────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
        <div className="text-center">
          <p className="text-sm font-medium text-gray-700">Analysing issue…</p>
          <p className="text-xs text-gray-400 mt-1">Inferring authoring intent from Jira content</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">

      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded font-mono">
            {issue.issue_key}
          </span>
          <ChevronRight className="w-3 h-3 text-gray-400" />
          <span className="text-xs font-medium text-gray-600">Confirm authoring intent</span>
        </div>
        <p className="text-xs text-gray-400 truncate">{issue.summary}</p>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

        {/* Key insight banner */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex gap-3">
          <Info className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-medium text-amber-800 mb-0.5">Jira ≠ DITA content</p>
            <p className="text-xs text-amber-700 leading-relaxed">
              This Jira issue describes a bug. The DITA topic should tell the <strong>user how to fix it</strong> — not copy the reproduction steps.
              Confirm what to write below.
            </p>
          </div>
        </div>

        {/* Title transformation */}
        <div>
          <p className="text-xs font-medium text-gray-600 mb-2">DITA topic title</p>
          <div className="space-y-2">
            {/* Jira original */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-20 flex-shrink-0">Jira title</span>
              <p className="text-xs text-gray-500 line-through">{issue.summary}</p>
            </div>
            {/* Transformed */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-20 flex-shrink-0">DITA title</span>
              {isEditingTitle ? (
                <div className="flex gap-2 flex-1">
                  <input
                    ref={titleRef}
                    className="flex-1 text-xs border border-blue-300 rounded px-2 py-1.5 bg-white focus:outline-none focus:border-blue-500"
                    value={editedTitle}
                    onChange={e => setEditedTitle(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') setIsEditingTitle(false) }}
                  />
                  <button
                    onClick={() => setIsEditingTitle(false)}
                    className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                  >
                    <Check className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 flex-1">
                  <p className="text-xs font-medium text-gray-900 flex-1">{editedTitle}</p>
                  <button
                    onClick={() => { setIsEditingTitle(true); setTimeout(() => titleRef.current?.focus(), 50) }}
                    className="p-1 text-gray-400 hover:text-gray-600 rounded"
                  >
                    <Edit2 className="w-3 h-3" />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Intent selection */}
        <div>
          <p className="text-xs font-medium text-gray-600 mb-2">What to write</p>
          <div className="space-y-2">
            {suggestions.map(suggestion => {
              const Icon    = INTENT_ICONS[suggestion.intent_type] || FileText
              const c       = INTENT_COLORS[suggestion.intent_type] || INTENT_COLORS['configuration_task']
              const isChosen = selectedIntent === suggestion.intent_type

              return (
                <div
                  key={suggestion.intent_type}
                  onClick={() => handleIntentChange(suggestion.intent_type)}
                  className={`border rounded-lg p-3 cursor-pointer transition-all ${
                    isChosen
                      ? 'border-2 shadow-sm'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  style={isChosen ? {
                    borderColor: c.border,
                    background:  c.bg,
                  } : {}}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: isChosen ? c.border : '#F1EFE8' }}
                    >
                      <Icon className="w-4 h-4" style={{ color: isChosen ? '#fff' : '#6b7280' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span
                          className="text-xs font-semibold"
                          style={{ color: isChosen ? c.text : '#374151' }}
                        >
                          {suggestion.label}
                        </span>
                        {suggestion.is_primary && (
                          <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium">
                            AI suggestion
                          </span>
                        )}
                        <span className="text-xs text-gray-400 ml-auto">
                          {Math.round(suggestion.confidence * 100)}%
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 leading-relaxed">{suggestion.description}</p>
                      {isChosen && suggestion.reasoning && (
                        <p className="text-xs mt-1 italic" style={{ color: c.text }}>
                          {suggestion.reasoning}
                        </p>
                      )}
                    </div>
                    {isChosen && (
                      <div
                        className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
                        style={{ background: c.border }}
                      >
                        <Check className="w-3 h-3 text-white" />
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* What will be generated */}
        {selectedSuggestion && (
          <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
            <p className="text-xs font-medium text-gray-600 mb-2">What the DITA will contain</p>
            <div className="space-y-1.5">
              <div className="flex items-start gap-2 text-xs text-gray-500">
                <span className="text-green-600 mt-0.5 font-mono text-xs">✓</span>
                <span>User-facing fix steps (NOT Jira reproduction steps)</span>
              </div>
              <div className="flex items-start gap-2 text-xs text-gray-500">
                <span className="text-green-600 mt-0.5 font-mono text-xs">✓</span>
                <span>Background context from description (WHY it happens)</span>
              </div>
              <div className="flex items-start gap-2 text-xs text-gray-500">
                <span className="text-green-600 mt-0.5 font-mono text-xs">✓</span>
                <span>Solution hints from developer comments</span>
              </div>
              <div className="flex items-start gap-2 text-xs text-gray-500">
                <span className="text-red-400 mt-0.5 font-mono text-xs">✗</span>
                <span className="line-through text-gray-400">QA steps to reproduce the bug</span>
              </div>
              <div className="flex items-start gap-2 text-xs text-gray-500">
                <span className="text-red-400 mt-0.5 font-mono text-xs">✗</span>
                <span className="line-through text-gray-400">Expected / actual result (QA language)</span>
              </div>
            </div>
          </div>
        )}

        {error && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">{error}</p>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onBack} className="text-xs text-gray-500">
            Back
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!selectedIntent || confirming}
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs"
          >
            {confirming ? (
              <>
                <div className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin mr-2" />
                Preparing brief…
              </>
            ) : (
              <>
                Confirm intent → Research
                <ArrowRight className="w-3 h-3 ml-2" />
              </>
            )}
          </Button>
        </div>
        <p className="text-xs text-gray-400 text-center mt-1.5">
          AI generates from this intent — not from Jira content directly
        </p>
      </div>
    </div>
  )
}
