import { useState, useEffect } from 'react'
import {
  AlertTriangle, CheckCircle2, XCircle,
  Clock, GitCompare, FileEdit, ShieldCheck,
  ThumbsUp, ThumbsDown, RotateCcw, History,
  User, Bot, Info
} from 'lucide-react'
import { Button } from '../ui/button'
import type { JiraIssue, GeneratedDita } from '../../pages/AuthoringPage'

const API_BASE = '/api/v1'

// ── Types ─────────────────────────────────────────────────────────────────────

interface RelevanceCheck {
  is_relevant:      boolean
  score:            number
  matched_terms:    string[]
  missing_terms:    string[]
  wrong_topic_type: boolean
  warnings:         string[]
  recommendation:   string
}

interface VersionEntry {
  version:    number
  author:     string
  action:     string
  timestamp:  string
  ai_percent: number
  comment:    string
  diff_lines: number
}

interface ApprovalRecord {
  status:           string
  approved_by:      string
  approved_at:      string
  rejected_by:      string
  rejection_reason: string
  ai_percent:       number
  version:          number
}

interface Props {
  issue:         JiraIssue | null
  generatedDita: GeneratedDita | null
  onStartScratch: (content: string, filename: string) => void
  onApproved:     () => void
}

// ── Main component ────────────────────────────────────────────────────────────

