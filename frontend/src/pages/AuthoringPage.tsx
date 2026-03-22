import { useCallback, useEffect, useState } from 'react'
import { ChevronRight, Clock, FileText, RotateCcw } from 'lucide-react'
import { DitaEditor } from '../components/Authoring/DitaEditor'
import { JiraIssueBrowser } from '../components/Authoring/JiraIssueBrowser'
import { QualityPanel } from '../components/Authoring/QualityPanel'
import { QueryPlanPanel, type ResearchContext } from '../components/Authoring/QueryPlanPanel'
import { SafetyPanel } from '../components/Authoring/SafetyPanel'
import { useAuthorMemory } from '../hooks/useAuthorMemory'
import { apiUrl, getTenantId, withTenantHeaders } from '@/utils/api'

export interface JiraAttachment {
  id: string
  filename: string
  mime_type: string
  size_bytes?: number
  kind?: string
  is_video?: boolean
  is_image?: boolean
  relative_path?: string
  download_url?: string
}

export interface JiraIssue {
  issue_key: string
  summary: string
  description: string
  issue_type: string
  status: string
  priority: string
  labels: string[]
  components?: string[]
  fix_versions?: string[]
  attachments?: JiraAttachment[]
  comments?: { author: string; body_text: string; created: string }[]
}

export interface GeneratedDita {
  filename: string
  content: string
  dita_type: string
  quality_score: number
  quality_breakdown: {
    structure: number
    content_richness: number
    dita_features: number
    aem_readiness: number
  }
  validation: {
    label: string
    passing: boolean
  }[]
  sources_used: {
    label: string
    count: number
    color: string
  }[]
}

type Stage = 'idle' | 'research' | 'generating' | 'done'

const EMPTY_BREAKDOWN = {
  structure: 0,
  content_richness: 0,
  dita_features: 0,
  aem_readiness: 0,
}

