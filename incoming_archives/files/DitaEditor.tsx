import { useState, useEffect } from 'react'
import {
    Wand2, Download, Upload, Copy, RefreshCw,
    ChevronRight, FileText, CheckCircle2,
    ClipboardCheck, AlertTriangle, RotateCcw
} from 'lucide-react'
import { Button } from '../ui/button.tsx'
import { Input } from '../ui/input.tsx'
import { ReviewMode } from './ReviewMode'
import type { JiraIssue, GeneratedDita } from '../../pages/AuthoringPage.tsx'

const API_BASE = '/api/v1'

type Tab = 'preview' | 'xml' | 'rendered'

// Steps shown during generation with realistic timing
const GEN_STEPS = [
    { label: 'Fetching Jira issue + comments',  ms: 800  },
    { label: 'Querying RAG context',             ms: 1400 },
    { label: 'Finding expert DITA examples',     ms: 1000 },
    { label: 'Generating spec-compliant XML',    ms: 2000 },
    { label: 'Validating + scoring',             ms: 600  },
]

interface Props {
    issue: JiraIssue | null
    generatedDita: GeneratedDita | null
    isGenerating: boolean
    researchContext?: any | null    // ResearchContext from query plan execution
    onGenerating: () => void
    onGenerated: (dita: GeneratedDita) => void
}

