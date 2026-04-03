import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Building2,
  CheckCircle,
  Database,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  Upload,
  XCircle,
} from 'lucide-react'
import {
  apiUrl,
  fetchJson,
  getTenantId,
  setTenantId as persistTenantId,
  withTenantHeaders,
} from '@/utils/api'

interface RagStatus {
  chroma_available: boolean
  aem_guides?: {
    source: string
    chunk_count: number
    populate_via: string
  }
  dita_spec?: {
    source: string
    chunk_count: number
    populate_via: string
  }
  oxygen_examples?: {
    source: string
    source_url?: string
    chunk_count: number
    files_indexed?: number
    example_chunk_count?: number
    rag_chunk_count?: number
    indexed_at?: string
    populate_via: string
  }
  error?: string
}

interface TenantSummary {
  tenant_id: string
  name: string
  is_active?: boolean
  plan?: string
}

interface TenantDetails extends TenantSummary {
  jira_url?: string
  jira_email?: string
  token_configured?: boolean
  rag_collection?: string
  examples_collection?: string
  research_collection?: string
  terminology?: Record<string, string>
  forbidden_terms?: string[]
  style_rules?: string
  component_map?: Record<string, { audience?: string; product?: string }>
}

interface IndexedDoc {
  filename: string
  label: string
  doc_type: string
  chunks: number
  indexed_at: string
  file_hash: string
}

const EMPTY_JSON = '{\n  \n}'

function prettyJson(value: unknown, fallback: string = EMPTY_JSON): string {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch {
    return fallback
  }
}

function getApiError(payload: unknown): string | null {
  if (payload && typeof payload === 'object' && 'error' in payload && typeof payload.error === 'string' && payload.error) {
    return payload.error
  }
  return null
}

