import { useState, useEffect, useCallback } from 'react'
import { Search, RefreshCw, Bug, BookOpen, CheckSquare, Layers } from 'lucide-react'
import { Input } from '../ui/input'
import { Badge } from '../ui/badge'
import type { JiraIssue } from '../../pages/AuthoringPage'

const API_BASE = '/api/v1'

const FILTER_TABS = [
    { label: 'My Issues', jql: 'assignee = currentUser() ORDER BY updated DESC' },
    { label: 'Sprint',    jql: 'sprint in openSprints() ORDER BY priority ASC' },
    { label: 'Done',      jql: 'status = Done ORDER BY updated DESC' },
]

const STATUS_COLORS: Record<string, string> = {
    'Done':        'bg-green-50 text-green-700',
    'In Progress': 'bg-yellow-50 text-yellow-700',
    'Open':        'bg-gray-100 text-gray-600',
    'To Do':       'bg-gray-100 text-gray-600',
    'Closed':      'bg-green-50 text-green-700',
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
    'Bug':       <Bug className="w-3 h-3" />,
    'Story':     <BookOpen className="w-3 h-3" />,
    'Task':      <CheckSquare className="w-3 h-3" />,
    'Epic':      <Layers className="w-3 h-3" />,
}

const PRIORITY_DOT: Record<string, string> = {
    'Highest': 'bg-red-500',
    'High':    'bg-orange-400',
    'Medium':  'bg-yellow-400',
    'Low':     'bg-blue-400',
    'Lowest':  'bg-gray-400',
}

interface Props {
    onSelect: (issue: JiraIssue) => void
    selectedKey?: string
}

export function JiraIssueBrowser({ onSelect, selectedKey }: Props) {
    const [issues, setIssues]       = useState<JiraIssue[]>([])
    const [loading, setLoading]     = useState(false)
    const [error, setError]         = useState('')
    const [search, setSearch]       = useState('')
    const [activeTab, setActiveTab] = useState(0)

    const fetchIssues = useCallback(async (jql: string) => {
        setLoading(true)
        setError('')
        try {
            const res = await fetch(`${API_BASE}/jira/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jql, max_results: 30 }),
            })
            if (!res.ok) throw new Error(`Jira API error: ${res.status}`)
            const data = await res.json()
            setIssues(data.issues || [])
        } catch (e: any) {
            setError(e.message || 'Failed to fetch issues')
            setIssues([])
        } finally {
            setLoading(false)
        }
    }, [])

    // Fetch by direct issue key
    const fetchByKey = useCallback(async (key: string) => {
        setLoading(true)
        setError('')
        try {
            const res = await fetch(`${API_BASE}/jira/issue/${key}`)
            if (!res.ok) throw new Error(`Issue not found: ${key}`)
            const data = await res.json()
            setIssues([data])
        } catch (e: any) {
            setError(e.message)
            setIssues([])
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchIssues(FILTER_TABS[activeTab].jql)
    }, [activeTab, fetchIssues])

    const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key !== 'Enter') return
        const val = search.trim().toUpperCase()
        if (!val) {
            fetchIssues(FILTER_TABS[activeTab].jql)
            return
        }
        // Looks like an issue key
        if (/^[A-Z]+-\d+$/.test(val)) {
            fetchByKey(val)
        } else {
            fetchIssues(`text ~ "${search}" ORDER BY updated DESC`)
        }
    }

    const filtered = issues.filter(i =>
        !search || i.summary.toLowerCase().includes(search.toLowerCase()) ||
        i.issue_key.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-4 pt-4 pb-2 border-b border-gray-100">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                    Jira Issues
                </p>
                <div className="relative mb-3">
                    <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-gray-400" />
                    <Input
                        className="pl-8 text-xs h-8"
                        placeholder="Search or enter AEM-123..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        onKeyDown={handleSearch}
                    />
                </div>
                {/* Filter tabs */}
                <div className="flex gap-1">
                    {FILTER_TABS.map((tab, i) => (
                        <button
                            key={tab.label}
                            onClick={() => { setActiveTab(i); setSearch('') }}
                            className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
                                activeTab === i
                                    ? 'bg-blue-600 text-white'
                                    : 'text-gray-500 hover:bg-gray-100'
                            }`}
                        >
                            {tab.label}
                        </button>
                    ))}
                    <button
                        onClick={() => fetchIssues(FILTER_TABS[activeTab].jql)}
                        className="ml-auto text-gray-400 hover:text-gray-600 p-1"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Issue list */}
            <div className="flex-1 overflow-y-auto px-3 py-2">
                {loading && (
                    <div className="flex flex-col gap-2 mt-2">
                        {[1,2,3,4].map(n => (
                            <div key={n} className="h-20 bg-gray-100 rounded-lg animate-pulse" />
                        ))}
                    </div>
                )}

                {error && (
                    <div className="mt-4 p-3 bg-red-50 rounded-lg text-xs text-red-600">
                        {error}
                        <p className="mt-1 text-red-400">Check Jira credentials in Settings</p>
                    </div>
                )}

                {!loading && !error && filtered.length === 0 && (
                    <div className="mt-8 text-center text-xs text-gray-400">
                        <p>No issues found</p>
                        <p className="mt-1">Try a different filter or search</p>
                    </div>
                )}

                {!loading && filtered.map(issue => (
                    <IssueCard
                        key={issue.issue_key}
                        issue={issue}
                        isSelected={issue.issue_key === selectedKey}
                        onClick={() => onSelect(issue)}
                    />
                ))}
            </div>

            {!loading && filtered.length > 0 && (
                <div className="px-4 py-2 border-t border-gray-100 text-xs text-gray-400">
                    {filtered.length} issue{filtered.length !== 1 ? 's' : ''}
                </div>
            )}
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
    const typeIcon = TYPE_ICONS[issue.issue_type] || <CheckSquare className="w-3 h-3" />

    return (
        <div
            onClick={onClick}
            className={`mb-2 p-3 rounded-lg border cursor-pointer transition-all ${
                isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-sm'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
            }`}
        >
            <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-blue-600">{issue.issue_key}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium flex items-center gap-1 ${statusClass}`}>
          {typeIcon}
                    {issue.issue_type}
        </span>
            </div>
            <p className="text-xs text-gray-800 leading-relaxed mb-2 line-clamp-2">
                {issue.summary}
            </p>
            <div className="flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full ${priorityDot}`} />
                <span className="text-xs text-gray-400">{issue.priority || 'No priority'}</span>
                <span className={`ml-auto text-xs px-1.5 py-0.5 rounded ${statusClass}`}>
          {issue.status}
        </span>
            </div>
            {issue.labels && issue.labels.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                    {issue.labels.slice(0, 3).map(l => (
                        <Badge key={l} variant="secondary" className="text-xs py-0 px-1.5">
                            {l}
                        </Badge>
                    ))}
                </div>
            )}
        </div>
    )
}
