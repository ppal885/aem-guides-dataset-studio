import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Copy,
  Download,
  FileText,
  Paperclip,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  Save,
  Upload,
  Wand2,
} from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import type { GeneratedDita, JiraIssue } from '../../pages/AuthoringPage'
import type { ResearchContext } from './QueryPlanPanel'
import { apiUrl, withTenantHeaders } from '@/utils/api'

const API_BASE = '/api/v1'
const XML_INDENT = '  '

const QUICK_REFINE_PROMPTS = [
  'Rewrite this into cleaner user-facing documentation',
  'Strengthen the title, shortdesc, and overall content flow',
  'Use the research context to improve accuracy and specificity',
]

type Tab = 'preview' | 'xml' | 'rendered'

interface Props {
  issue: JiraIssue | null
  generatedDita: GeneratedDita | null
  isGenerating: boolean
  researchContext?: ResearchContext | null
  onGenerating: () => void
  onGenerated: (dita: GeneratedDita) => void
}

function formatXmlDocument(content: string) {
  const trimmed = content.trim()
  if (!trimmed) {
    return content
  }

  const declarationMatch = trimmed.match(/^<\?xml[\s\S]*?\?>/i)
  const declaration = declarationMatch?.[0] || ''
  const withoutDeclaration = declaration ? trimmed.slice(declaration.length).trimStart() : trimmed
  const doctypeMatch = withoutDeclaration.match(/^<!DOCTYPE[\s\S]*?>/i)
  const doctype = doctypeMatch?.[0] || ''
  let body = doctype ? withoutDeclaration.slice(doctype.length).trimStart() : withoutDeclaration

  body = body
    .replace(/>\s+</g, '>\n<')
    .replace(/\r\n/g, '\n')
    .trim()

  if (!body) {
    return [declaration, doctype].filter(Boolean).join('\n')
  }

  const lines = body.split('\n').map(line => line.trim()).filter(Boolean)
  const formatted: string[] = []
  let level = 0

  for (const line of lines) {
    const isClosingTag = /^<\//.test(line)
    const isComment = /^<!--/.test(line)
    const isDirective = /^<\?/.test(line) || /^<!/.test(line)
    const hasInlineClosingTag = /<[^/!][^>]*>.*<\/[^>]+>$/.test(line)
    const isSelfClosingTag = /^<[^!?/][^>]*\/>$/.test(line)
    const isOpeningTag = /^<[^!?/][^>]*>$/.test(line)

    if (isClosingTag) {
      level = Math.max(level - 1, 0)
    }

    formatted.push(`${XML_INDENT.repeat(level)}${line}`)

    if (!isClosingTag && !isComment && !isDirective && isOpeningTag && !isSelfClosingTag && !hasInlineClosingTag) {
      level += 1
    }
  }

  return [declaration, doctype, ...formatted].filter(Boolean).join('\n')
}

function getRootTag(content: string) {
  const match = content.match(/<([A-Za-z_][\w:.-]*)\b/)
  return match ? match[1] : null
}

function getContentWordCount(content: string) {
  return content
    .replace(/<[^>]+>/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean).length
}

function getApiErrorMessage(data: unknown, fallback: string) {
  if (!data || typeof data !== 'object') {
    return fallback
  }
  const payload = data as { error?: unknown; detail?: unknown }
  if (typeof payload.error === 'string' && payload.error.trim()) {
    return payload.error
  }
  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return payload.detail
  }
  return fallback
}