export function SettingsPage() {
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [ragError, setRagError] = useState<string | null>(null)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const [docError, setDocError] = useState<string | null>(null)
  const [indexingDita, setIndexingDita] = useState(false)
  const [crawlingAem, setCrawlingAem] = useState(false)
  const [indexingGithubExamples, setIndexingGithubExamples] = useState(false)
  const [lastAction, setLastAction] = useState<string | null>(null)

  const [tenantId, setTenantId] = useState(() => getTenantId())
  const [tenants, setTenants] = useState<TenantSummary[]>([])
  const [tenantDetails, setTenantDetails] = useState<TenantDetails | null>(null)
  const [tenantSaving, setTenantSaving] = useState(false)
  const [knowledgeSaving, setKnowledgeSaving] = useState(false)
  const [uploadingPdf, setUploadingPdf] = useState(false)
  const [indexedDocs, setIndexedDocs] = useState<IndexedDoc[]>([])
  const [creatingTenant, setCreatingTenant] = useState(false)

  const [workspaceForm, setWorkspaceForm] = useState({
    name: '',
    plan: 'standard',
    jira_url: '',
    jira_email: '',
    jira_token: '',
  })
  const [knowledgeForm, setKnowledgeForm] = useState({
    terminology: EMPTY_JSON,
    component_map: EMPTY_JSON,
    forbidden_terms: '',
    style_rules: '',
  })
  const [createForm, setCreateForm] = useState({
    tenant_id: '',
    name: '',
    plan: 'standard',
    jira_url: '',
    jira_email: '',
    jira_token: '',
  })
  const [uploadForm, setUploadForm] = useState({
    doc_type: 'product_doc',
    label: '',
  })
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const loadRagStatus = useCallback(async () => {
    setLoading(true)
    setRagError(null)
    try {
      const data = await fetchJson<RagStatus>(apiUrl('/api/v1/ai/rag-status'))
      setRagStatus(data)
      setRagError(null)
    } catch (caughtError) {
      setRagError(caughtError instanceof Error ? caughtError.message : 'Failed to load RAG status')
      setRagStatus(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTenants = useCallback(async () => {
    const data = await fetchJson<{ tenants: TenantSummary[] }>(
      apiUrl('/api/v1/admin/tenants'),
      { headers: withTenantHeaders({}, tenantId) },
    )
    const apiError = getApiError(data)
    if (apiError) {
      throw new Error(apiError)
    }
    setTenants(data.tenants || [])
  }, [tenantId])

  const loadTenantDetails = useCallback(async (activeTenantId: string) => {
    const data = await fetchJson<TenantDetails>(
      apiUrl(`/api/v1/admin/tenants/${activeTenantId}`),
      { headers: withTenantHeaders({}, activeTenantId) },
    )
    const apiError = getApiError(data)
    if (apiError) {
      throw new Error(apiError)
    }
    setTenantDetails(data)
    setWorkspaceForm({
      name: data.name || activeTenantId,
      plan: data.plan || 'standard',
      jira_url: data.jira_url || '',
      jira_email: data.jira_email || '',
      jira_token: '',
    })
    setKnowledgeForm({
      terminology: prettyJson(data.terminology || {}),
      component_map: prettyJson(data.component_map || {}),
      forbidden_terms: (data.forbidden_terms || []).join('\n'),
      style_rules: data.style_rules || '',
    })
  }, [])

  const loadIndexedDocs = useCallback(async (activeTenantId: string) => {
    const data = await fetchJson<{ docs: IndexedDoc[] }>(
      apiUrl('/api/v1/docs/indexed'),
      { headers: withTenantHeaders({}, activeTenantId) },
    )
    const apiError = getApiError(data)
    if (apiError) {
      throw new Error(apiError)
    }
    setIndexedDocs(data.docs || [])
  }, [])

  const refreshTenantSurface = useCallback(async (activeTenantId: string) => {
    setWorkspaceError(null)
    try {
      await loadTenants()
      await loadTenantDetails(activeTenantId)
      setWorkspaceError(null)
    } catch (caughtError) {
      setWorkspaceError(caughtError instanceof Error ? caughtError.message : 'Failed to load tenant settings')
    }
  }, [loadTenantDetails, loadTenants])

  const refreshIndexedDocs = useCallback(async (activeTenantId: string) => {
    setDocError(null)
    try {
      await loadIndexedDocs(activeTenantId)
      setDocError(null)
    } catch (caughtError) {
      setDocError(caughtError instanceof Error ? caughtError.message : 'Failed to load indexed documents')
    }
  }, [loadIndexedDocs])

  useEffect(() => {
    void loadRagStatus()
  }, [loadRagStatus])

  useEffect(() => {
    persistTenantId(tenantId)
    void refreshTenantSurface(tenantId)
    void refreshIndexedDocs(tenantId)
  }, [refreshIndexedDocs, refreshTenantSurface, tenantId])

  const handleIndexDita = useCallback(async () => {
    setIndexingDita(true)
    setLastAction(null)
    setRagError(null)
    try {
      const result = await fetchJson<{ chunks_stored?: number; errors?: string[] }>(
        apiUrl('/api/v1/ai/index-dita-pdf'),
        { method: 'POST', body: JSON.stringify({}), headers: withTenantHeaders({ 'Content-Type': 'application/json' }, tenantId) },
      )
      const apiError = getApiError(result)
      if (apiError) {
        throw new Error(apiError)
      }
      const chunks = result.chunks_stored ?? 0
      const errs = result.errors ?? []
      setLastAction(errs.length ? `Indexed ${chunks} chunks with errors: ${errs.join('; ')}` : `Indexed ${chunks} DITA chunks`)
      await loadRagStatus()
    } catch (caughtError) {
      setRagError(caughtError instanceof Error ? caughtError.message : 'Index DITA PDF failed')
    } finally {
      setIndexingDita(false)
    }
  }, [loadRagStatus, tenantId])

  const handleCrawlAem = useCallback(async () => {
    setCrawlingAem(true)
    setLastAction(null)
    setRagError(null)
    try {
      const result = await fetchJson<{ chunks_stored?: number; pages_crawled?: number; errors?: string[] }>(
        apiUrl('/api/v1/ai/crawl-aem-guides'),
        { method: 'POST', body: JSON.stringify({}), headers: withTenantHeaders({ 'Content-Type': 'application/json' }, tenantId) },
      )
      const apiError = getApiError(result)
      if (apiError) {
        throw new Error(apiError)
      }
      const chunks = result.chunks_stored ?? 0
      const pages = result.pages_crawled ?? 0
      const errs = result.errors ?? []
      setLastAction(errs.length ? `Crawled ${pages} pages with ${chunks} chunks and some errors` : `Crawled ${pages} pages and stored ${chunks} chunks`)
      await loadRagStatus()
    } catch (caughtError) {
      setRagError(caughtError instanceof Error ? caughtError.message : 'Crawl AEM Guides failed')
    } finally {
      setCrawlingAem(false)
    }
  }, [loadRagStatus, tenantId])

  const handleIndexGithubExamples = useCallback(async () => {
    setIndexingGithubExamples(true)
    setLastAction(null)
    setRagError(null)
    try {
      const result = await fetchJson<{
        files_indexed?: number
        example_chunks_stored?: number
        rag_chunks_stored?: number
        errors?: string[]
        source_label?: string
      }>(
        apiUrl('/api/v1/ai/index-github-dita-examples'),
        {
          method: 'POST',
          body: JSON.stringify({}),
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }, tenantId),
        },
      )
      const apiError = getApiError(result)
      if (apiError) {
        throw new Error(apiError)
      }
      const files = result.files_indexed ?? 0
      const exampleChunks = result.example_chunks_stored ?? 0
      const ragChunks = result.rag_chunks_stored ?? 0
      const errs = result.errors ?? []
      const sourceLabel = result.source_label || 'GitHub DITA examples'
      setLastAction(
        errs.length
          ? `Indexed ${files} GitHub DITA files from ${sourceLabel} with some errors`
          : `Indexed ${files} GitHub DITA files into examples (${exampleChunks}) and tenant RAG (${ragChunks})`,
      )
      await loadRagStatus()
    } catch (caughtError) {
      setRagError(caughtError instanceof Error ? caughtError.message : 'GitHub DITA example indexing failed')
    } finally {
      setIndexingGithubExamples(false)
    }
  }, [loadRagStatus, tenantId])

  const handleWorkspaceSave = useCallback(async () => {
    setTenantSaving(true)
    setWorkspaceError(null)
    try {
      const result = await fetchJson(
        apiUrl(`/api/v1/admin/tenants/${tenantId}`),
        {
          method: 'PUT',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }, tenantId),
          body: JSON.stringify(workspaceForm),
        },
      )
      const apiError = getApiError(result)
      if (apiError) {
        throw new Error(apiError)
      }
      setLastAction(`Saved workspace settings for ${tenantId}`)
      await loadTenants()
      await loadTenantDetails(tenantId)
    } catch (caughtError) {
      setWorkspaceError(caughtError instanceof Error ? caughtError.message : 'Failed to save tenant settings')
    } finally {
      setTenantSaving(false)
    }
  }, [loadTenantDetails, loadTenants, tenantId, workspaceForm])

  const handleKnowledgeSave = useCallback(async () => {
    setKnowledgeSaving(true)
    setWorkspaceError(null)
    try {
      const terminology = JSON.parse(knowledgeForm.terminology || '{}')
      const componentMap = JSON.parse(knowledgeForm.component_map || '{}')
      const forbiddenTerms = knowledgeForm.forbidden_terms
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)

      const result = await fetchJson(
        apiUrl(`/api/v1/admin/tenants/${tenantId}/knowledge-base`),
        {
          method: 'PUT',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }, tenantId),
          body: JSON.stringify({
            terminology: terminology as Record<string, string>,
            component_map: componentMap as Record<string, { audience?: string; product?: string }>,
            forbidden_terms: forbiddenTerms,
            style_rules: knowledgeForm.style_rules,
          }),
        },
      )
      const apiError = getApiError(result)
      if (apiError) {
        throw new Error(apiError)
      }
      setLastAction(`Saved knowledge base for ${tenantId}`)
      await loadTenantDetails(tenantId)
    } catch (caughtError) {
      setWorkspaceError(caughtError instanceof Error ? caughtError.message : 'Failed to save tenant knowledge')
    } finally {
      setKnowledgeSaving(false)
    }
  }, [knowledgeForm, loadTenantDetails, tenantId])

  const handleCreateTenant = useCallback(async () => {
    setCreatingTenant(true)
    setWorkspaceError(null)
    try {
      const created = await fetchJson<TenantDetails>(
        apiUrl('/api/v1/admin/tenants'),
        {
          method: 'POST',
          headers: withTenantHeaders({ 'Content-Type': 'application/json' }, tenantId),
          body: JSON.stringify(createForm),
        },
      )
      const apiError = getApiError(created)
      if (apiError) {
        throw new Error(apiError)
      }
      const nextTenantId = created.tenant_id || createForm.tenant_id
      setCreateForm({
        tenant_id: '',
        name: '',
        plan: 'standard',
        jira_url: '',
        jira_email: '',
        jira_token: '',
      })
      setTenantId(nextTenantId)
      setLastAction(`Created tenant ${nextTenantId}`)
    } catch (caughtError) {
      setWorkspaceError(caughtError instanceof Error ? caughtError.message : 'Failed to create tenant')
    } finally {
      setCreatingTenant(false)
    }
  }, [createForm, tenantId])

  const handleUploadPdf = useCallback(async () => {
    if (!selectedFile) {
      setDocError('Choose a PDF to upload first.')
      return
    }

    setUploadingPdf(true)
    setDocError(null)
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('doc_type', uploadForm.doc_type)
      formData.append('label', uploadForm.label)

      const response = await fetch(apiUrl('/api/v1/docs/index-pdf'), {
        method: 'POST',
        headers: withTenantHeaders({}, tenantId),
        body: formData,
      })
      const data = await response.json()
      if (!response.ok || data.error) {
        throw new Error(data.error || 'Failed to upload PDF')
      }

      setSelectedFile(null)
      setUploadForm(previous => ({ ...previous, label: '' }))
      setLastAction(`Indexed ${data.chunks_stored || 0} chunks from ${data.filename}`)
      await refreshIndexedDocs(tenantId)
    } catch (caughtError) {
      setDocError(caughtError instanceof Error ? caughtError.message : 'Failed to upload PDF')
    } finally {
      setUploadingPdf(false)
    }
  }, [refreshIndexedDocs, selectedFile, tenantId, uploadForm.doc_type, uploadForm.label])

  const handleRemoveDoc = useCallback(async (fileHash: string) => {
    setDocError(null)
    try {
      const result = await fetchJson(
        apiUrl(`/api/v1/docs/indexed/${fileHash}`),
        {
          method: 'DELETE',
          headers: withTenantHeaders({}, tenantId),
        },
      )
      const apiError = getApiError(result)
      if (apiError) {
        throw new Error(apiError)
      }
      setLastAction('Removed indexed document')
      await refreshIndexedDocs(tenantId)
    } catch (caughtError) {
      setDocError(caughtError instanceof Error ? caughtError.message : 'Failed to remove indexed document')
    }
  }, [refreshIndexedDocs, tenantId])

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100">
          <Settings className="h-6 w-6 text-slate-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-600">Tenant workspaces, knowledge sources, and indexing controls</p>
        </div>
      </div>

      {lastAction ? (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-700">
          <CheckCircle className="h-5 w-5 shrink-0" />
          <span>{lastAction}</span>
        </div>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-900">
            <Database className="h-5 w-5" />
            RAG status
          </h2>

          {ragError ? <InlineError message={ragError} className="mb-4" /> : null}

          {loading ? (
            <div className="flex items-center gap-2 py-4 text-slate-600">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading RAG status...
            </div>
          ) : null}

          {!loading && ragStatus ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                {ragStatus.chroma_available ? (
                  <CheckCircle className="h-5 w-5 text-green-600" />
                ) : (
                  <XCircle className="h-5 w-5 text-amber-600" />
                )}
                <span className="font-medium">
                  ChromaDB: {ragStatus.chroma_available ? 'Available' : 'Not available'}
                </span>
              </div>

              <SourceCard
                title="AEM Guides crawl"
                subtitle={ragStatus.aem_guides?.source || 'Experience League source'}
                chunks={ragStatus.aem_guides?.chunk_count || 0}
                actionLabel={crawlingAem ? 'Crawling...' : 'Crawl AEM Guides'}
                onAction={handleCrawlAem}
                loading={crawlingAem}
              />

              <SourceCard
                title="DITA spec PDFs"
                subtitle={ragStatus.dita_spec?.source || 'DITA PDF source'}
                chunks={ragStatus.dita_spec?.chunk_count || 0}
                actionLabel={indexingDita ? 'Indexing...' : 'Index DITA PDF'}
                onAction={handleIndexDita}
                loading={indexingDita}
              />

              <SourceCard
                title="Oxygen DITA examples"
                subtitle={
                  ragStatus.oxygen_examples
                    ? `${ragStatus.oxygen_examples.source}${ragStatus.oxygen_examples.files_indexed ? ` · ${ragStatus.oxygen_examples.files_indexed} files` : ''}`
                    : 'GitHub DITA topics and maps for examples and tenant RAG'
                }
                chunks={ragStatus.oxygen_examples?.chunk_count || 0}
                actionLabel={indexingGithubExamples ? 'Indexing...' : 'Index GitHub DITA'}
                onAction={handleIndexGithubExamples}
                loading={indexingGithubExamples}
              />
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Building2 className="h-5 w-5 text-slate-600" />
            <h2 className="text-lg font-semibold text-slate-900">Active workspace</h2>
          </div>

          {workspaceError ? <InlineError message={workspaceError} className="mb-4" /> : null}

          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">Tenant</label>
          <select
            value={tenantId}
            onChange={event => setTenantId(event.target.value)}
            className="mb-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            {tenants.map(tenant => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.name} ({tenant.tenant_id})
              </option>
            ))}
          </select>

          <div className="grid gap-3 sm:grid-cols-2">
            <InfoPill label="RAG collection" value={tenantDetails?.rag_collection || 'n/a'} />
            <InfoPill label="Examples" value={tenantDetails?.examples_collection || 'n/a'} />
            <InfoPill label="Plan" value={tenantDetails?.plan || 'standard'} />
            <InfoPill label="Token" value={tenantDetails?.token_configured ? 'Configured' : 'Not set'} />
          </div>

          <button
            onClick={() => {
              void refreshTenantSurface(tenantId)
            }}
            className="mt-4 flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh workspace
          </button>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Workspace configuration</h2>
            <button
              onClick={handleWorkspaceSave}
              disabled={tenantSaving}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {tenantSaving ? 'Saving...' : 'Save workspace'}
            </button>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Display name">
              <input
                value={workspaceForm.name}
                onChange={event => setWorkspaceForm(previous => ({ ...previous, name: event.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </Field>
            <Field label="Plan">
              <select
                value={workspaceForm.plan}
                onChange={event => setWorkspaceForm(previous => ({ ...previous, plan: event.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="standard">Standard</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </Field>
            <Field label="Jira URL">
              <input
                value={workspaceForm.jira_url}
                onChange={event => setWorkspaceForm(previous => ({ ...previous, jira_url: event.target.value }))}
                placeholder="https://your-jira.example.com"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </Field>
            <Field label="Jira email">
              <input
                value={workspaceForm.jira_email}
                onChange={event => setWorkspaceForm(previous => ({ ...previous, jira_email: event.target.value }))}
                placeholder="docs@example.com"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </Field>
            <Field label="Jira API token">
              <input
                type="password"
                value={workspaceForm.jira_token}
                onChange={event => setWorkspaceForm(previous => ({ ...previous, jira_token: event.target.value }))}
                placeholder={tenantDetails?.token_configured ? 'Leave blank to keep current token' : 'Paste API token'}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </Field>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Plus className="h-4 w-4 text-slate-500" />
            <h2 className="text-lg font-semibold text-slate-900">Create tenant</h2>
          </div>

          <div className="space-y-3">
            <input
              value={createForm.tenant_id}
              onChange={event => setCreateForm(previous => ({ ...previous, tenant_id: event.target.value }))}
              placeholder="tenant_id"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <input
              value={createForm.name}
              onChange={event => setCreateForm(previous => ({ ...previous, name: event.target.value }))}
              placeholder="Tenant display name"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <select
              value={createForm.plan}
              onChange={event => setCreateForm(previous => ({ ...previous, plan: event.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="standard">Standard</option>
              <option value="enterprise">Enterprise</option>
            </select>
            <input
              value={createForm.jira_url}
              onChange={event => setCreateForm(previous => ({ ...previous, jira_url: event.target.value }))}
              placeholder="Jira URL"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <input
              value={createForm.jira_email}
              onChange={event => setCreateForm(previous => ({ ...previous, jira_email: event.target.value }))}
              placeholder="Jira email"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <input
              type="password"
              value={createForm.jira_token}
              onChange={event => setCreateForm(previous => ({ ...previous, jira_token: event.target.value }))}
              placeholder="Jira API token"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <button
              onClick={handleCreateTenant}
              disabled={creatingTenant || !createForm.tenant_id.trim() || !createForm.name.trim()}
              className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {creatingTenant ? 'Creating...' : 'Create tenant'}
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Knowledge base</h2>
            <p className="text-sm text-slate-500">Terminology, style rules, and component audience mapping for {tenantId}</p>
          </div>
          <button
            onClick={handleKnowledgeSave}
            disabled={knowledgeSaving}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {knowledgeSaving ? 'Saving...' : 'Save knowledge'}
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Field label="Terminology map (JSON)">
            <textarea
              value={knowledgeForm.terminology}
              onChange={event => setKnowledgeForm(previous => ({ ...previous, terminology: event.target.value }))}
              className="min-h-[220px] w-full rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs"
            />
          </Field>

          <Field label="Component map (JSON)">
            <textarea
              value={knowledgeForm.component_map}
              onChange={event => setKnowledgeForm(previous => ({ ...previous, component_map: event.target.value }))}
              className="min-h-[220px] w-full rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs"
            />
          </Field>

          <Field label="Forbidden terms">
            <textarea
              value={knowledgeForm.forbidden_terms}
              onChange={event => setKnowledgeForm(previous => ({ ...previous, forbidden_terms: event.target.value }))}
              placeholder="One term per line"
              className="min-h-[160px] w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm"
            />
          </Field>

          <Field label="Style rules">
            <textarea
              value={knowledgeForm.style_rules}
              onChange={event => setKnowledgeForm(previous => ({ ...previous, style_rules: event.target.value }))}
              placeholder="Client-specific writing rules..."
              className="min-h-[160px] w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm"
            />
          </Field>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Client PDFs</h2>
            <p className="text-sm text-slate-500">Upload tenant-specific product docs, style guides, and approved topics for RAG</p>
          </div>
          <button
            onClick={() => void refreshIndexedDocs(tenantId)}
            className="flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh docs
          </button>
        </div>

        {docError ? <InlineError message={docError} className="mb-4" /> : null}

        <div className="mb-6 grid gap-3 lg:grid-cols-[180px_1fr_160px_auto]">
          <select
            value={uploadForm.doc_type}
            onChange={event => setUploadForm(previous => ({ ...previous, doc_type: event.target.value }))}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="product_doc">Product doc</option>
            <option value="style_guide">Style guide</option>
            <option value="approved_topic">Approved topic</option>
            <option value="terminology">Terminology</option>
            <option value="api_reference">API reference</option>
            <option value="release_notes">Release notes</option>
            <option value="user_manual">User manual</option>
            <option value="other">Other</option>
          </select>
          <input
            value={uploadForm.label}
            onChange={event => setUploadForm(previous => ({ ...previous, label: event.target.value }))}
            placeholder="Optional label"
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <input
            type="file"
            accept="application/pdf"
            onChange={event => setSelectedFile(event.target.files?.[0] || null)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <button
            onClick={handleUploadPdf}
            disabled={uploadingPdf || !selectedFile}
            className="flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {uploadingPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {uploadingPdf ? 'Uploading...' : 'Upload'}
          </button>
        </div>

        {!indexedDocs.length ? (
          <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
            No tenant PDFs indexed yet.
          </div>
        ) : (
          <div className="space-y-2">
            {indexedDocs.map(doc => (
              <div key={`${doc.file_hash}-${doc.filename}`} className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3">
                <FileText className="h-4 w-4 text-slate-500" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">{doc.label || doc.filename}</p>
                  <p className="text-xs text-slate-500">
                    {doc.doc_type} / {doc.chunks} chunks / {doc.indexed_at ? new Date(doc.indexed_at).toLocaleString() : 'Unknown date'}
                  </p>
                </div>
                <button
                  onClick={() => void handleRemoveDoc(doc.file_hash)}
                  className="rounded-md border border-red-200 p-2 text-red-600 hover:bg-red-50"
                  title="Remove indexed document"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      {children}
    </label>
  )
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 font-mono text-xs text-slate-600">{value}</p>
    </div>
  )
}

function InlineError({ message, className = '' }: { message: string; className?: string }) {
  return (
    <div className={`flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 ${className}`.trim()}>
      <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function SourceCard({
  title,
  subtitle,
  chunks,
  actionLabel,
  onAction,
  loading,
}: {
  title: string
  subtitle: string
  chunks: number
  actionLabel: string
  onAction: () => void
  loading: boolean
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-medium text-slate-900">{title}</p>
          <p className="text-sm text-slate-500">{subtitle}</p>
        </div>
        <p className="rounded bg-white px-2 py-1 font-mono text-sm text-slate-700">{chunks} chunks</p>
      </div>
      <button
        onClick={onAction}
        disabled={loading}
        className="mt-3 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Working...' : actionLabel}
      </button>
    </div>
  )
}