export function DitaEditor({
    issue,
    generatedDita,
    isGenerating,
    researchContext,
    onGenerating,
    onGenerated,
}: Props) {
    const [activeTab, setActiveTab]       = useState<Tab>('preview')
    const [refineText, setRefineText]     = useState('')
    const [refining, setRefining]         = useState(false)
    const [copied, setCopied]             = useState(false)
    const [uploadStatus, setUploadStatus] = useState<'idle'|'uploading'|'done'|'error'>('idle')
    const [reviewMode, setReviewMode]     = useState(false)
    const [genStep, setGenStep]           = useState(-1)
    const [genError, setGenError]         = useState('')

    // Animate generation steps while API call runs
    useEffect(() => {
        if (!isGenerating) { setGenStep(-1); return }
        setGenStep(0)
        let current = 0
        const timers: ReturnType<typeof setTimeout>[] = []
        let elapsed = 0
        GEN_STEPS.forEach((step, i) => {
            elapsed += step.ms
            const t = setTimeout(() => {
                current = i + 1
                setGenStep(current)
            }, elapsed)
            timers.push(t)
        })
        return () => timers.forEach(clearTimeout)
    }, [isGenerating])

    // ── Generate ──────────────────────────────────────────────────────────────
    const handleGenerate = async () => {
        if (!issue) return
        setGenError('')
        setReviewMode(false)
        onGenerating()

        try {
            const res = await fetch(`${API_BASE}/ai/generate-dita-from-jira`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    issue_key: issue.issue_key,
                    dita_type: 'auto',
                    // Pass research context so backend uses it in generation
                    research_context: researchContext
                        ? researchContext.results?.map((r: any) => ({
                            category: r.category,
                            query:    r.query,
                            summary:  r.summary,
                            chunks:   r.chunks?.slice(0, 2),
                          }))
                        : null,
                    issue: {
                        issue_key:   issue.issue_key,
                        summary:     issue.summary,
                        description: issue.description,
                        issue_type:  issue.issue_type,
                        labels:      issue.labels,
                        priority:    issue.priority,
                        status:      issue.status,
                        comments:    issue.comments || [],
                    },
                }),
            })

            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || err.error || `Server error ${res.status}`)
            }

            const data = await res.json()
            onGenerated(_normalize(data, issue.issue_key))

        } catch (e: any) {
            const msg = e?.message || 'Generation failed'
            setGenError(msg)
            onGenerated({
                filename:          `${issue.issue_key}-task.dita`,
                content:           `<!-- Generation failed: ${msg} -->`,
                dita_type:         'task',
                quality_score:     0,
                quality_breakdown: { structure: 0, content_richness: 0, dita_features: 0, aem_readiness: 0 },
                validation:        [{ label: msg, passing: false }],
                sources_used:      [],
            })
        }
    }

    // ── Refine ────────────────────────────────────────────────────────────────
    const handleRefine = async () => {
        if (!generatedDita || !refineText.trim()) return
        setRefining(true)
        try {
            const res = await fetch(`${API_BASE}/ai/refine-dita`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename:        generatedDita.filename,
                    current_content: generatedDita.content,
                    instruction:     refineText,
                }),
            })
            if (!res.ok) throw new Error(`Refine failed: ${res.status}`)
            const data = await res.json()
            onGenerated(_normalize(data, issue?.issue_key || 'unknown'))
            setRefineText('')
        } catch (e: any) {
            setGenError(e?.message || 'Refine failed')
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
        const url  = URL.createObjectURL(blob)
        const a    = document.createElement('a')
        a.href     = url
        a.download = generatedDita.filename
        a.click()
        URL.revokeObjectURL(url)
    }

    const handleUploadToAem = async () => {
        if (!generatedDita) return
        setUploadStatus('uploading')
        try {
            const res = await fetch(`${API_BASE}/aem/upload-dita`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: generatedDita.filename,
                    content:  generatedDita.content,
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

    // ── State: no issue selected ──────────────────────────────────────────────
    if (!issue) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center px-8">
                <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                    <FileText className="w-6 h-6 text-blue-400" />
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">No issue selected</p>
                <p className="text-xs text-gray-400">
                    Pick a Jira issue from the left panel to get started
                </p>
            </div>
        )
    }

    // ── State: issue selected, not yet generated ──────────────────────────────
    if (!generatedDita && !isGenerating) {
        return (
            <div className="flex flex-col h-full">
                <IssueHeader issue={issue} />

                {/* Error from previous attempt */}
                {genError && (
                    <div className="mx-5 mt-4 flex items-start gap-2.5 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                        <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                        <div>
                            <p className="text-xs font-medium text-red-700">Generation failed</p>
                            <p className="text-xs text-red-600 mt-0.5">{genError}</p>
                            <p className="text-xs text-red-400 mt-1">
                                Check backend is running at localhost:8000 and .env has Jira credentials
                            </p>
                        </div>
                    </div>
                )}

                <div className="flex flex-col items-center justify-center flex-1 px-8 text-center">
                    <div className="max-w-xs">
                        <div className="w-14 h-14 bg-blue-50 rounded-xl flex items-center justify-center mb-4 mx-auto">
                            <Wand2 className="w-7 h-7 text-blue-500" />
                        </div>
                        <p className="text-sm font-medium text-gray-800 mb-2">Ready to generate</p>
                        <p className="text-xs text-gray-500 mb-5 leading-relaxed">
                            Generate spec-compliant DITA for{' '}
                            <span className="font-semibold text-blue-600">{issue.issue_key}</span>{' '}
                            using your RAG knowledge base
                        </p>

                        {/* Preview of what will happen */}
                        <div className="text-left bg-gray-50 rounded-lg p-3 mb-6 space-y-2">
                            {GEN_STEPS.map((step, i) => (
                                <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                                    <div className="w-1.5 h-1.5 rounded-full bg-gray-300 flex-shrink-0" />
                                    {step.label}
                                </div>
                            ))}
                        </div>

                        <Button
                            onClick={handleGenerate}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-8"
                        >
                            <Wand2 className="w-4 h-4 mr-2" />
                            {genError ? 'Retry generation' : 'Generate DITA'}
                        </Button>
                        <p className="text-xs text-gray-400 mt-3">
                            DITA 1.3 · Experience League · Expert examples
                        </p>
                    </div>
                </div>
            </div>
        )
    }

    // ── State: generating ─────────────────────────────────────────────────────
    if (isGenerating) {
        return (
            <div className="flex flex-col h-full">
                <IssueHeader issue={issue} />
                <div className="flex flex-col items-center justify-center flex-1 gap-6">
                    <div className="w-10 h-10 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                    <div className="text-center">
                        <p className="text-sm font-medium text-gray-700 mb-4">
                            Generating DITA for {issue.issue_key}...
                        </p>
                        <div className="flex flex-col gap-2.5 text-xs min-w-[240px]">
                            {GEN_STEPS.map((step, i) => (
                                <GenStep
                                    key={i}
                                    label={step.label}
                                    done={i < genStep}
                                    loading={i === genStep}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    // ── State: review mode ────────────────────────────────────────────────────
    if (reviewMode && generatedDita) {
        return (
            <ReviewMode
                dita={generatedDita}
                onComplete={() => setReviewMode(false)}
                onCancel={() => setReviewMode(false)}
            />
        )
    }

    // ── State: generated — main editor view ───────────────────────────────────
    const hasError = generatedDita?.quality_score === 0

    return (
        <div className="flex flex-col h-full">
            <IssueHeader issue={issue} dita={generatedDita} />

            {/* Error banner if generation produced an error file */}
            {hasError && genError && (
                <div className="mx-5 mt-3 flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600 flex-1">{genError}</p>
                    <button
                        onClick={handleGenerate}
                        className="text-xs text-red-700 font-medium flex items-center gap-1 hover:text-red-900"
                    >
                        <RotateCcw className="w-3 h-3" />
                        Retry
                    </button>
                </div>
            )}

            {/* Toolbar */}
            <div className="flex items-center justify-between px-5 py-2 border-b border-gray-100 flex-wrap gap-2">
                {/* View tabs */}
                <div className="flex">
                    {(['preview', 'xml', 'rendered'] as Tab[]).map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
                                activeTab === tab
                                    ? 'border-blue-500 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                            }`}
                        >
                            {tab === 'xml' ? 'XML' : tab === 'rendered' ? 'Rendered' : 'Preview'}
                        </button>
                    ))}
                </div>

                {/* Actions */}
                <div className="flex gap-1.5 flex-wrap">
                    <button
                        onClick={() => setReviewMode(true)}
                        className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-amber-300 bg-amber-50 hover:bg-amber-100 text-amber-700 font-medium transition-colors"
                    >
                        <ClipboardCheck className="w-3 h-3" />
                        Review
                    </button>
                    <button
                        onClick={handleGenerate}
                        className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 transition-colors"
                    >
                        <RotateCcw className="w-3 h-3" />
                        Regenerate
                    </button>
                    <button
                        onClick={handleCopy}
                        className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 transition-colors"
                    >
                        <Copy className="w-3 h-3" />
                        {copied ? 'Copied!' : 'Copy'}
                    </button>
                    <button
                        onClick={handleDownload}
                        className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-600 transition-colors"
                    >
                        <Download className="w-3 h-3" />
                        Download
                    </button>
                    <button
                        onClick={handleUploadToAem}
                        disabled={uploadStatus === 'uploading' || hasError}
                        className={`text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md font-medium transition-colors ${
                            uploadStatus === 'done'    ? 'bg-green-600 text-white border border-green-600'
                            : uploadStatus === 'error' ? 'bg-red-500 text-white border border-red-500'
                            : hasError                 ? 'bg-gray-200 text-gray-400 border border-gray-200 cursor-not-allowed'
                            : 'bg-blue-600 text-white hover:bg-blue-700 border border-blue-600'
                        }`}
                    >
                        <Upload className="w-3 h-3" />
                        {uploadStatus === 'uploading' ? 'Uploading...'
                            : uploadStatus === 'done'    ? 'Uploaded!'
                            : uploadStatus === 'error'   ? 'Failed'
                            : 'Upload to AEM'}
                    </button>
                </div>
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
                {activeTab === 'preview'  && <DitaPreview dita={generatedDita!} />}
                {activeTab === 'xml'      && <XmlSource content={generatedDita!.content} />}
                {activeTab === 'rendered' && <RenderedView content={generatedDita!.content} />}
            </div>

            {/* AI Refine bar */}
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50/80">
                <div className="flex gap-2">
                    <Input
                        className="text-xs h-8 flex-1 bg-white"
                        placeholder='Refine: "add note about AEM 4.1" or "remove prereq section"'
                        value={refineText}
                        onChange={e => setRefineText(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleRefine()}
                        disabled={hasError}
                    />
                    <Button
                        size="sm"
                        disabled={!refineText.trim() || refining || hasError}
                        onClick={handleRefine}
                        className="bg-blue-600 hover:bg-blue-700 text-white h-8 text-xs px-4"
                    >
                        {refining
                            ? <RefreshCw className="w-3 h-3 animate-spin" />
                            : 'Refine'
                        }
                    </Button>
                </div>
            </div>
        </div>
    )
}

// ── Response normalizer ───────────────────────────────────────────────────────
function _normalize(data: any, issueKey: string): GeneratedDita {
    // Shape 1: already correct {filename, content, ...}
    if (data?.content && data?.filename) {
        return {
            filename:          data.filename,
            content:           data.content,
            dita_type:         data.dita_type         || 'task',
            quality_score:     data.quality_score      ?? 0,
            quality_breakdown: data.quality_breakdown  || { structure: 0, content_richness: 0, dita_features: 0, aem_readiness: 0 },
            validation:        data.validation         || [],
            sources_used:      data.sources_used       || [],
        }
    }
    // Shape 2: {xml, dita_type, ...}
    if (data?.xml || data?.dita_content || data?.dita_xml) {
        const content  = data.xml || data.dita_content || data.dita_xml
        const dtype    = data.dita_type || 'task'
        return {
            filename:          `${issueKey.toLowerCase()}-${dtype}.dita`,
            content,
            dita_type:         dtype,
            quality_score:     data.quality_score ?? 70,
            quality_breakdown: data.quality_breakdown || { structure: 20, content_richness: 20, dita_features: 15, aem_readiness: 15 },
            validation:        data.validation    || [{ label: 'Generated', passing: true }],
            sources_used:      data.sources_used  || [],
        }
    }
    // Shape 3: raw string
    if (typeof data === 'string' && data.includes('<?xml')) {
        const dtype = data.includes('<task') ? 'task' : data.includes('<concept') ? 'concept' : 'topic'
        return {
            filename:          `${issueKey.toLowerCase()}-${dtype}.dita`,
            content:           data,
            dita_type:         dtype,
            quality_score:     60,
            quality_breakdown: { structure: 20, content_richness: 15, dita_features: 10, aem_readiness: 15 },
            validation:        [{ label: 'Generated (unscored)', passing: true }],
            sources_used:      [],
        }
    }
    // Fallback
    return {
        filename:          `${issueKey.toLowerCase()}-task.dita`,
        content:           `<!-- Unexpected response: ${JSON.stringify(data).slice(0, 200)} -->`,
        dita_type:         'task',
        quality_score:     0,
        quality_breakdown: { structure: 0, content_richness: 0, dita_features: 0, aem_readiness: 0 },
        validation:        [{ label: 'Unexpected response format from backend', passing: false }],
        sources_used:      [],
    }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function IssueHeader({ issue, dita }: { issue: JiraIssue; dita?: GeneratedDita | null }) {
    return (
        <div className="px-5 py-4 border-b border-gray-100">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                    {issue.issue_key}
                </span>
                <ChevronRight className="w-3 h-3 text-gray-400" />
                <span className="text-xs text-gray-500 capitalize">
                    {issue.issue_type?.toLowerCase() || 'issue'}
                </span>
                {dita && (
                    <>
                        <ChevronRight className="w-3 h-3 text-gray-400" />
                        <span className="text-xs text-gray-500 font-mono">{dita.filename}</span>
                        <span className={`ml-auto text-xs px-2 py-0.5 rounded font-medium ${
                            dita.quality_score >= 80 ? 'bg-green-50 text-green-700'
                            : dita.quality_score >= 60 ? 'bg-yellow-50 text-yellow-700'
                            : dita.quality_score > 0  ? 'bg-red-50 text-red-700'
                            : 'bg-gray-100 text-gray-500'
                        }`}>
                            {dita.quality_score > 0 ? `${dita.quality_score}/100` : 'Error'}
                        </span>
                    </>
                )}
            </div>
            <p className="text-base font-medium text-gray-900 leading-snug">{issue.summary}</p>
        </div>
    )
}

function GenStep({ label, done, loading }: { label: string; done?: boolean; loading?: boolean }) {
    return (
        <div className="flex items-center gap-2">
            {done
                ? <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                : loading
                ? <div className="w-3.5 h-3.5 border border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                : <div className="w-3.5 h-3.5 rounded-full border border-gray-300 flex-shrink-0" />
            }
            <span className={
                done    ? 'text-gray-700'
                : loading ? 'text-blue-600 font-medium'
                : 'text-gray-400'
            }>
                {label}
            </span>
        </div>
    )
}

function DitaPreview({ dita }: { dita: GeneratedDita }) {
    const c = dita.content

    const extract = (tag: string) => {
        const m = c.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'))
        return m ? m[1].replace(/<[^>]+>/g, '').trim() : null
    }
    const extractAll = (tag: string) => {
        const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
        const out: string[] = []
        let m
        while ((m = re.exec(c)) !== null) {
            const t = m[1].replace(/<[^>]+>/g, '').trim()
            if (t) out.push(t)
        }
        return out
    }

    const title     = extract('title')
    const shortdesc = extract('shortdesc')
    const prereq    = extract('prereq')
    const context   = extract('context')
    const cmds      = extractAll('cmd')
    const result    = extract('result')
    const sections  = extractAll('section')
    const notes     = extractAll('note')

    // Error state — show raw content
    if (!title && !shortdesc && (c.startsWith('<!--') || c.startsWith('{'))) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-xs font-medium text-red-700 mb-2 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Generation error — no valid DITA parsed
                </p>
                <pre className="text-xs text-red-600 whitespace-pre-wrap font-mono">{c}</pre>
            </div>
        )
    }

    return (
        <div className="text-sm leading-relaxed space-y-4 pb-4">
            {title && (
                <h2 className="text-lg font-medium text-gray-900 pb-2 border-b border-gray-100">
                    {title}
                </h2>
            )}
            {shortdesc && (
                <div className="flex gap-2 items-start">
                    <Badge label="shortdesc" color="blue" />
                    <p className="text-gray-600 text-xs flex-1 italic">{shortdesc}</p>
                </div>
            )}
            {prereq && (
                <div className="border-l-2 border-gray-200 pl-3">
                    <Badge label="prereq" color="gray" />
                    <p className="text-xs text-gray-600 mt-1">{prereq}</p>
                </div>
            )}
            {context && (
                <div className="border-l-2 border-gray-200 pl-3">
                    <Badge label="context" color="gray" />
                    <p className="text-xs text-gray-600 mt-1">{context}</p>
                </div>
            )}
            {cmds.length > 0 && (
                <div className="border-l-2 border-blue-100 pl-3">
                    <Badge label="steps" color="green" />
                    <div className="mt-2 space-y-2">
                        {cmds.map((cmd, i) => (
                            <div key={i} className="flex gap-2 items-start">
                                <span className="text-xs text-gray-400 w-5 mt-0.5 flex-shrink-0 font-mono">{i + 1}.</span>
                                <div className="flex items-start gap-1.5 flex-wrap">
                                    <Badge label="cmd" color="amber" />
                                    <span className="text-xs text-gray-700">{cmd}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            {notes.map((note, i) => (
                <div key={i} className="bg-amber-50 border-l-2 border-amber-300 pl-3 py-1 rounded-r">
                    <Badge label="note" color="amber" />
                    <p className="text-xs text-amber-800 mt-1">{note}</p>
                </div>
            ))}
            {sections.map((sec, i) => (
                <div key={i} className="border-l-2 border-gray-200 pl-3">
                    <Badge label="section" color="purple" />
                    <p className="text-xs text-gray-600 mt-1">{sec.slice(0, 400)}</p>
                </div>
            ))}
            {result && (
                <div className="border-l-2 border-green-300 pl-3 bg-green-50/50 rounded-r py-1">
                    <Badge label="result" color="green" />
                    <p className="text-xs text-gray-700 mt-1">{result}</p>
                </div>
            )}
        </div>
    )
}

function Badge({ label, color }: { label: string; color: string }) {
    const map: Record<string, string> = {
        blue:   'bg-blue-50 text-blue-700',
        green:  'bg-green-50 text-green-700',
        amber:  'bg-amber-50 text-amber-700',
        gray:   'bg-gray-100 text-gray-600',
        purple: 'bg-purple-50 text-purple-700',
    }
    return (
        <span className={`inline-block text-xs font-mono font-medium px-1.5 py-0.5 rounded flex-shrink-0 ${map[color] || map.gray}`}>
            {label}
        </span>
    )
}

function XmlSource({ content }: { content: string }) {
    return (
        <pre className="text-xs font-mono text-gray-700 bg-gray-50 border border-gray-200 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap leading-relaxed">
            {content}
        </pre>
    )
}

function RenderedView({ content }: { content: string }) {
    const extract = (tag: string) => {
        const m = content.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'))
        return m ? m[1].replace(/<[^>]+>/g, '').trim() : null
    }
    const extractAll = (tag: string) => {
        const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
        const out: string[] = []
        let m
        while ((m = re.exec(content)) !== null) out.push(m[1].replace(/<[^>]+>/g, '').trim())
        return out
    }

    return (
        <div className="prose prose-sm max-w-none pb-4">
            <h1 className="text-xl font-semibold text-gray-900">{extract('title') || 'Untitled'}</h1>
            {extract('shortdesc') && (
                <p className="text-gray-600 italic border-l-4 border-blue-200 pl-3 not-prose py-1 my-3 text-sm">
                    {extract('shortdesc')}
                </p>
            )}
            {extract('prereq') && (
                <div><h3 className="text-sm font-medium">Prerequisites</h3><p className="text-sm">{extract('prereq')}</p></div>
            )}
            {extract('context') && (
                <div><h3 className="text-sm font-medium">Context</h3><p className="text-sm">{extract('context')}</p></div>
            )}
            {extractAll('cmd').length > 0 && (
                <div>
                    <h3 className="text-sm font-medium">Steps</h3>
                    <ol className="list-decimal list-inside space-y-1 text-sm">
                        {extractAll('cmd').map((cmd, i) => <li key={i}>{cmd}</li>)}
                    </ol>
                </div>
            )}
            {extract('result') && (
                <div>
                    <h3 className="text-sm font-medium">Result</h3>
                    <p className="text-sm bg-green-50 text-green-800 p-2 rounded">{extract('result')}</p>
                </div>
            )}
        </div>
    )
}
