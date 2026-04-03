import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { BookOpen, Bug, CheckSquare, Clock3, Layers, RefreshCw, Search } from 'lucide-react'
import { Badge } from '../ui/badge'
import { Input } from '../ui/input'
import type { JiraIssue } from '../../pages/AuthoringPage'
import type { RecentIssue } from '../../hooks/useAuthorMemory'
import { withTenantHeaders } from '@/utils/api'

const API_BASE = '/api/v1'

const FILTER_TABS = [
  { label: 'My issues', jql: 'assignee = currentUser() ORDER BY updated DESC' },
  { label: 'Sprint', jql: 'sprint in openSprints() ORDER BY priority ASC' },
  { label: 'Done', jql: 'status = Done ORDER BY updated DESC' },
]

const STATUS_COLORS: Record<string, string> = {
  Done: 'bg-emerald-50 text-emerald-700',
  'In Progress': 'bg-amber-50 text-amber-700',
  Open: 'bg-gray-100 text-gray-600',
  'To Do': 'bg-gray-100 text-gray-600',
  Closed: 'bg-emerald-50 text-emerald-700',
}

const PRIORITY_DOT: Record<string, string> = {
  Highest: 'bg-red-500',
  High: 'bg-orange-400',
  Medium: 'bg-yellow-400',
  Low: 'bg-blue-400',
  Lowest: 'bg-gray-400',
}

interface Props {
  onSelect: (issue: JiraIssue) => void
  selectedKey?: string
  lastIssueKey?: string
  recentIssues?: RecentIssue[]
}

