import { useState, useCallback, useEffect } from 'react'
import { JiraIssueBrowser }  from '../components/Authoring/JiraIssueBrowser'
import { DitaEditor }        from '../components/Authoring/DitaEditor'
import { QualityPanel }      from '../components/Authoring/QualityPanel'
import { QueryPlanPanel }    from '../components/Authoring/QueryPlanPanel'
import { SafetyPanel }       from '../components/Authoring/SafetyPanel'
import { FileText, ChevronRight, Clock, RotateCcw } from 'lucide-react'
import { useAuthorMemory }   from '../hooks/useAuthorMemory'
import type { ResearchContext } from '../components/Authoring/QueryPlanPanel'

export interface JiraIssue {
    issue_key:   string
    summary:     string
    description: string
    issue_type:  string
    status:      string
    priority:    string
    labels:      string[]
    comments?:   { author: string; body_text: string; created: string }[]
}

export interface GeneratedDita {
    filename:          string
    content:           string
    dita_type:         string
    quality_score:     number
    quality_breakdown: {
        structure:        number
        content_richness: number
        dita_features:    number
        aem_readiness:    number
    }
    validation:   { label: string; passing: boolean }[]
    sources_used: { label: string; count: number; color: string }[]
}

type Stage = 'idle' | 'research' | 'generating' | 'done'