export function SafetyPanel({ issue, generatedDita, onStartScratch, onApproved }: Props) {
  const [relevance,    setRelevance]    = useState<RelevanceCheck | null>(null)
  const [approval,     setApproval]     = useState<ApprovalRecord | null>(null)
  const [history,      setHistory]      = useState<VersionEntry[]>([])
  const [activeTab,    setActiveTab]    = useState<'safety'|'history'|'audit'>('safety')
  const [loadingCheck, setLoadingCheck] = useState(false)
  const [loadingApprove, setLoadingApprove] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [showReject,   setShowReject]   = useState(false)
  const [scratchLoading, setScratchLoading] = useState(false)

  // Run relevance check automatically when DITA is generated
  useEffect(() => {
    if (generatedDita && issue && generatedDita.quality_score > 0) {
      runRelevanceCheck()
      loadHistory()
      loadApprovalStatus()
    }
  }, [generatedDita?.filename])

  const runRelevanceCheck = async () => {
    if (!generatedDita || !issue) return
    setLoadingCheck(true)
    try {
      const res = await fetch(`${API_BASE}/safety/check-relevance`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue,
          content:    generatedDita.content,
          dita_type:  generatedDita.dita_type,
        }),
      })
      const data = await res.json()
      setRelevance(data)

      // Auto-save as version 1 (AI generated)
      await fetch(`${API_BASE}/safety/save-version`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue_key: issue.issue_key,
          filename:  generatedDita.filename,
          content:   generatedDita.content,
          author:    'ai',
          action:    'generated',
          comment:   'Initial AI generation',
        }),
      })
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingCheck(false)
    }
  }

  const loadHistory = async () => {
    if (!issue || !generatedDita) return
    try {
      const res  = await fetch(`${API_BASE}/safety/version-history/${issue.issue_key}/${generatedDita.filename}`)
      const data = await res.json()
      setHistory(data.history || [])
    } catch (e) { console.error(e) }
  }

  const loadApprovalStatus = async () => {
    if (!issue || !generatedDita) return
    try {
      const res  = await fetch(`${API_BASE}/safety/approval-status/${issue.issue_key}/${generatedDita.filename}`)
      const data = await res.json()
      if (data.status !== 'not_submitted') setApproval(data)
    } catch (e) { console.error(e) }
  }

  const handleApprove = async () => {
    if (!issue || !generatedDita) return
    setLoadingApprove(true)
    try {
      await fetch(`${API_BASE}/safety/approve`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue_key:   issue.issue_key,
          filename:    generatedDita.filename,
          approved_by: 'author',
        }),
      })
      setApproval({ status: 'approved', approved_by: 'author', approved_at: new Date().toISOString(), rejected_by: '', rejection_reason: '', ai_percent: relevance ? (1 - relevance.score) * 100 : 50, version: history.length })
      onApproved()
    } catch (e) { console.error(e) }
    finally { setLoadingApprove(false) }
  }

  const handleReject = async () => {
    if (!issue || !generatedDita || !rejectReason.trim()) return
    try {
      await fetch(`${API_BASE}/safety/reject`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue_key:   issue.issue_key,
          filename:    generatedDita.filename,
          rejected_by: 'author',
          reason:      rejectReason,
        }),
      })
      setApproval({ status: 'rejected', approved_by: '', approved_at: '', rejected_by: 'author', rejection_reason: rejectReason, ai_percent: 100, version: history.length })
      setShowReject(false)
      setRejectReason('')
    } catch (e) { console.error(e) }
  }

  const handleScratch = async (ditaType: string) => {
    if (!issue) return
    setScratchLoading(true)
    try {
      const res  = await fetch(`${API_BASE}/safety/scratch-mode`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue_key: issue.issue_key,
          dita_type: ditaType,
          author:    'author',
        }),
      })
      const data = await res.json()
      onStartScratch(data.content, data.filename)
    } catch (e) { console.error(e) }
    finally { setScratchLoading(false) }
  }

  // ── Empty state ─────────────────────────────────────────────────────────────
  if (!generatedDita || !issue) {
    return (
      <div className="p-4 flex flex-col items-center justify-center h-full text-center">
        <ShieldCheck className="w-8 h-8 text-gray-300 mb-2" />
        <p className="text-xs text-gray-400">Safety controls appear after generation</p>
      </div>
    )
  }

  // ── Relevance check loading ─────────────────────────────────────────────────
  if (loadingCheck) {
    return (
      <div className="p-4 flex flex-col items-center justify-center gap-3">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-gray-500">Checking relevance...</p>
      </div>
    )
  }

  const aiPercent  = history.length > 0 ? history[history.length - 1].ai_percent : 100
  const isApproved = approval?.status === 'approved'
  const isRejected = approval?.status === 'rejected'

  return (
    <div className="flex flex-col h-full">
      {/* Tab nav */}
      <div className="flex border-b border-gray-100">
        {(['safety', 'history', 'audit'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 text-xs font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'text-blue-600 border-b-2 border-blue-500'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Safety tab */}
      {activeTab === 'safety' && (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">

          {/* AI contribution meter */}
          <div className="bg-white border border-gray-200 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-gray-600">AI contribution</span>
              <span className={`text-xs font-semibold ${
                aiPercent > 80 ? 'text-amber-600' : aiPercent > 40 ? 'text-blue-600' : 'text-green-600'
              }`}>{Math.round(aiPercent)}%</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  aiPercent > 80 ? 'bg-amber-400' : aiPercent > 40 ? 'bg-blue-400' : 'bg-green-400'
                }`}
                style={{ width: `${aiPercent}%` }}
              />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-xs text-gray-400 flex items-center gap-0.5">
                <Bot className="w-2.5 h-2.5" /> AI
              </span>
              <span className="text-xs text-gray-400 flex items-center gap-0.5">
                <User className="w-2.5 h-2.5" /> Human
              </span>
            </div>
          </div>

          {/* Relevance check */}
          {relevance && (
            <div className={`border rounded-lg p-3 ${
              relevance.is_relevant && !relevance.wrong_topic_type
                ? 'border-green-200 bg-green-50'
                : relevance.score > 0.4
                ? 'border-amber-200 bg-amber-50'
                : 'border-red-200 bg-red-50'
            }`}>
              <div className="flex items-center gap-1.5 mb-2">
                {relevance.is_relevant && !relevance.wrong_topic_type
                  ? <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                  : relevance.score > 0.4
                  ? <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  : <XCircle className="w-3.5 h-3.5 text-red-600" />
                }
                <span className={`text-xs font-semibold ${
                  relevance.is_relevant && !relevance.wrong_topic_type ? 'text-green-700'
                  : relevance.score > 0.4 ? 'text-amber-700'
                  : 'text-red-700'
                }`}>
                  Relevance: {Math.round(relevance.score * 100)}%
                </span>
              </div>

              {/* Warnings */}
              {relevance.warnings.length > 0 && (
                <div className="space-y-1 mb-2">
                  {relevance.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-amber-700 flex items-start gap-1">
                      <span className="flex-shrink-0 mt-0.5">⚠</span>
                      {w}
                    </p>
                  ))}
                </div>
              )}

              {/* Matched / missing terms */}
              {relevance.matched_terms.length > 0 && (
                <div className="mb-1.5">
                  <p className="text-xs text-gray-500 mb-1">Found in content:</p>
                  <div className="flex flex-wrap gap-1">
                    {relevance.matched_terms.map(t => (
                      <span key={t} className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">{t}</span>
                    ))}
                  </div>
                </div>
              )}
              {relevance.missing_terms.length > 0 && (
                <div className="mb-1.5">
                  <p className="text-xs text-gray-500 mb-1">Missing from content:</p>
                  <div className="flex flex-wrap gap-1">
                    {relevance.missing_terms.map(t => (
                      <span key={t} className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">{t}</span>
                    ))}
                  </div>
                </div>
              )}

              <p className="text-xs text-gray-600 mt-2 italic">{relevance.recommendation}</p>
            </div>
          )}

          {/* Approval status */}
          {(isApproved || isRejected) && (
            <div className={`border rounded-lg p-3 ${
              isApproved ? 'border-green-300 bg-green-50' : 'border-red-200 bg-red-50'
            }`}>
              <div className="flex items-center gap-1.5">
                {isApproved
                  ? <ThumbsUp className="w-3.5 h-3.5 text-green-600" />
                  : <ThumbsDown className="w-3.5 h-3.5 text-red-600" />
                }
                <span className={`text-xs font-semibold ${isApproved ? 'text-green-700' : 'text-red-700'}`}>
                  {isApproved ? 'Approved for publishing' : 'Rejected — needs revision'}
                </span>
              </div>
              {isRejected && approval?.rejection_reason && (
                <p className="text-xs text-red-600 mt-1">{approval.rejection_reason}</p>
              )}
            </div>
          )}

          {/* Approval actions */}
          {!isApproved && !isRejected && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-600">Publishing approval</p>

              <Button
                onClick={handleApprove}
                disabled={loadingApprove}
                className="w-full bg-green-600 hover:bg-green-700 text-white text-xs h-8"
              >
                <ThumbsUp className="w-3 h-3 mr-1.5" />
                Approve for publishing
              </Button>

              {!showReject ? (
                <button
                  onClick={() => setShowReject(true)}
                  className="w-full text-xs text-red-600 border border-red-200 rounded-md py-1.5 hover:bg-red-50 transition-colors flex items-center justify-center gap-1.5"
                >
                  <ThumbsDown className="w-3 h-3" />
                  Reject — needs revision
                </button>
              ) : (
                <div className="space-y-2">
                  <textarea
                    className="w-full text-xs border border-red-200 rounded-md p-2 resize-none h-16 focus:outline-none focus:border-red-400"
                    placeholder="Reason for rejection..."
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                    autoFocus
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={handleReject}
                      disabled={!rejectReason.trim()}
                      className="flex-1 text-xs bg-red-600 text-white rounded-md py-1.5 hover:bg-red-700 disabled:opacity-50"
                    >
                      Confirm rejection
                    </button>
                    <button
                      onClick={() => { setShowReject(false); setRejectReason('') }}
                      className="text-xs border border-gray-200 rounded-md px-3 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Scratch mode */}
          <div className="border border-gray-200 rounded-lg p-3">
            <p className="text-xs font-medium text-gray-600 mb-1.5 flex items-center gap-1.5">
              <FileEdit className="w-3.5 h-3.5" />
              Write from scratch
            </p>
            <p className="text-xs text-gray-500 mb-2">
              Ignore AI output completely. Get a clean DITA template and write your own content.
            </p>
            <div className="flex gap-1.5 flex-wrap">
              {['task', 'concept', 'reference', 'glossentry'].map(type => (
                <button
                  key={type}
                  onClick={() => handleScratch(type)}
                  disabled={scratchLoading}
                  className="text-xs px-2.5 py-1 border border-gray-200 rounded hover:bg-gray-50 text-gray-600 font-mono transition-colors"
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Re-check button */}
          <button
            onClick={runRelevanceCheck}
            className="w-full text-xs text-gray-500 border border-gray-200 rounded-md py-1.5 hover:bg-gray-50 flex items-center justify-center gap-1.5"
          >
            <RotateCcw className="w-3 h-3" />
            Re-check relevance
          </button>
        </div>
      )}

      {/* History tab */}
      {activeTab === 'history' && (
        <div className="flex-1 overflow-y-auto p-3">
          {history.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No version history yet</p>
          ) : (
            <div className="space-y-2">
              {[...history].reverse().map((v, i) => (
                <div key={v.version} className={`border rounded-lg p-2.5 ${
                  i === 0 ? 'border-blue-200 bg-blue-50/50' : 'border-gray-200'
                }`}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      {v.author === 'ai'
                        ? <Bot className="w-3 h-3 text-purple-500" />
                        : <User className="w-3 h-3 text-blue-500" />
                      }
                      <span className="text-xs font-medium text-gray-700">
                        v{v.version} — {v.action}
                      </span>
                      {i === 0 && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">current</span>
                      )}
                    </div>
                    <span className={`text-xs font-medium ${
                      v.ai_percent > 80 ? 'text-amber-600'
                      : v.ai_percent > 40 ? 'text-blue-600'
                      : 'text-green-600'
                    }`}>
                      {Math.round(v.ai_percent)}% AI
                    </span>
                  </div>
                  <p className="text-xs text-gray-400">
                    {new Date(v.timestamp).toLocaleString()}
                  </p>
                  {v.comment && <p className="text-xs text-gray-600 mt-0.5 italic">{v.comment}</p>}
                  {v.diff_lines > 0 && (
                    <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                      <GitCompare className="w-3 h-3" />
                      {v.diff_lines} lines changed
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Audit tab */}
      {activeTab === 'audit' && (
        <AuditTab issueKey={issue.issue_key} />
      )}
    </div>
  )
}

// ── Audit tab subcomponent ────────────────────────────────────────────────────

function AuditTab({ issueKey }: { issueKey: string }) {
  const [entries, setEntries] = useState<any[]>([])

  useEffect(() => {
    fetch(`${API_BASE}/safety/audit-log/${issueKey}`)
      .then(r => r.json())
      .then(d => setEntries(d.entries || []))
      .catch(console.error)
  }, [issueKey])

  const ACTION_COLORS: Record<string, string> = {
    generated:           'text-purple-600 bg-purple-50',
    edited:              'text-blue-600 bg-blue-50',
    approved:            'text-green-600 bg-green-50',
    rejected:            'text-red-600 bg-red-50',
    scratch_started:     'text-amber-600 bg-amber-50',
    approval_requested:  'text-gray-600 bg-gray-100',
  }

  return (
    <div className="flex-1 overflow-y-auto p-3">
      {entries.length === 0 ? (
        <p className="text-xs text-gray-400 text-center py-6">No audit entries yet</p>
      ) : (
        <div className="space-y-2">
          {[...entries].reverse().map((e, i) => (
            <div key={i} className="border border-gray-100 rounded-lg p-2.5">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  {e.actor === 'ai' || e.actor === 'system'
                    ? <Bot className="w-3 h-3 text-purple-400" />
                    : <User className="w-3 h-3 text-blue-400" />
                  }
                  <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                    ACTION_COLORS[e.action] || 'text-gray-600 bg-gray-100'
                  }`}>
                    {e.action}
                  </span>
                </div>
                <span className="text-xs text-gray-400">
                  {new Date(e.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-xs text-gray-500">
                by <span className="font-medium">{e.actor}</span>
                {e.section && <> · section: <span className="font-mono">{e.section}</span></>}
                {e.change_size > 0 && <> · {e.change_size} chars changed</>}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