export function DitaEditor({
  issue,
  generatedDita,
  isGenerating,
  researchContext,
  onGenerating,
  onGenerated,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('preview')
  const [refineText, setRefineText] = useState('')
  const [refining, setRefining] = useState(false)
  const [copied, setCopied] = useState(false)
  const [savingXml, setSavingXml] = useState(false)
  const [error, setError] = useState('')
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [editableContent, setEditableContent] = useState('')
  const [editorNotice, setEditorNotice] = useState('')
  const [wrapXml, setWrapXml] = useState(false)

  useEffect(() => {
    setEditableContent(generatedDita?.content || '')
    setEditorNotice('')
  }, [generatedDita?.content, generatedDita?.filename])

  useEffect(() => {
    if (!editorNotice) {
      return
    }
    const timeout = window.setTimeout(() => setEditorNotice(''), 2400)
    return () => window.clearTimeout(timeout)
  }, [editorNotice])

  const hasUnsavedXml = Boolean(generatedDita && editableContent !== generatedDita.content)
  const ditaForPreview = useMemo(
    () => (generatedDita ? { ...generatedDita, content: editableContent } : null),
    [editableContent, generatedDita],
  )
  const currentValidation = generatedDita?.validation || []
  const passingChecks = currentValidation.filter(check => check.passing).length
  const failingChecks = currentValidation.filter(check => !check.passing)
  const xmlMetrics = useMemo(() => {
    const content = editableContent || generatedDita?.content || ''
    return {
      characters: content.length,
      lines: content ? content.split(/\r?\n/).length : 0,
      words: getContentWordCount(content),
      rootTag: getRootTag(content),
    }
  }, [editableContent, generatedDita?.content])

  const handleGenerate = async () => {
    if (!issue) {
      return
    }
    onGenerating()
    setError('')

    try {
      const response = await fetch(`${API_BASE}/ai/generate-dita-from-jira`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          issue_key: issue.issue_key,
          issue,
          dita_type: 'auto',
          research_context: researchContext,
        }),
      })
      const data = await response.json()
      if (!response.ok || data.error) {
        throw new Error(getApiErrorMessage(data, 'Generation failed'))
      }
      if (issue) {
        await fetch(`${API_BASE}/safety/save-version`, {
          method: 'POST',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            issue_key: issue.issue_key,
            filename: data.filename,
            content: data.content,
            author: 'ai',
            action: 'generated',
            comment: 'Initial AI generation',
          }),
        })
      }
      onGenerated(data)
      setActiveTab('preview')
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Generation failed'
      setError(message)
      onGenerated({
        filename: `${issue.issue_key.toLowerCase()}-task.dita`,
        content: '<!-- Generation failed. Check backend configuration and try again. -->',
        dita_type: 'task',
        quality_score: 0,
        quality_breakdown: {
          structure: 0,
          content_richness: 0,
          dita_features: 0,
          aem_readiness: 0,
        },
        validation: [],
        sources_used: [],
      })
    }
  }

  const handleRefine = async () => {
    if (!generatedDita || !refineText.trim()) {
      return
    }
    setRefining(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/ai/refine-dita`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          filename: generatedDita.filename,
          current_content: editableContent || generatedDita.content,
          instruction: refineText.trim(),
          issue,
          research_context: researchContext,
        }),
      })
      const data = await response.json()
      if (!response.ok || data.error) {
        throw new Error(getApiErrorMessage(data, 'Refine failed'))
      }
      if (issue) {
        await fetch(`${API_BASE}/safety/save-version`, {
          method: 'POST',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            issue_key: issue.issue_key,
            filename: data.filename,
            content: data.content,
            author: 'author',
            action: 'edited',
            comment: `AI refinement: ${refineText.trim()}`,
          }),
        })
      }
      onGenerated(data)
      setRefineText('')
      setActiveTab('preview')
      setEditorNotice('Refinement applied')
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Refine failed'
      setError(message)
    } finally {
      setRefining(false)
    }
  }

  const handleSaveXml = async () => {
    if (!generatedDita || !hasUnsavedXml) {
      return
    }
    setSavingXml(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/ai/evaluate-dita`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          filename: generatedDita.filename,
          content: editableContent,
        }),
      })
      const data = await response.json()
      if (!response.ok || data.error) {
        throw new Error(getApiErrorMessage(data, 'Failed to evaluate updated XML'))
      }

      if (issue) {
        await fetch(`${API_BASE}/safety/save-version`, {
          method: 'POST',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            issue_key: issue.issue_key,
            filename: data.filename,
            content: data.content,
            author: 'author',
            action: 'edited',
            comment: 'Manual XML edit in the authoring workspace',
          }),
        })
      }
      onGenerated(data)
      setEditorNotice('XML saved and re-scored')
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Could not save XML changes'
      setError(message)
    } finally {
      setSavingXml(false)
    }
  }

  const handleAutoIndent = () => {
    const content = editableContent || generatedDita?.content || ''
    if (!content.trim()) {
      return
    }
    const formatted = formatXmlDocument(content)
    setEditableContent(formatted)
    setActiveTab('xml')
    setEditorNotice(formatted === content ? 'XML already looks formatted' : 'XML auto-indented')
  }

  const handleResetXml = () => {
    if (!generatedDita) {
      return
    }
    setEditableContent(generatedDita.content)
    setEditorNotice('Reverted to the last saved XML')
  }

  const handleCopy = () => {
    const content = editableContent || generatedDita?.content
    if (!content) {
      return
    }
    void navigator.clipboard.writeText(content)
    setCopied(true)
    setEditorNotice('XML copied to clipboard')
    window.setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    if (!generatedDita) {
      return
    }
    const blob = new Blob([editableContent || generatedDita.content], { type: 'application/xml' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = generatedDita.filename
    anchor.click()
    URL.revokeObjectURL(url)
    setEditorNotice(`Downloaded ${generatedDita.filename}`)
  }

  const handleUploadToAem = async () => {
    if (!generatedDita) {
      return
    }
    setUploadStatus('uploading')
    try {
      const response = await fetch(`${API_BASE}/aem/upload-dita`, {
        method: 'POST',
        headers: withTenantHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          filename: generatedDita.filename,
          content: editableContent || generatedDita.content,
        }),
      })
      const data = await response.json()
      if (!response.ok || data.error) {
        throw new Error(getApiErrorMessage(data, 'Upload failed'))
      }
      setUploadStatus('done')
      window.setTimeout(() => setUploadStatus('idle'), 3000)
    } catch {
      setUploadStatus('error')
      window.setTimeout(() => setUploadStatus('idle'), 3000)
    }
  }

  const applyQuickRefine = (prompt: string) => {
    setRefineText(prompt)
  }

  if (!issue) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50">
          <FileText className="h-6 w-6 text-blue-400" />
        </div>
        <p className="mb-1 text-sm font-medium text-gray-700">Select a Jira issue</p>
        <p className="text-xs text-gray-400">Pick an issue from the left panel to start generating DITA.</p>
      </div>
    )
  }

  if (!generatedDita && !isGenerating) {
    return (
      <div className="flex h-full flex-col">
        <IssueHeader issue={issue} />
        <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
          <div className="max-w-sm">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50">
              <Wand2 className="h-6 w-6 text-blue-500" />
            </div>
            <p className="mb-1 text-sm font-medium text-gray-800">Ready to generate</p>
            <p className="mb-6 text-xs text-gray-500">
              Generate a spec-aware DITA topic for <strong>{issue.issue_key}</strong> using Jira details, your knowledge base, and any approved research context.
            </p>
            <Button onClick={handleGenerate} className="bg-blue-600 px-6 text-white hover:bg-blue-700">
              <Wand2 className="mr-2 h-4 w-4" />
              Generate DITA
            </Button>
            <p className="mt-3 text-xs text-gray-400">
              Sources: Experience League, DITA spec, example topics, and selected research
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (isGenerating) {
    return (
      <div className="flex h-full flex-col">
        <IssueHeader issue={issue} />
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">Generating DITA...</p>
            <div className="mt-3 flex flex-col gap-1 text-xs text-gray-400">
              <GenerationStep label="Fetching Jira data" done />
              <GenerationStep label={researchContext ? `Using ${researchContext.total_chunks} research chunks` : 'Using base retrieval context'} done />
              <GenerationStep label="Generating XML" loading />
              <GenerationStep label="Validating structure" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <IssueHeader issue={issue} dita={generatedDita} />

      <div className="border-b border-gray-100 px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-0">
            {(['preview', 'xml', 'rendered'] as Tab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`border-b-2 px-4 py-2 text-xs font-medium capitalize transition-colors ${
                  activeTab === tab ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab === 'xml' ? 'XML editor' : tab === 'rendered' ? 'Rendered' : 'Preview'}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {editorNotice ? (
              <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{editorNotice}</span>
            ) : null}
            <span
              className={`rounded px-2 py-1 text-xs font-medium ${
                hasUnsavedXml ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'
              }`}
            >
              {hasUnsavedXml ? 'Unsaved XML' : 'Saved'}
            </span>
            {activeTab === 'xml' ? (
              <button
                onClick={handleAutoIndent}
                className="flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
              >
                <Wand2 className="h-3 w-3" />
                Auto-indent
              </button>
            ) : null}
            {activeTab === 'xml' ? (
              <button
                onClick={() => setWrapXml(current => !current)}
                className="rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
              >
                {wrapXml ? 'Wrap off' : 'Wrap on'}
              </button>
            ) : null}
            {activeTab === 'xml' && hasUnsavedXml ? (
              <button
                onClick={handleResetXml}
                className="flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
              >
                <RotateCcw className="h-3 w-3" />
                Revert
              </button>
            ) : null}
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
            >
              <Copy className="h-3 w-3" />
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
            >
              <Download className="h-3 w-3" />
              Download
            </button>
            {hasUnsavedXml ? (
              <button
                onClick={handleSaveXml}
                disabled={savingXml}
                className="flex items-center gap-1.5 rounded-md border border-blue-600 bg-blue-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {savingXml ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                {savingXml ? 'Saving...' : 'Save XML'}
              </button>
            ) : null}
            <button
              onClick={handleUploadToAem}
              disabled={uploadStatus === 'uploading'}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                uploadStatus === 'done'
                  ? 'border border-emerald-600 bg-emerald-600 text-white'
                  : uploadStatus === 'error'
                    ? 'border border-red-600 bg-red-600 text-white'
                    : 'border border-blue-600 bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              <Upload className="h-3 w-3" />
              {uploadStatus === 'uploading'
                ? 'Uploading...'
                : uploadStatus === 'done'
                  ? 'Uploaded'
                  : uploadStatus === 'error'
                    ? 'Failed'
                    : 'Upload to AEM'}
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <InfoPill label="Root" value={xmlMetrics.rootTag || 'unknown'} tone="gray" />
          <InfoPill label="Lines" value={String(xmlMetrics.lines)} tone="gray" />
          <InfoPill label="Words" value={String(xmlMetrics.words)} tone="gray" />
          <InfoPill label="Chars" value={String(xmlMetrics.characters)} tone="gray" />
          <InfoPill
            label="Validation"
            value={`${passingChecks}/${currentValidation.length || 0} passing`}
            tone={failingChecks.length ? 'amber' : 'emerald'}
          />
          {researchContext ? (
            <InfoPill label="Research" value={`${researchContext.total_chunks} chunks`} tone="blue" />
          ) : null}
          <InfoPill label="Sources" value={String(generatedDita?.sources_used.length || 0)} tone="blue" />
        </div>
      </div>

      {error ? (
        <div className="border-b border-red-200 bg-red-50 px-5 py-2 text-xs text-red-600">{error}</div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {activeTab === 'preview' && ditaForPreview ? <DitaPreview dita={ditaForPreview} /> : null}
        {activeTab === 'xml' ? (
          <XmlEditor
            content={editableContent}
            onChange={setEditableContent}
            filename={generatedDita?.filename || ''}
            wrapLines={wrapXml}
            onAutoIndent={handleAutoIndent}
            hasUnsavedChanges={hasUnsavedXml}
            failingChecks={failingChecks.map(check => check.label)}
          />
        ) : null}
        {activeTab === 'rendered' ? <RenderedPreview content={editableContent} /> : null}
      </div>

      <div className="border-t border-gray-100 bg-gray-50 px-5 py-3">
        <div className="mb-2 flex flex-wrap gap-2">
          {QUICK_REFINE_PROMPTS.map(prompt => (
            <button
              key={prompt}
              onClick={() => applyQuickRefine(prompt)}
              className="rounded-full border border-gray-200 bg-white px-3 py-1 text-[11px] text-gray-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
            >
              {prompt}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            className="h-8 flex-1 bg-white text-xs"
            placeholder="Refine with AI, for example: rewrite the title and shortdesc so they sound like production docs"
            value={refineText}
            onChange={event => setRefineText(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter') {
                void handleRefine()
              }
            }}
          />
          <Button
            size="sm"
            disabled={!refineText.trim() || refining}
            onClick={() => void handleRefine()}
            className="h-8 bg-blue-600 text-xs text-white hover:bg-blue-700"
          >
            {refining ? <RefreshCw className="h-3 w-3 animate-spin" /> : 'Refine'}
          </Button>
        </div>
        <p className="mt-2 text-[11px] text-gray-400">
          Tip: in the XML editor, press <span className="font-mono">Tab</span> to indent and <span className="font-mono">Ctrl/Cmd + Shift + F</span> to auto-format.
        </p>
      </div>
    </div>
  )
}

function IssueHeader({ issue, dita }: { issue: JiraIssue; dita?: GeneratedDita | null }) {
  const attachments = issue.attachments || []
  const videoCount = attachments.filter(attachment => attachment.is_video).length

  return (
    <div className="border-b border-gray-100 px-5 py-4">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-600">{issue.issue_key}</span>
        <ChevronRight className="h-3 w-3 text-gray-400" />
        <span className="text-xs text-gray-500">{issue.issue_type?.toLowerCase()} topic</span>
        {attachments.length ? (
          <span className="rounded bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-600">
            {attachments.length} attachment{attachments.length === 1 ? '' : 's'}
          </span>
        ) : null}
        {videoCount ? (
          <span className="rounded bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-700">
            {videoCount} video{videoCount === 1 ? '' : 's'}
          </span>
        ) : null}
        {dita ? (
          <>
            <ChevronRight className="h-3 w-3 text-gray-400" />
            <span className="text-xs text-gray-500">{dita.filename}</span>
            <span
              className={`ml-auto rounded px-2 py-0.5 text-xs font-medium ${
                dita.quality_score >= 80
                  ? 'bg-emerald-50 text-emerald-700'
                  : dita.quality_score >= 60
                    ? 'bg-amber-50 text-amber-700'
                    : 'bg-red-50 text-red-700'
              }`}
            >
              {dita.quality_score}/100 quality
            </span>
          </>
        ) : null}
      </div>
      <p className="text-base font-medium text-gray-900">{issue.summary}</p>
      {attachments.length ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {attachments.slice(0, 3).map(attachment => {
            const label = attachment.filename || 'attachment'
            const icon = attachment.is_video ? (
              <PlayCircle className="h-3 w-3" />
            ) : (
              <Paperclip className="h-3 w-3" />
            )

            if (attachment.download_url) {
              return (
                <a
                  key={`${attachment.id}-${label}`}
                  href={apiUrl(attachment.download_url)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 transition-colors hover:border-blue-300 hover:text-blue-700"
                  title={`Open ${label}`}
                >
                  {icon}
                  <span className="max-w-[220px] truncate">{label}</span>
                </a>
              )
            }

            return (
              <span
                key={`${attachment.id}-${label}`}
                className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600"
                title={label}
              >
                {icon}
                <span className="max-w-[220px] truncate">{label}</span>
              </span>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function GenerationStep({ label, done, loading }: { label: string; done?: boolean; loading?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {done ? (
        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
      ) : loading ? (
        <div className="h-3 w-3 animate-spin rounded-full border border-blue-500 border-t-transparent" />
      ) : (
        <div className="h-3 w-3 rounded-full border border-gray-300" />
      )}
      <span className={done ? 'text-gray-600' : loading ? 'text-blue-600' : 'text-gray-400'}>{label}</span>
    </div>
  )
}

function DitaPreview({ dita }: { dita: GeneratedDita }) {
  const content = dita.content

  const extract = (tag: string) => {
    const match = content.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'))
    return match ? match[1].replace(/<[^>]+>/g, '').trim() : null
  }

  const extractAll = (tag: string) => {
    const results: string[] = []
    const pattern = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
    let match: RegExpExecArray | null
    while ((match = pattern.exec(content)) !== null) {
      results.push(match[1].replace(/<[^>]+>/g, '').trim())
    }
    return results
  }

  const title = extract('title')
  const shortdesc = extract('shortdesc')
  const prereq = extract('prereq')
  const context = extract('context')
  const commands = extractAll('cmd')
  const result = extract('result')
  const sections = extractAll('section')

  return (
    <div className="space-y-4 text-sm leading-relaxed">
      {title ? <h2 className="text-lg font-medium text-gray-900">{title}</h2> : null}

      {shortdesc ? (
        <div className="flex gap-2">
          <ElementBadge label="shortdesc" color="blue" />
          <p className="text-xs text-gray-600">{shortdesc}</p>
        </div>
      ) : null}

      {prereq ? (
        <div className="border-l-2 border-gray-200 pl-3">
          <ElementBadge label="prereq" color="gray" />
          <p className="mt-1 text-xs text-gray-600">{prereq}</p>
        </div>
      ) : null}

      {context ? (
        <div className="border-l-2 border-gray-200 pl-3">
          <ElementBadge label="context" color="gray" />
          <p className="mt-1 text-xs text-gray-600">{context}</p>
        </div>
      ) : null}

      {commands.length ? (
        <div className="border-l-2 border-gray-200 pl-3">
          <ElementBadge label="steps" color="green" />
          <div className="mt-2 space-y-2">
            {commands.map((command, index) => (
              <div key={`${command}-${index}`} className="flex items-start gap-2">
                <span className="mt-0.5 w-4 text-xs text-gray-400">{index + 1}.</span>
                <div>
                  <ElementBadge label="cmd" color="amber" />
                  <span className="ml-2 text-xs text-gray-700">{command}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {sections.map((section, index) => (
        <div key={`${section}-${index}`} className="border-l-2 border-gray-200 pl-3">
          <ElementBadge label="section" color="purple" />
          <p className="mt-1 text-xs text-gray-600">{section.slice(0, 300)}</p>
        </div>
      ))}

      {result ? (
        <div className="border-l-2 border-emerald-200 pl-3">
          <ElementBadge label="result" color="green" />
          <p className="mt-1 text-xs text-gray-600">{result}</p>
        </div>
      ) : null}
    </div>
  )
}

function ElementBadge({ label, color }: { label: string; color: string }) {
  const colors: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-700',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    gray: 'bg-gray-100 text-gray-600',
    purple: 'bg-violet-50 text-violet-700',
  }

  return <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-xs font-medium ${colors[color] || colors.gray}`}>{label}</span>
}

function InfoPill({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'gray' | 'blue' | 'amber' | 'emerald'
}) {
  const tones: Record<string, string> = {
    gray: 'bg-gray-100 text-gray-600',
    blue: 'bg-blue-50 text-blue-700',
    amber: 'bg-amber-50 text-amber-700',
    emerald: 'bg-emerald-50 text-emerald-700',
  }

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${tones[tone] || tones.gray}`}>
      <span className="text-gray-400">{label}</span>
      <span>{value}</span>
    </span>
  )
}

function XmlEditor({
  content,
  onChange,
  filename,
  wrapLines,
  onAutoIndent,
  hasUnsavedChanges,
  failingChecks,
}: {
  content: string
  onChange: (value: string) => void
  filename: string
  wrapLines: boolean
  onAutoIndent: () => void
  hasUnsavedChanges: boolean
  failingChecks: string[]
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'f') {
      event.preventDefault()
      onAutoIndent()
      return
    }

    if (event.key !== 'Tab') {
      return
    }

    event.preventDefault()
    const target = event.currentTarget
    const { selectionStart, selectionEnd, value } = target
    const selectedText = value.slice(selectionStart, selectionEnd)

    if (!selectedText.includes('\n')) {
      if (event.shiftKey) {
        const lineStart = value.lastIndexOf('\n', selectionStart - 1) + 1
        const line = value.slice(lineStart, selectionEnd || selectionStart)
        const removalLength = line.startsWith(XML_INDENT) ? XML_INDENT.length : line.startsWith('\t') ? 1 : 0
        if (removalLength === 0) {
          return
        }
        const nextValue = `${value.slice(0, lineStart)}${value.slice(lineStart + removalLength)}`
        onChange(nextValue)
        window.requestAnimationFrame(() => {
          const nextPosition = Math.max(selectionStart - removalLength, lineStart)
          textareaRef.current?.setSelectionRange(nextPosition, nextPosition)
        })
        return
      }

      const nextValue = `${value.slice(0, selectionStart)}${XML_INDENT}${value.slice(selectionEnd)}`
      onChange(nextValue)
      window.requestAnimationFrame(() => {
        const nextPosition = selectionStart + XML_INDENT.length
        textareaRef.current?.setSelectionRange(nextPosition, nextPosition)
      })
      return
    }

    const lineStart = value.lastIndexOf('\n', selectionStart - 1) + 1
    const lineEnd = selectionEnd + value.slice(selectionEnd).indexOf('\n')
    const safeLineEnd = lineEnd < selectionEnd ? value.length : lineEnd
    const block = value.slice(lineStart, safeLineEnd)
    const updatedBlock = event.shiftKey
      ? block
          .split('\n')
          .map(line => (line.startsWith(XML_INDENT) ? line.slice(XML_INDENT.length) : line.replace(/^\t/, '')))
          .join('\n')
      : block
          .split('\n')
          .map(line => `${XML_INDENT}${line}`)
          .join('\n')

    const nextValue = `${value.slice(0, lineStart)}${updatedBlock}${value.slice(safeLineEnd)}`
    onChange(nextValue)

    const delta = updatedBlock.length - block.length
    window.requestAnimationFrame(() => {
      textareaRef.current?.setSelectionRange(selectionStart, selectionEnd + delta)
    })
  }

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-3 py-2">
          <div>
            <p className="text-xs font-medium text-gray-600">Live XML workspace</p>
            <p className="text-[11px] text-gray-400">Edit XML directly, then save to re-score and re-run validation.</p>
          </div>
          <div className="flex items-center gap-2">
            {hasUnsavedChanges ? (
              <span className="rounded bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700">Changes pending</span>
            ) : (
              <span className="rounded bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700">Synced</span>
            )}
            <span className="font-mono text-[11px] text-gray-400">{filename}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 bg-gray-50 px-3 py-2">
          <button
            onClick={onAutoIndent}
            className="rounded border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-100"
          >
            Auto-indent
          </button>
          <span className="text-[11px] text-gray-400">Tab indents selected lines. Shift+Tab outdents.</span>
        </div>
        {failingChecks.length ? (
          <div className="flex flex-wrap items-center gap-2 border-b border-amber-100 bg-amber-50 px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 text-amber-600" />
            <span className="text-[11px] font-medium text-amber-700">Last validation gaps:</span>
            {failingChecks.slice(0, 4).map(check => (
              <span key={check} className="rounded bg-white px-2 py-0.5 text-[11px] text-amber-700">
                {check}
              </span>
            ))}
          </div>
        ) : null}
        <textarea
          ref={textareaRef}
          value={content}
          onChange={event => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          wrap={wrapLines ? 'soft' : 'off'}
          className={`min-h-[520px] w-full rounded-b-lg border-0 bg-gray-50 p-4 font-mono text-xs leading-relaxed text-gray-700 focus:outline-none ${
            wrapLines ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'
          }`}
        />
      </div>
    </div>
  )
}

function RenderedPreview({ content }: { content: string }) {
  const extract = (tag: string) => {
    const match = content.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'))
    return match ? match[1].replace(/<[^>]+>/g, '').trim() : null
  }

  const extractAll = (tag: string) => {
    const results: string[] = []
    const pattern = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
    let match: RegExpExecArray | null
    while ((match = pattern.exec(content)) !== null) {
      results.push(match[1].replace(/<[^>]+>/g, '').trim())
    }
    return results
  }

  return (
    <div className="prose prose-sm max-w-none">
      <h1 className="text-xl font-semibold">{extract('title')}</h1>
      {extract('shortdesc') ? <p className="italic text-gray-600">{extract('shortdesc')}</p> : null}
      {extract('context') ? (
        <section>
          <h3>Context</h3>
          <p>{extract('context')}</p>
        </section>
      ) : null}
      {extractAll('cmd').length ? (
        <section>
          <h3>Steps</h3>
          <ol>
            {extractAll('cmd').map((command, index) => (
              <li key={`${command}-${index}`}>{command}</li>
            ))}
          </ol>
        </section>
      ) : null}
      {extract('result') ? (
        <section>
          <h3>Result</h3>
          <p>{extract('result')}</p>
        </section>
      ) : null}
    </div>
  )
}
