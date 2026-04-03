/**
 * useAuthorMemory — React hook that connects the authoring UI to
 * the UserPreferencesService backend.
 *
 * What it does:
 * 1. On mount → fetches last session (last issue, stage, stats)
 * 2. On issue select → saves to memory automatically
 * 3. On stage change → updates memory
 * 4. Exposes recentIssues, preferredDitaType, authorName
 *
 * Place at: frontend/src/hooks/useAuthorMemory.ts
 */

import { useState, useEffect, useCallback } from 'react'

const API_BASE   = '/api/v1'
const AUTHOR_ID  = 'default'   // swap for real auth later

// ── Types ─────────────────────────────────────────────────────────────────────

export interface RecentIssue {
  issue_key:  string
  summary:    string
  dita_type:  string
  opened_at:  string
}

export interface AuthorStats {
  generated: number
  approved:  number
  rejected:  number
}

export interface SessionState {
  author_id:          string
  display_name:       string
  last_issue_key:     string
  last_issue_summary: string
  last_dita_type:     string
  last_stage:         string
  recent_issues:      RecentIssue[]
  default_tab:        string
  show_research_step: boolean
  min_quality_score:  number
  stats:              AuthorStats
}

const DEFAULT_SESSION: SessionState = {
  author_id:          AUTHOR_ID,
  display_name:       '',
  last_issue_key:     '',
  last_issue_summary: '',
  last_dita_type:     'task',
  last_stage:         'idle',
  recent_issues:      [],
  default_tab:        'preview',
  show_research_step: true,
  min_quality_score:  80,
  stats:              { generated: 0, approved: 0, rejected: 0 },
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuthorMemory() {
  const [session, setSession]   = useState<SessionState>(DEFAULT_SESSION)
  const [loading, setLoading]   = useState(true)
  const [restored, setRestored] = useState(false)

  // ── Load session on mount ─────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      try {
        const res  = await fetch(`${API_BASE}/prefs/session/${AUTHOR_ID}`)
        const data = await res.json()
        if (!data.error) {
          setSession(prev => ({ ...prev, ...data }))
          setRestored(true)
        }
      } catch (e) {
        console.warn('Could not load author session:', e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // ── Remember issue selection ──────────────────────────────────────────────
  const rememberIssue = useCallback(async (
    issueKey:    string,
    summary:     string,
    ditaType:    string = 'task',
    stage:       string = 'research',
  ) => {
    // Optimistic update
    setSession(prev => ({
      ...prev,
      last_issue_key:     issueKey,
      last_issue_summary: summary,
      last_dita_type:     ditaType,
      last_stage:         stage,
      recent_issues: [
        { issue_key: issueKey, summary, dita_type: ditaType, opened_at: new Date().toISOString() },
        ...prev.recent_issues.filter(r => r.issue_key !== issueKey),
      ].slice(0, 10),
    }))

    // Persist to backend (fire and forget)
    try {
      await fetch(`${API_BASE}/prefs/last-issue`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author_id:     AUTHOR_ID,
          issue_key:     issueKey,
          issue_summary: summary,
          dita_type:     ditaType,
          stage,
        }),
      })
    } catch (e) {
      console.warn('Could not save issue to memory:', e)
    }
  }, [])

  // ── Remember stage change ─────────────────────────────────────────────────
  const rememberStage = useCallback(async (stage: string) => {
    setSession(prev => ({ ...prev, last_stage: stage }))
    if (!session.last_issue_key) return
    try {
      await fetch(`${API_BASE}/prefs/last-issue`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author_id:     AUTHOR_ID,
          issue_key:     session.last_issue_key,
          issue_summary: session.last_issue_summary,
          dita_type:     session.last_dita_type,
          stage,
        }),
      })
    } catch (e) { /* silent */ }
  }, [session.last_issue_key, session.last_issue_summary, session.last_dita_type])

  // ── Get preferred DITA type for an issue ──────────────────────────────────
  const getPreferredDitaType = useCallback(async (
    issueType: string,
    labels:    string[] = [],
  ): Promise<string> => {
    // Quick label check client-side
    const labelMap: Record<string, string> = {
      concept: 'concept', overview: 'concept',
      reference: 'reference', api: 'reference',
      glossary: 'glossentry', term: 'glossentry',
    }
    for (const label of labels) {
      if (labelMap[label.toLowerCase()]) return labelMap[label.toLowerCase()]
    }
    // Fall back to session dita_type_map (loaded from backend)
    const typeMap = (session as any).dita_type_map || {}
    return typeMap[issueType] || 'task'
  }, [session])

  // ── Record action for stats ───────────────────────────────────────────────
  const recordAction = useCallback(async (
    action: 'generated' | 'approved' | 'rejected' | 'scratch_started',
  ) => {
    // Optimistic
    setSession(prev => ({
      ...prev,
      stats: {
        ...prev.stats,
        generated: action === 'generated' ? prev.stats.generated + 1 : prev.stats.generated,
        approved:  action === 'approved'  ? prev.stats.approved  + 1 : prev.stats.approved,
        rejected:  action === 'rejected'  ? prev.stats.rejected  + 1 : prev.stats.rejected,
      },
    }))
    try {
      await fetch(`${API_BASE}/prefs/record`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author_id: AUTHOR_ID, action }),
      })
    } catch (e) { /* silent */ }
  }, [])

  // ── Update UI preference ──────────────────────────────────────────────────
  const updateUIPref = useCallback(async (key: string, value: any) => {
    setSession(prev => ({ ...prev, [key]: value }))
    try {
      await fetch(`${API_BASE}/prefs/ui`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author_id: AUTHOR_ID, key, value }),
      })
    } catch (e) { /* silent */ }
  }, [])

  // ── Set author name ───────────────────────────────────────────────────────
  const setAuthorName = useCallback(async (name: string, email: string = '') => {
    setSession(prev => ({ ...prev, display_name: name, email }))
    try {
      await fetch(`${API_BASE}/prefs/author`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author_id: AUTHOR_ID, display_name: name, email }),
      })
    } catch (e) { /* silent */ }
  }, [])

  return {
    session,
    loading,
    restored,           // true if session was loaded from backend

    // Actions
    rememberIssue,
    rememberStage,
    getPreferredDitaType,
    recordAction,
    updateUIPref,
    setAuthorName,

    // Shortcuts
    recentIssues:      session.recent_issues,
    lastIssueKey:      session.last_issue_key,
    lastIssueSummary:  session.last_issue_summary,
    authorName:        session.display_name || 'Author',
    showResearchStep:  session.show_research_step,
    minQualityScore:   session.min_quality_score,
    stats:             session.stats,
  }
}