export function JiraIssueBrowser({
  onSelect,
  selectedKey,
  lastIssueKey,
  recentIssues = [],
}: Props) {
  const [issues, setIssues] = useState<JiraIssue[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState(0)

  const fetchIssues = useCallback(async (jql: string) => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/jira/search`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ jql, max_results: 30 }),
      })
      if (!response.ok) {
        throw new Error(`Jira API error: ${response.status}`)
      }
      const data = await response.json()
      setIssues(data.issues || [])
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Failed to fetch issues'
      setError(message)
      setIssues([])
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchByKey = useCallback(async (key: string) => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/jira/issue/${key}`, {
        headers: withTenantHeaders(),
      })
      if (!response.ok) {
        throw new Error(`Issue not found: ${key}`)
      }
      const data = await response.json()
      if (data.error) {
        throw new Error(data.error)
      }
      setIssues([data])
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Issue fetch failed'
      setError(message)
      setIssues([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchIssues(FILTER_TABS[activeTab].jql)
  }, [activeTab, fetchIssues])

  const handleSearch = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') {
      return
    }
    const normalized = search.trim().toUpperCase()
    if (!normalized) {
      void fetchIssues(FILTER_TABS[activeTab].jql)
      return
    }
    if (/^[A-Z]+-\d+$/.test(normalized)) {
      void fetchByKey(normalized)
      return
    }
    void fetchIssues(`text ~ "${search}" ORDER BY updated DESC`)
  }

  const filteredIssues = useMemo(
    () =>
      issues.filter(issue => {
        const query = search.toLowerCase()
        return (
          !search ||
          issue.summary.toLowerCase().includes(query) ||
          issue.issue_key.toLowerCase().includes(query)
        )
      }),
    [issues, search],
  )

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-gray-100 px-4 pb-2 pt-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Jira issues</p>

        <div className="relative mb-3">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-gray-400" />
          <Input
            className="h-8 pl-8 text-xs"
            placeholder="Search or enter AEM-123..."
            value={search}
            onChange={event => setSearch(event.target.value)}
            onKeyDown={handleSearch}
          />
        </div>

        <div className="flex gap-1">
          {FILTER_TABS.map((tab, index) => (
            <button
              key={tab.label}
              onClick={() => {
                setActiveTab(index)
                setSearch('')
              }}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                activeTab === index ? 'bg-blue-600 text-white' : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
          <button onClick={() => void fetchIssues(FILTER_TABS[activeTab].jql)} className="ml-auto p-1 text-gray-400 hover:text-gray-600">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {recentIssues.length ? (
        <div className="border-b border-gray-100 bg-gray-50 px-3 py-3">
          <div className="mb-2 flex items-center gap-1 text-xs font-medium text-gray-500">
            <Clock3 className="h-3 w-3" />
            Recent
          </div>
          <div className="space-y-1.5">
            {recentIssues.slice(0, 3).map(issue => (
              <button
                key={issue.issue_key}
                onClick={() => void fetchByKey(issue.issue_key)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  issue.issue_key === lastIssueKey ? 'border-blue-200 bg-blue-50' : 'border-gray-200 bg-white hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-medium text-blue-600">{issue.issue_key}</span>
                  <span className="text-gray-400">{issue.dita_type}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-gray-600">{issue.summary}</p>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-3 py-2">
        {loading ? (
          <div className="mt-2 flex flex-col gap-2">
            {[1, 2, 3, 4].map(index => (
              <div key={index} className="h-20 animate-pulse rounded-lg bg-gray-100" />
            ))}
          </div>
        ) : null}

        {error ? (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-xs text-red-600">
            {error}
            <p className="mt-1 text-red-400">Check Jira credentials in Settings.</p>
          </div>
        ) : null}

        {!loading && !error && !filteredIssues.length ? (
          <div className="mt-8 text-center text-xs text-gray-400">
            <p>No issues found.</p>
            <p className="mt-1">Try another filter or search query.</p>
          </div>
        ) : null}

        {!loading &&
          filteredIssues.map(issue => (
            <IssueCard
              key={issue.issue_key}
              issue={issue}
              isSelected={issue.issue_key === selectedKey}
              onClick={() => onSelect(issue)}
            />
          ))}
      </div>

      {!loading && filteredIssues.length ? (
        <div className="border-t border-gray-100 px-4 py-2 text-xs text-gray-400">
          {filteredIssues.length} issue{filteredIssues.length === 1 ? '' : 's'}
        </div>
      ) : null}
    </div>
  )
}

function IssueCard({
  issue,
  isSelected,
  onClick,
}: {
  issue: JiraIssue
  isSelected: boolean
  onClick: () => void
}) {
  const statusClass = STATUS_COLORS[issue.status] || 'bg-gray-100 text-gray-600'
  const priorityDot = PRIORITY_DOT[issue.priority] || 'bg-gray-400'

  return (
    <button
      onClick={onClick}
      className={`mb-2 w-full rounded-lg border p-3 text-left transition-all ${
        isSelected ? 'border-blue-500 bg-blue-50 shadow-sm' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
      }`}
    >
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-semibold text-blue-600">{issue.issue_key}</span>
        <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${statusClass}`}>
          <IssueTypeIcon issueType={issue.issue_type} />
          {issue.issue_type}
        </span>
      </div>

      <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-gray-800">{issue.summary}</p>

      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 rounded-full ${priorityDot}`} />
        <span className="text-xs text-gray-400">{issue.priority || 'No priority'}</span>
        <span className={`ml-auto rounded px-1.5 py-0.5 text-xs ${statusClass}`}>{issue.status}</span>
      </div>

      {issue.labels?.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {issue.labels.slice(0, 3).map(label => (
            <Badge key={label} variant="secondary" className="px-1.5 py-0 text-xs">
              {label}
            </Badge>
          ))}
        </div>
      ) : null}
    </button>
  )
}

function IssueTypeIcon({ issueType }: { issueType: string }) {
  if (issueType === 'Bug') {
    return <Bug className="h-3 w-3" />
  }
  if (issueType === 'Story') {
    return <BookOpen className="h-3 w-3" />
  }
  if (issueType === 'Epic') {
    return <Layers className="h-3 w-3" />
  }
  return <CheckSquare className="h-3 w-3" />
}