export default function AuthoringPage() {
  const memory = useAuthorMemory()
  const tenantId = getTenantId()

  const [selectedIssue, setSelectedIssue] = useState<JiraIssue | null>(null)
  const [researchContext, setResearchContext] = useState<ResearchContext | null>(null)
  const [generatedDita, setGeneratedDita] = useState<GeneratedDita | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [stage, setStage] = useState<Stage>('idle')
  const [showRestoreBanner, setShowRestoreBanner] = useState(false)
  const [rightPanelTab, setRightPanelTab] = useState<'review' | 'safety'>('review')

  useEffect(() => {
    if (memory.restored && memory.lastIssueKey && !selectedIssue) {
      setShowRestoreBanner(true)
    }
  }, [memory.lastIssueKey, memory.restored, selectedIssue])

  const handleIssueSelect = useCallback(
    async (issue: JiraIssue) => {
      setSelectedIssue(issue)
      setResearchContext(null)
      setGeneratedDita(null)
      setIsGenerating(false)
      setShowRestoreBanner(false)
      setRightPanelTab('review')

      const preferredType = await memory.getPreferredDitaType(issue.issue_type, issue.labels)
      const nextStage: Stage = memory.showResearchStep ? 'research' : 'generating'
      setStage(nextStage)
      void memory.rememberIssue(issue.issue_key, issue.summary, preferredType, nextStage)

      void (async () => {
        try {
          const response = await fetch(apiUrl(`/api/v1/jira/issue/${issue.issue_key}`), {
            headers: withTenantHeaders(),
          })
          if (!response.ok) {
            return
          }
          const fullIssue = (await response.json()) as JiraIssue
          setSelectedIssue(current =>
            current?.issue_key === issue.issue_key ? { ...current, ...fullIssue } : current,
          )
        } catch {
          // Keep the lightweight issue card data if the detail fetch fails.
        }
      })()
    },
    [memory],
  )

  const handleResearchComplete = useCallback(
    (context: ResearchContext) => {
      setResearchContext(context)
      setStage('generating')
      void memory.rememberStage('generating')
    },
    [memory],
  )

  const handleSkipResearch = useCallback(() => {
    setResearchContext(null)
    setStage('generating')
    void memory.rememberStage('generating')
  }, [memory])

  const handleGenerating = useCallback(() => {
    setIsGenerating(true)
    setStage('generating')
  }, [])

  const handleGenerated = useCallback(
    (dita: GeneratedDita) => {
      setGeneratedDita(dita)
      setIsGenerating(false)
      setStage('done')
      setRightPanelTab('review')
      void memory.rememberStage('done')
      if (isGenerating) {
        void memory.recordAction('generated')
      }
    },
    [isGenerating, memory],
  )

  const handleStartScratch = useCallback(
    (content: string, filename: string, ditaType: string) => {
      setGeneratedDita({
        filename,
        content,
        dita_type: ditaType,
        quality_score: 0,
        quality_breakdown: EMPTY_BREAKDOWN,
        validation: [],
        sources_used: [{ label: 'Scratch template', count: 1, color: 'gray' }],
      })
      setStage('done')
      setRightPanelTab('review')
      void memory.recordAction('scratch_started')
    },
    [memory],
  )

  const handleApproved = useCallback(() => {
    void memory.recordAction('approved')
  }, [memory])

  const handleRegenerate = useCallback(() => {
    setGeneratedDita(null)
    setIsGenerating(false)
    setStage('generating')
    setRightPanelTab('review')
    void memory.rememberStage('generating')
  }, [memory])

  const renderCenter = () => {
    if (!selectedIssue) {
      return (
        <div className="flex h-full flex-col items-center justify-center px-8 text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50">
            <FileText className="h-6 w-6 text-blue-400" />
          </div>
          <p className="mb-1 text-sm font-medium text-gray-700">
            Welcome back{memory.authorName !== 'Author' ? `, ${memory.authorName}` : ''}
          </p>
          <p className="mb-4 text-xs text-gray-400">Select an issue from the left panel to begin authoring.</p>

          {memory.stats.generated > 0 ? (
            <div className="mb-5 flex gap-6">
              <StatCard label="generated" value={memory.stats.generated} valueClassName="text-gray-800" />
              <StatCard label="approved" value={memory.stats.approved} valueClassName="text-emerald-600" />
              <StatCard label="rejected" value={memory.stats.rejected} valueClassName="text-red-500" />
            </div>
          ) : null}

          {memory.recentIssues.length ? (
            <div className="w-full max-w-xs">
              <p className="mb-2 flex items-center justify-center gap-1 text-xs text-gray-400">
                <Clock className="h-3 w-3" />
                Recent issues
              </p>
              <div className="space-y-1.5">
                {memory.recentIssues.slice(0, 5).map(issue => (
                  <div key={issue.issue_key} className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-xs">
                    <span className="mr-2 font-mono font-medium text-blue-600">{issue.issue_key}</span>
                    <span className="text-gray-600">{issue.summary.slice(0, 45)}</span>
                    <span className="ml-1 text-gray-400">/ {issue.dita_type}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )
    }

    if (stage === 'research') {
      return (
        <QueryPlanPanel
          issue={selectedIssue}
          onResearchComplete={handleResearchComplete}
          onSkip={handleSkipResearch}
        />
      )
    }

    return (
      <DitaEditor
        issue={selectedIssue}
        generatedDita={generatedDita}
        isGenerating={isGenerating}
        researchContext={researchContext}
        onGenerating={handleGenerating}
        onGenerated={handleGenerated}
      />
    )
  }

  return (
    <div className="-mx-6 -my-8 flex h-full min-h-0 flex-col bg-gray-50">
      {showRestoreBanner ? (
        <div className="flex items-center gap-3 border-b border-blue-200 bg-blue-50 px-6 py-2">
          <RotateCcw className="h-3.5 w-3.5 text-blue-500" />
          <p className="flex-1 text-xs text-blue-700">
            Last session: <span className="font-mono font-medium">{memory.lastIssueKey}</span>
            {' / '}
            {memory.lastIssueSummary.slice(0, 60)}
          </p>
          <button
            onClick={() => setShowRestoreBanner(false)}
            className="text-xs font-medium text-blue-600 hover:text-blue-800"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      <div className="shrink-0 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-blue-600" />
          <span className="text-sm font-medium text-gray-900">DITA Authoring</span>
          <span className="ml-1 text-xs text-gray-400">Jira to research to generation to review</span>
        </div>

        <div className="flex items-center gap-1.5 text-xs">
          <StageChip label="Select" active={stage === 'idle'} done={stage !== 'idle'} />
          <ChevronRight className="h-3 w-3 text-gray-300" />
          <StageChip label="Research" active={stage === 'research'} done={['generating', 'done'].includes(stage)} />
          <ChevronRight className="h-3 w-3 text-gray-300" />
          <StageChip label="Generate" active={stage === 'generating'} done={stage === 'done'} />
          <ChevronRight className="h-3 w-3 text-gray-300" />
          <StageChip label="Review" active={stage === 'done'} done={stage === 'done'} />

          {selectedIssue ? (
            <span className="ml-2 rounded bg-blue-50 px-2 py-0.5 font-mono font-medium text-blue-700">
              {selectedIssue.issue_key}
            </span>
          ) : null}
          {researchContext ? (
            <span className="rounded bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700">
              {researchContext.total_chunks} chunks
            </span>
          ) : null}
          {generatedDita ? (
            <span
              className={`rounded px-2 py-0.5 font-medium ${
                generatedDita.quality_score >= memory.minQualityScore ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
              }`}
            >
              {generatedDita.quality_score}/100
            </span>
          ) : null}
          {memory.authorName !== 'Author' ? (
            <span className="ml-2 border-l border-gray-200 pl-2 text-gray-400">{memory.authorName}</span>
          ) : null}
          <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-slate-500">{tenantId}</span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="w-72 shrink-0 overflow-y-auto border-r border-gray-200 bg-white">
          <JiraIssueBrowser
            onSelect={handleIssueSelect}
            selectedKey={selectedIssue?.issue_key}
            lastIssueKey={memory.lastIssueKey}
            recentIssues={memory.recentIssues}
          />
        </div>

        <div className="min-w-0 flex-1 overflow-y-auto bg-white">{renderCenter()}</div>

        <div className="flex min-h-0 w-[22rem] shrink-0 flex-col border-l border-gray-200 bg-gray-50 xl:w-[24rem]">
          {generatedDita ? (
            <div className="border-b border-gray-200 bg-white px-3 py-2">
              <div className="grid grid-cols-2 gap-2 rounded-xl bg-gray-100 p-1">
                <button
                  onClick={() => setRightPanelTab('review')}
                  className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                    rightPanelTab === 'review' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Review
                </button>
                <button
                  onClick={() => setRightPanelTab('safety')}
                  className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                    rightPanelTab === 'safety' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Safety
                </button>
              </div>
            </div>
          ) : null}

          <div className="min-h-0 flex-1 overflow-y-auto bg-white">
            {!generatedDita || rightPanelTab === 'review' ? (
              <QualityPanel
                dita={generatedDita}
                issue={selectedIssue}
                researchContext={researchContext}
                onRegenerate={handleRegenerate}
                onDitaUpdated={handleGenerated}
              />
            ) : (
              <SafetyPanel
                issue={selectedIssue}
                generatedDita={generatedDita}
                onStartScratch={handleStartScratch}
                onApproved={handleApproved}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function StageChip({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
        active ? 'bg-blue-600 text-white' : done ? 'bg-emerald-100 text-emerald-700' : 'text-gray-400'
      }`}
    >
      {done ? `OK ${label}` : label}
    </span>
  )
}

function StatCard({
  label,
  value,
  valueClassName,
}: {
  label: string
  value: number
  valueClassName: string
}) {
  return (
    <div className="text-center">
      <p className={`text-xl font-medium ${valueClassName}`}>{value}</p>
      <p className="text-xs text-gray-400">{label}</p>
    </div>
  )
}
