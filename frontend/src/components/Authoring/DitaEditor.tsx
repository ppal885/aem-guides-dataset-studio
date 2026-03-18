import { useState } from 'react'
import {
    Wand2, Download, Upload, Copy, RefreshCw,
    ChevronRight, FileText, AlertCircle, CheckCircle2
} from 'lucide-react'
import { Button } from '../ui/button.tsx'
import { Input } from '../ui/input.tsx'
import type { JiraIssue, GeneratedDita } from '../../pages/AuthoringPage.tsx'

const API_BASE = '/api/v1'

type Tab = 'preview' | 'xml' | 'rendered'

interface Props {
    issue: JiraIssue | null
    generatedDita: GeneratedDita | null
    isGenerating: boolean
    onGenerating: () => void
    onGenerated: (dita: GeneratedDita) => void
}

export function DitaEditor({
                               issue,
                               generatedDita,
                               isGenerating,
                               onGenerating,
                               onGenerated,
                           }: Props) {
    const [activeTab, setActiveTab] = useState<Tab>('preview')
    const [refineText, setRefineText] = useState('')
    const [refining, setRefining] = useState(false)
    const [copied, setCopied] = useState(false)
    const [uploadStatus, setUploadStatus] = useState<'idle'|'uploading'|'done'|'error'>('idle')

    const handleGenerate = async () => {
        if (!issue) return
        onGenerating()
        try {
            const res = await fetch(`${API_BASE}/ai/generate-dita-from-jira`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    issue_key: issue.issue_key,
                    dita_type: 'auto',
                }),
            })
            if (!res.ok) throw new Error('Generation failed')
            const data = await res.json()
            onGenerated(data)
        } catch (e) {
            console.error(e)
            onGenerated({
                filename: `${issue.issue_key}-task.dita`,
                content: `<!-- Generation failed. Check MCP server connection. -->`,
                dita_type: 'task',
                quality_score: 0,
                quality_breakdown: { structure: 0, content_richness: 0, dita_features: 0, aem_readiness: 0 },
                validation: [],
                sources_used: [],
            })
        }
    }

    const handleRefine = async () => {
        if (!generatedDita || !refineText.trim()) return
        setRefining(true)
        try {
            const res = await fetch(`${API_BASE}/ai/refine-dita`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: generatedDita.filename,
                    current_content: generatedDita.content,
                    instruction: refineText,
                }),
            })
            if (!res.ok) throw new Error('Refine failed')
            const data = await res.json()
            onGenerated(data)
            setRefineText('')
        } catch (e) {
            console.error(e)
        } finally {
            setRefining(false)
        }
    }

    const handleCopy = () => {
        if (!generatedDita) return
        navigator.clipboard.writeText(generatedDita.content)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    const handleDownload = () => {
        if (!generatedDita) return
        const blob = new Blob([generatedDita.content], { type: 'application/xml' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = generatedDita.filename
        a.click()
        URL.revokeObjectURL(url)
    }

    const handleUploadToAem = async () => {
        if (!generatedDita) return
        setUploadStatus('uploading')
        try {
            const res = await fetch(`${API_BASE}/aem/upload-dita`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: generatedDita.filename,
                    content: generatedDita.content,
                }),
            })
            if (!res.ok) throw new Error('Upload failed')
            setUploadStatus('done')
            setTimeout(() => setUploadStatus('idle'), 3000)
        } catch {
            setUploadStatus('error')
            setTimeout(() => setUploadStatus('idle'), 3000)
        }
    }

    // ── Empty state ──────────────────────────────────────────────────────────
    if (!issue) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center px-8">
                <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                    <FileText className="w-6 h-6 text-blue-400" />
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">Select a Jira issue</p>
                <p className="text-xs text-gray-400">
                    Pick an issue from the left panel to generate DITA
                </p>
            </div>
        )
    }

    // ── Issue selected, not yet generated ────────────────────────────────────
    if (!generatedDita && !isGenerating) {
        return (
            <div className="flex flex-col h-full">
                <IssueHeader issue={issue} />
                <div className="flex flex-col items-center justify-center flex-1 px-8 text-center">
                    <div className="max-w-sm">
                        <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4 mx-auto">
                            <Wand2 className="w-6 h-6 text-blue-500" />
                        </div>
                        <p className="text-sm font-medium text-gray-800 mb-1">Ready to generate</p>
                        <p className="text-xs text-gray-500 mb-6">
                            Click below to generate a spec-compliant DITA topic from{' '}
                            <strong>{issue.issue_key}</strong> using your RAG knowledge base
                        </p>
                        <Button
                            onClick={handleGenerate}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-6"
                        >
                            <Wand2 className="w-4 h-4 mr-2" />
                            Generate DITA
                        </Button>
                        <p className="text-xs text-gray-400 mt-3">
                            Uses Experience League + DITA 1.3 spec + expert examples
                        </p>
                    </div>
                </div>
            </div>
        )
    }

    // ── Generating ────────────────────────────────────────────────────────────
    if (isGenerating) {
        return (
            <div className="flex flex-col h-full">
                <IssueHeader issue={issue} />
                <div className="flex flex-col items-center justify-center flex-1 gap-4">
                    <div className="w-10 h-10 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                    <div className="text-center">
                        <p className="text-sm font-medium text-gray-700">Generating DITA...</p>
                        <div className="flex flex-col gap-1 mt-3 text-xs text-gray-400">
                            <GenerationStep label="Fetching Jira data" done />
                            <GenerationStep label="Querying RAG context" done />
                            <GenerationStep label="Finding expert examples" loading />
                            <GenerationStep label="Generating XML" />
                            <GenerationStep label="Validating structure" />
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    // ── Generated ─────────────────────────────────────────────────────────────
    return (
        <div className="flex flex-col h-full">
            <IssueHeader issue={issue} dita={generatedDita} />

            {/* Toolbar */}
            <div className="flex items-center justify-between px-5 py-2 border-b border-gray-100">
                {/* Tabs */}
                <div className="flex gap-0">
                    {(['preview', 'xml', 'rendered'] as Tab[]).map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 text-xs font-medium capitalize border-b-2 transition-colors ${
                                activeTab === tab
                                    ? 'border-blue-500 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                            }`}
                        >
                            {tab === 'xml' ? 'XML Source' : tab === 'rendered' ? 'Rendered' : 'Preview'}
                        </button>
                    ))}
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                    <button
                        onClick={handleCopy}
                        className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600"
                    >
                        <Copy className="w-3 h-3" />
                        {copied ? 'Copied!' : 'Copy'}
                    </button>
                    <button
                        onClick={handleDownload}
                        className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600"
                    >
                        <Download className="w-3 h-3" />
                        Download
                    </button>
                    <button
                        onClick={handleUploadToAem}
                        disabled={uploadStatus === 'uploading'}
                        className={`text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md font-medium transition-colors ${
                            uploadStatus === 'done'
                                ? 'bg-green-600 text-white border-green-600'
                                : uploadStatus === 'error'
                                    ? 'bg-red-600 text-white border-red-600'
                                    : 'bg-blue-600 text-white hover:bg-blue-700 border-blue-600'
                        }`}
                    >
                        <Upload className="w-3 h-3" />
                        {uploadStatus === 'uploading' ? 'Uploading...'
                            : uploadStatus === 'done' ? 'Uploaded!'
                                : uploadStatus === 'error' ? 'Failed'
                                    : 'Upload to AEM'}
                    </button>
                </div>
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
                {activeTab === 'preview' && <DitaPreview dita={generatedDita!} />}
                {activeTab === 'xml' && <XmlSource content={generatedDita!.content} />}
                {activeTab === 'rendered' && <RenderedPreview content={generatedDita!.content} />}
            </div>

            {/* AI Refine bar */}
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
                <div className="flex gap-2">
                    <Input
                        className="text-xs h-8 flex-1 bg-white"
                        placeholder="Refine with AI... e.g. 'add a note about AEM 4.1 compatibility'"
                        value={refineText}
                        onChange={e => setRefineText(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleRefine()}
                    />
                    <Button
                        size="sm"
                        disabled={!refineText.trim() || refining}
                        onClick={handleRefine}
                        className="bg-blue-600 hover:bg-blue-700 text-white h-8 text-xs"
                    >
                        {refining ? <RefreshCw className="w-3 h-3 animate-spin" /> : 'Refine'}
                    </Button>
                </div>
            </div>
        </div>
    )
}

// ── Sub-components ───────────────────────────────────────────────────────────

function IssueHeader({ issue, dita }: { issue: JiraIssue; dita?: GeneratedDita | null }) {
    return (
        <div className="px-5 py-4 border-b border-gray-100">
            <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
          {issue.issue_key}
        </span>
                <ChevronRight className="w-3 h-3 text-gray-400" />
                <span className="text-xs text-gray-500">{issue.issue_type?.toLowerCase()} topic</span>
                {dita && (
                    <>
                        <ChevronRight className="w-3 h-3 text-gray-400" />
                        <span className="text-xs text-gray-500">{dita.filename}</span>
                        <span
                            className={`ml-auto text-xs px-2 py-0.5 rounded font-medium ${
                                dita.quality_score >= 80
                                    ? 'bg-green-50 text-green-700'
                                    : dita.quality_score >= 60
                                        ? 'bg-yellow-50 text-yellow-700'
                                        : 'bg-red-50 text-red-700'
                            }`}
                        >
              {dita.quality_score}/100 quality
            </span>
                    </>
                )}
            </div>
            <p className="text-base font-medium text-gray-900">{issue.summary}</p>
        </div>
    )
}

function GenerationStep({ label, done, loading }: { label: string; done?: boolean; loading?: boolean }) {
    return (
        <div className="flex items-center gap-2">
            {done ? (
                <CheckCircle2 className="w-3 h-3 text-green-500" />
            ) : loading ? (
                <div className="w-3 h-3 border border-blue-500 border-t-transparent rounded-full animate-spin" />
            ) : (
                <div className="w-3 h-3 rounded-full border border-gray-300" />
            )}
            <span className={done ? 'text-gray-600' : loading ? 'text-blue-600' : 'text-gray-400'}>
        {label}
      </span>
        </div>
    )
}

// Structured DITA preview — shows elements with labels
function DitaPreview({ dita }: { dita: GeneratedDita }) {
    const content = dita.content

    const extract = (tag: string) => {
        const m = content.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'))
        return m ? m[1].replace(/<[^>]+>/g, '').trim() : null
    }

    const extractAll = (tag: string) => {
        const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
        const results: string[] = []
        let m
        while ((m = re.exec(content)) !== null) {
            results.push(m[1].replace(/<[^>]+>/g, '').trim())
        }
        return results
    }

    const title = extract('title')
    const shortdesc = extract('shortdesc')
    const prereq = extract('prereq')
    const context = extract('context')
    const cmds = extractAll('cmd')
    const result = extract('result')
    const sections = extractAll('section')

    return (
        <div className="text-sm leading-relaxed space-y-4">
            {title && (
                <h2 className="text-lg font-medium text-gray-900">{title}</h2>
            )}

            {shortdesc && (
                <div className="flex gap-2">
                    <ElementBadge label="shortdesc" color="blue" />
                    <p className="text-gray-600 text-xs">{shortdesc}</p>
                </div>
            )}

            {prereq && (
                <div className="border-l-2 border-gray-200 pl-3">
                    <ElementBadge label="prereq" color="gray" />
                    <p className="text-xs text-gray-600 mt-1">{prereq}</p>
                </div>
            )}

            {context && (
                <div className="border-l-2 border-gray-200 pl-3">
                    <ElementBadge label="context" color="gray" />
                    <p className="text-xs text-gray-600 mt-1">{context}</p>
                </div>
            )}

            {cmds.length > 0 && (
                <div className="border-l-2 border-gray-200 pl-3">
                    <ElementBadge label="steps" color="green" />
                    <div className="mt-2 space-y-2">
                        {cmds.map((cmd, i) => (
                            <div key={i} className="flex gap-2 items-start">
                                <span className="text-xs text-gray-400 w-4 mt-0.5">{i + 1}.</span>
                                <div>
                                    <ElementBadge label="cmd" color="amber" />
                                    <span className="text-xs text-gray-700 ml-2">{cmd}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {sections.map((sec, i) => (
                <div key={i} className="border-l-2 border-gray-200 pl-3">
                    <ElementBadge label="section" color="purple" />
                    <p className="text-xs text-gray-600 mt-1">{sec.slice(0, 300)}</p>
                </div>
            ))}

            {result && (
                <div className="border-l-2 border-green-200 pl-3">
                    <ElementBadge label="result" color="green" />
                    <p className="text-xs text-gray-600 mt-1">{result}</p>
                </div>
            )}
        </div>
    )
}

function ElementBadge({ label, color }: { label: string; color: string }) {
    const colors: Record<string, string> = {
        blue:   'bg-blue-50 text-blue-700',
        green:  'bg-green-50 text-green-700',
        amber:  'bg-amber-50 text-amber-700',
        gray:   'bg-gray-100 text-gray-600',
        purple: 'bg-purple-50 text-purple-700',
    }
    return (
        <span className={`inline-block text-xs font-mono font-medium px-1.5 py-0.5 rounded text-xs ${colors[color] || colors.gray}`}>
      {label}
    </span>
    )
}

function XmlSource({ content }: { content: string }) {
    return (
        <pre className="text-xs font-mono text-gray-700 bg-gray-50 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap leading-relaxed">
      {content}
    </pre>
    )
}

function RenderedPreview({ content }: { content: string }) {
    const extract = (tag: string) => {
        const m = content.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'))
        return m ? m[1].replace(/<[^>]+>/g, '').trim() : null
    }
    const extractAll = (tag: string) => {
        const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
        const results: string[] = []
        let m
        while ((m = re.exec(content)) !== null) results.push(m[1].replace(/<[^>]+>/g, '').trim())
        return results
    }

    return (
        <div className="prose prose-sm max-w-none">
            <h1 className="text-xl font-semibold">{extract('title')}</h1>
            {extract('shortdesc') && (
                <p className="text-gray-600 italic">{extract('shortdesc')}</p>
            )}
            {extract('context') && (
                <section>
                    <h3>Context</h3>
                    <p>{extract('context')}</p>
                </section>
            )}
            {extractAll('cmd').length > 0 && (
                <section>
                    <h3>Steps</h3>
                    <ol>
                        {extractAll('cmd').map((cmd, i) => <li key={i}>{cmd}</li>)}
                    </ol>
                </section>
            )}
            {extract('result') && (
                <section>
                    <h3>Result</h3>
                    <p>{extract('result')}</p>
                </section>
            )}
        </div>
    )
}