export default function AuthoringPage() {
    const memory = useAuthorMemory()

    const [selectedIssue,      setSelectedIssue]      = useState<JiraIssue | null>(null)
    const [researchContext,    setResearchContext]     = useState<ResearchContext | null>(null)
    const [generatedDita,      setGeneratedDita]       = useState<GeneratedDita | null>(null)
    const [isGenerating,       setIsGenerating]        = useState(false)
    const [stage,              setStage]               = useState<Stage>('idle')
    const [showRestoreBanner,  setShowRestoreBanner]   = useState(false)

    useEffect(() => {
        if (memory.restored && memory.lastIssueKey && !selectedIssue) {
            setShowRestoreBanner(true)
        }
    }, [memory.restored, memory.lastIssueKey])

    const handleIssueSelect = useCallback(async (issue: JiraIssue) => {
        setSelectedIssue(issue)
        setResearchContext(null)
        setGeneratedDita(null)
        setShowRestoreBanner(false)

        const preferredType = await memory.getPreferredDitaType(issue.issue_type, issue.labels)
        const nextStage: Stage = memory.showResearchStep ? 'research' : 'generating'
        setStage(nextStage)
        memory.rememberIssue(issue.issue_key, issue.summary, preferredType, nextStage)
    }, [memory])

    const handleResearchComplete = useCallback((context: ResearchContext) => {
        setResearchContext(context)
        setStage('generating')
        memory.rememberStage('generating')
    }, [memory])

    const handleSkipResearch = useCallback(() => {
        setStage('generating')
        memory.rememberStage('generating')
    }, [memory])

    const handleGenerating = useCallback(() => {
        setIsGenerating(true)
        setStage('generating')
    }, [])

    const handleGenerated = useCallback((dita: GeneratedDita) => {
        setGeneratedDita(dita)
        setIsGenerating(false)
        setStage('done')
        memory.rememberStage('done')
        memory.recordAction('generated')
    }, [memory])

    const handleStartScratch = useCallback((content: string, filename: string) => {
        setGeneratedDita(prev => prev ? { ...prev, content, filename, quality_score: 0 } : null)
        memory.recordAction('scratch_started')
    }, [memory])

    const handleApproved = useCallback(() => {
        memory.recordAction('approved')
    }, [memory])

    const renderCenter = () => {
        if (!selectedIssue) {
            return (
                <div className="flex flex-col items-center justify-center h-full text-center px-8">
                    <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                        <FileText className="w-6 h-6 text-blue-400" />
                    </div>
                    <p className="text-sm font-medium text-gray-700 mb-1">
                        Welcome back{memory.authorName !== 'Author' ? `, ${memory.authorName}` : ''}
                    </p>
                    <p className="text-xs text-gray-400 mb-4">Select an issue from the left panel</p>

                    {memory.stats.generated > 0 && (
                        <div className="flex gap-6 mb-5">
                            <div className="text-center">
                                <p className="text-xl font-medium text-gray-800">{memory.stats.generated}</p>
                                <p className="text-xs text-gray-400">generated</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xl font-medium text-green-600">{memory.stats.approved}</p>
                                <p className="text-xs text-gray-400">approved</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xl font-medium text-red-500">{memory.stats.rejected}</p>
                                <p className="text-xs text-gray-400">rejected</p>
                            </div>
                        </div>
                    )}

                    {memory.recentIssues.length > 0 && (
                        <div className="w-full max-w-xs">
                            <p className="text-xs text-gray-400 mb-2 flex items-center gap-1 justify-center">
                                <Clock className="w-3 h-3" /> Recent issues
                            </p>
                            <div className="space-y-1.5">
                                {memory.recentIssues.slice(0, 5).map(r => (
                                    <div key={r.issue_key}
                                        className="text-left text-xs px-3 py-2 rounded-lg border border-gray-200 bg-white">
                                        <span className="font-mono font-medium text-blue-600 mr-2">{r.issue_key}</span>
                                        <span className="text-gray-600">{r.summary.slice(0, 45)}</span>
                                        <span className="text-gray-400 ml-1">· {r.dita_type}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
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
        <div className="flex flex-col h-[calc(100vh-64px)] bg-gray-50">

            {showRestoreBanner && (
                <div className="bg-blue-50 border-b border-blue-200 px-6 py-2 flex items-center gap-3">
                    <RotateCcw className="w-3.5 h-3.5 text-blue-500" />
                    <p className="text-xs text-blue-700 flex-1">
                        Last session: <span className="font-mono font-medium">{memory.lastIssueKey}</span>
                        {' — '}{memory.lastIssueSummary.slice(0, 60)}
                    </p>
                    <button onClick={() => setShowRestoreBanner(false)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                        Dismiss
                    </button>
                </div>
            )}

            <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
                <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-600" />
                    <span className="text-sm font-medium text-gray-900">DITA Authoring</span>
                    <span className="text-xs text-gray-400 ml-1">
                        Jira → Research → Generate → Review → Publish
                    </span>
                </div>

                <div className="flex items-center gap-1.5 text-xs">
                    <StageChip label="Select"   active={stage === 'idle'}       done={stage !== 'idle'} />
                    <ChevronRight className="w-3 h-3 text-gray-300" />
                    <StageChip label="Research" active={stage === 'research'}   done={['generating','done'].includes(stage)} />
                    <ChevronRight className="w-3 h-3 text-gray-300" />
                    <StageChip label="Generate" active={stage === 'generating'} done={stage === 'done'} />
                    <ChevronRight className="w-3 h-3 text-gray-300" />
                    <StageChip label="Done"     active={false}                  done={stage === 'done'} />

                    {selectedIssue && (
                        <span className="ml-2 bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-medium font-mono">
                            {selectedIssue.issue_key}
                        </span>
                    )}
                    {researchContext && (
                        <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded font-medium">
                            {researchContext.total_chunks} chunks
                        </span>
                    )}
                    {generatedDita && generatedDita.quality_score > 0 && (
                        <span className={`px-2 py-0.5 rounded font-medium ${
                            generatedDita.quality_score >= memory.minQualityScore
                                ? 'bg-green-50 text-green-700'
                                : 'bg-amber-50 text-amber-700'
                        }`}>
                            {generatedDita.quality_score}/100
                            {generatedDita.quality_score < memory.minQualityScore && ' ⚠'}
                        </span>
                    )}
                    {memory.authorName !== 'Author' && (
                        <span className="ml-2 text-gray-400 border-l border-gray-200 pl-2">
                            {memory.authorName}
                        </span>
                    )}
                </div>
            </div>

            <div className="flex flex-1 overflow-hidden">
                <div className="w-72 flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
                    <JiraIssueBrowser
                        onSelect={handleIssueSelect}
                        selectedKey={selectedIssue?.issue_key}
                        lastIssueKey={memory.lastIssueKey}
                        recentIssues={memory.recentIssues}
                    />
                </div>

                <div className="flex-1 overflow-y-auto bg-white min-w-0">
                    {renderCenter()}
                </div>

                <div className="w-64 flex-shrink-0 border-l border-gray-200 bg-gray-50 overflow-y-auto">
                    {stage === 'done' && generatedDita ? (
                        <SafetyPanel
                            issue={selectedIssue}
                            generatedDita={generatedDita}
                            onStartScratch={handleStartScratch}
                            onApproved={handleApproved}
                        />
                    ) : (
                        <QualityPanel
                            dita={generatedDita}
                            issue={selectedIssue}
                            researchContext={researchContext}
                        />
                    )}
                </div>
            </div>
        </div>
    )
}

function StageChip({ label, active, done }: { label: string; active: boolean; done: boolean }) {
    return (
        <span className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
            active ? 'bg-blue-600 text-white'
            : done  ? 'bg-green-100 text-green-700'
            : 'text-gray-400'
        }`}>
            {done ? `✓ ${label}` : label}
        </span>
    )
}
