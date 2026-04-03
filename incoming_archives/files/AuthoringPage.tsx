import { useState, useCallback } from 'react'
import { JiraIssueBrowser }  from '../components/Authoring/JiraIssueBrowser'
import { DitaEditor }        from '../components/Authoring/DitaEditor'
import { QualityPanel }      from '../components/Authoring/QualityPanel'
import { QueryPlanPanel }    from '../components/Authoring/QueryPlanPanel'
import { FileText, ChevronRight } from 'lucide-react'
import type { ResearchContext } from '../components/Authoring/QueryPlanPanel'

export interface JiraIssue {
    issue_key:    string
    summary:      string
    description:  string
    issue_type:   string
    status:       string
    priority:     string
    labels:       string[]
    comments?:    { author: string; body_text: string; created: string }[]
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

// ── Stages ────────────────────────────────────────────────────────────────────
// idle → research → generating → done
type Stage = 'idle' | 'research' | 'generating' | 'done'

export default function AuthoringPage() {
    const [selectedIssue,   setSelectedIssue]   = useState<JiraIssue | null>(null)
    const [researchContext, setResearchContext]  = useState<ResearchContext | null>(null)
    const [generatedDita,   setGeneratedDita]    = useState<GeneratedDita | null>(null)
    const [isGenerating,    setIsGenerating]     = useState(false)
    const [stage,           setStage]            = useState<Stage>('idle')

    // Issue selected → go to research stage
    const handleIssueSelect = useCallback((issue: JiraIssue) => {
        setSelectedIssue(issue)
        setResearchContext(null)
        setGeneratedDita(null)
        setStage('research')
    }, [])

    // Research complete → go to generating
    const handleResearchComplete = useCallback((context: ResearchContext) => {
        setResearchContext(context)
        setStage('generating')
    }, [])

    // Skip research → go straight to generating
    const handleSkipResearch = useCallback(() => {
        setStage('generating')
    }, [])

    // Generating
    const handleGenerating = useCallback(() => {
        setIsGenerating(true)
        setStage('generating')
    }, [])

    // Done
    const handleGenerated = useCallback((dita: GeneratedDita) => {
        setGeneratedDita(dita)
        setIsGenerating(false)
        setStage('done')
    }, [])

    // Decide what to show in center panel
    const renderCenter = () => {
        if (!selectedIssue) {
            return (
                <div className="flex flex-col items-center justify-center h-full text-center px-8">
                    <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                        <FileText className="w-6 h-6 text-blue-400" />
                    </div>
                    <p className="text-sm font-medium text-gray-700 mb-1">Select a Jira issue</p>
                    <p className="text-xs text-gray-400">Pick an issue from the left panel to start</p>
                </div>
            )
        }

        // Research stage — show query plan panel
        if (stage === 'research') {
            return (
                <QueryPlanPanel
                    issue={selectedIssue}
                    onResearchComplete={handleResearchComplete}
                    onSkip={handleSkipResearch}
                />
            )
        }

        // Generating / done — show DITA editor
        // Pass research context so generation uses it
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

            {/* Page header with stage indicator */}
            <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
                <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-600" />
                    <span className="text-sm font-medium text-gray-900">DITA Authoring</span>
                    <span className="text-xs text-gray-400 ml-1">
                        Jira → Research → Generate → Review → Publish
                    </span>
                </div>

                <div className="flex items-center gap-1.5 text-xs">
                    <StageChip
                        label="Select"
                        active={stage === 'idle'}
                        done={stage !== 'idle'}
                    />
                    <ChevronRight className="w-3 h-3 text-gray-300" />
                    <StageChip
                        label="Research"
                        active={stage === 'research'}
                        done={stage === 'generating' || stage === 'done'}
                    />
                    <ChevronRight className="w-3 h-3 text-gray-300" />
                    <StageChip
                        label="Generate"
                        active={stage === 'generating'}
                        done={stage === 'done'}
                    />
                    <ChevronRight className="w-3 h-3 text-gray-300" />
                    <StageChip label="Done" active={false} done={stage === 'done'} />

                    {/* Context indicators */}
                    {selectedIssue && (
                        <span className="ml-2 bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-medium">
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
                            generatedDita.quality_score >= 80
                                ? 'bg-green-50 text-green-700'
                                : 'bg-yellow-50 text-yellow-700'
                        }`}>
                            {generatedDita.quality_score}/100
                        </span>
                    )}
                </div>
            </div>

            {/* 3-panel layout */}
            <div className="flex flex-1 overflow-hidden">

                {/* Panel 1 — Jira browser */}
                <div className="w-72 flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
                    <JiraIssueBrowser
                        onSelect={handleIssueSelect}
                        selectedKey={selectedIssue?.issue_key}
                    />
                </div>

                {/* Panel 2 — Research or Editor */}
                <div className="flex-1 overflow-y-auto bg-white min-w-0">
                    {renderCenter()}
                </div>

                {/* Panel 3 — Quality panel */}
                <div className="w-64 flex-shrink-0 border-l border-gray-200 bg-gray-50 overflow-y-auto">
                    <QualityPanel
                        dita={generatedDita}
                        issue={selectedIssue}
                        researchContext={researchContext}
                    />
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
