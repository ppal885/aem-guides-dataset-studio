import { useState, useCallback } from 'react'
import { JiraIssueBrowser } from '../components/Authoring/JiraIssueBrowser'
import { DitaEditor } from '../components/Authoring/DitaEditor'
import { QualityPanel } from '../components/Authoring/QualityPanel'
import { FileText } from 'lucide-react'

export interface JiraIssue {
    issue_key: string
    summary: string
    description: string
    issue_type: string
    status: string
    priority: string
    labels: string[]
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

export default function AuthoringPage() {
    const [selectedIssue, setSelectedIssue] = useState<JiraIssue | null>(null)
    const [generatedDita, setGeneratedDita] = useState<GeneratedDita | null>(null)
    const [isGenerating, setIsGenerating] = useState(false)

    const handleIssueSelect = useCallback((issue: JiraIssue) => {
        setSelectedIssue(issue)
        setGeneratedDita(null)
    }, [])

    const handleGenerated = useCallback((dita: GeneratedDita) => {
        setGeneratedDita(dita)
        setIsGenerating(false)
    }, [])

    return (
        <div className="flex flex-col h-[calc(100vh-64px)] bg-gray-50">
            {/* Page header */}
            <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
                <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-600" />
                    <span className="text-sm font-medium text-gray-900">DITA Authoring</span>
                    <span className="text-xs text-gray-400 ml-2">
            Jira → DITA in one click
          </span>
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                    {selectedIssue && (
                        <span className="bg-blue-50 text-blue-700 px-2 py-1 rounded font-medium">
              {selectedIssue.issue_key} selected
            </span>
                    )}
                    {generatedDita && (
                        <span className="bg-green-50 text-green-700 px-2 py-1 rounded font-medium">
              {generatedDita.filename} ready
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

                {/* Panel 2 — DITA editor */}
                <div className="flex-1 overflow-y-auto bg-white">
                    <DitaEditor
                        issue={selectedIssue}
                        generatedDita={generatedDita}
                        isGenerating={isGenerating}
                        onGenerating={() => setIsGenerating(true)}
                        onGenerated={handleGenerated}
                    />
                </div>

                {/* Panel 3 — Quality + validation */}
                <div className="w-64 flex-shrink-0 border-l border-gray-200 bg-gray-50 overflow-y-auto">
                    <QualityPanel dita={generatedDita} issue={selectedIssue} />
                </div>
            </div>
        </div>
    )
}
