import { useState, useCallback, useEffect } from 'react';
import { apiUrl, fetchJson } from '@/utils/api';
import { Settings, Database, FileText, Loader2, CheckCircle, XCircle, Plus, Link } from 'lucide-react';

interface RagStatus {
  chroma_available: boolean;
  aem_guides?: {
    source: string;
    collection?: string;
    chunk_count: number;
    count_scope?: string;
    populate_via: string;
  };
  dita_spec?: {
    source: string;
    collection?: string;
    chunk_count: number;
    count_scope?: string;
    populate_via: string;
  };
  dita_ot_github?: {
    source: string;
    collection?: string;
    chunk_count: number;
    count_scope?: string;
    populate_via: string;
  };
  jira_qa?: {
    source: string;
    collection?: string;
    chunk_count: number;
    count_scope?: string;
    populate_via: string;
  };
  tavily?: {
    configured: boolean;
    chat_enabled: boolean;
    hint?: string | null;
  };
  error?: string;
}

export function SettingsPage() {
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [indexingDita, setIndexingDita] = useState(false);
  const [crawlingAem, setCrawlingAem] = useState(false);
  const [indexingDitaOt, setIndexingDitaOt] = useState(false);
  const [indexingJiraQa, setIndexingJiraQa] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);

  // Custom URL indexing state
  const [customUrlsText, setCustomUrlsText] = useState('');
  const [indexingCustomUrls, setIndexingCustomUrls] = useState(false);
  const [customUrlsResult, setCustomUrlsResult] = useState<{ message: string; isError: boolean } | null>(null);

  const loadRagStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJson<RagStatus>(apiUrl('/api/v1/ai/rag-status?tenant_id=default'));
      setRagStatus(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load RAG status');
      setRagStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRagStatus();
  }, [loadRagStatus]);

  const handleIndexDita = useCallback(async () => {
    setIndexingDita(true);
    setLastAction(null);
    setError(null);
    try {
      const result = await fetchJson<{ chunks_stored?: number; sources_indexed?: string[]; errors?: string[] }>(
        apiUrl('/api/v1/ai/index-dita-pdf'),
        { method: 'POST', body: JSON.stringify({}) }
      );
      const chunks = result.chunks_stored ?? 0;
      const errs = result.errors ?? [];
      if (errs.length > 0) {
        setLastAction(`Indexed ${chunks} chunks with errors: ${errs.join('; ')}`);
      } else {
        setLastAction(`Indexed ${chunks} chunks successfully`);
      }
      await loadRagStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Index DITA PDF failed');
    } finally {
      setIndexingDita(false);
    }
  }, [loadRagStatus]);

  const handleIndexDitaOt = useCallback(async () => {
    setIndexingDitaOt(true);
    setLastAction(null);
    setError(null);
    try {
      const result = await fetchJson<{ indexed?: number; errors?: string[] }>(
        apiUrl('/api/v1/ai/index-dita-ot-github'),
        { method: 'POST' }
      );
      const indexed = result.indexed ?? 0;
      const errs = result.errors ?? [];
      if (errs.length > 0) {
        setLastAction(`Indexed ${indexed} DITA OT issues with errors: ${errs.join('; ')}`);
      } else {
        setLastAction(`Indexed ${indexed} DITA OT GitHub issues successfully`);
      }
      await loadRagStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Index DITA OT GitHub failed');
    } finally {
      setIndexingDitaOt(false);
    }
  }, [loadRagStatus]);

  const handleCrawlAem = useCallback(async () => {
    setCrawlingAem(true);
    setLastAction(null);
    setError(null);
    try {
      const result = await fetchJson<{ chunks_stored?: number; pages_crawled?: number; errors?: string[] }>(
        apiUrl('/api/v1/ai/crawl-aem-guides'),
        { method: 'POST', body: JSON.stringify({}) }
      );
      const chunks = result.chunks_stored ?? 0;
      const pages = result.pages_crawled ?? 0;
      const errs = result.errors ?? [];
      if (errs.length > 0) {
        setLastAction(`Crawled ${pages} pages, stored ${chunks} chunks. Errors: ${errs.join('; ')}`);
      } else {
        setLastAction(`Crawled ${pages} pages, stored ${chunks} chunks`);
      }
      await loadRagStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Crawl AEM Guides failed');
    } finally {
      setCrawlingAem(false);
    }
  }, [loadRagStatus]);

  const handleIndexJiraQa = useCallback(async () => {
    setIndexingJiraQa(true);
    setLastAction(null);
    setError(null);
    try {
      const result = await fetchJson<{ indexed?: number; chunks_stored?: number; errors?: string[] }>(
        apiUrl('/api/v1/jira-rag/index'),
        {
          method: 'POST',
          body: JSON.stringify({ sync_mode: 'incremental', project_key: 'GUIDES', force_reindex: false }),
        }
      );
      const indexed = result.indexed ?? result.chunks_stored ?? 0;
      const errs = result.errors ?? [];
      if (errs.length > 0) {
        setLastAction(`Indexed ${indexed} Jira QA issues with errors: ${errs.join('; ')}`);
      } else {
        setLastAction(`Indexed ${indexed} Jira QA issues successfully`);
      }
      await loadRagStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Index Jira QA failed');
    } finally {
      setIndexingJiraQa(false);
    }
  }, [loadRagStatus]);

  const handleIndexCustomUrls = useCallback(async () => {
    const urls = customUrlsText
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.startsWith('http://') || line.startsWith('https://'));

    if (urls.length === 0) {
      setCustomUrlsResult({ message: 'No valid URLs found. Enter one URL per line starting with http:// or https://', isError: true });
      return;
    }

    setIndexingCustomUrls(true);
    setCustomUrlsResult(null);
    try {
      const result = await fetchJson<{ chunks_stored?: number; pages_crawled?: number; errors?: string[] }>(
        apiUrl('/api/v1/ai/crawl-aem-guides'),
        { method: 'POST', body: JSON.stringify({ urls }) }
      );
      const chunks = result.chunks_stored ?? 0;
      const pages = result.pages_crawled ?? 0;
      const errs = result.errors ?? [];
      if (errs.length > 0) {
        setCustomUrlsResult({
          message: `Indexed ${pages} page(s), ${chunks} chunks. Errors: ${errs.join('; ')}`,
          isError: true,
        });
      } else {
        setCustomUrlsResult({
          message: `${pages} page(s) indexed — ${chunks} chunks added to RAG knowledge base`,
          isError: false,
        });
        setCustomUrlsText('');
      }
      await loadRagStatus();
    } catch (e) {
      setCustomUrlsResult({ message: e instanceof Error ? e.message : 'Indexing failed', isError: true });
    } finally {
      setIndexingCustomUrls(false);
    }
  }, [customUrlsText, loadRagStatus]);

  const validUrlCount = customUrlsText
    .split('\n')
    .filter(line => line.trim().startsWith('http://') || line.trim().startsWith('https://')).length;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center">
          <Settings className="w-6 h-6 text-slate-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
          <p className="text-slate-600 text-sm">RAG indexing and AI configuration</p>
        </div>
      </div>

      <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Database className="w-5 h-5" />
          RAG Status
        </h2>

        {loading && (
          <div className="flex items-center gap-2 text-slate-600 py-4">
            <Loader2 className="w-5 h-5 animate-spin" />
            Loading RAG status...
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 text-red-600 bg-red-50 rounded-lg p-4 mb-4">
            <XCircle className="w-5 h-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {lastAction && !error && (
          <div className="flex items-center gap-2 text-green-700 bg-green-50 rounded-lg p-4 mb-4">
            <CheckCircle className="w-5 h-5 shrink-0" />
            <span>{lastAction}</span>
          </div>
        )}

        {!loading && ragStatus && (
          <div className="space-y-4">
            {ragStatus.error && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <strong className="font-medium">RAG status note:</strong> {ragStatus.error}
              </div>
            )}

            <div className="flex items-center gap-2">
              {ragStatus.chroma_available ? (
                <CheckCircle className="w-5 h-5 text-green-600" />
              ) : (
                <XCircle className="w-5 h-5 text-amber-600" />
              )}
              <span className="font-medium">
                ChromaDB: {ragStatus.chroma_available ? 'Available' : 'Not available'}
              </span>
            </div>

            <p className="text-sm text-slate-700 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <span className="font-medium">Vector RAG (Chroma):</span>{' '}
              <code className="text-xs">{ragStatus.aem_guides?.collection ?? 'aem_guides'}</code> ={' '}
              <strong>{ragStatus.aem_guides?.chunk_count ?? 0}</strong> chunks ·{' '}
              <code className="text-xs">{ragStatus.dita_spec?.collection ?? 'dita_spec'}</code> ={' '}
              <strong>{ragStatus.dita_spec?.chunk_count ?? 0}</strong> chunks ·{' '}
              <code className="text-xs">{ragStatus.dita_ot_github?.collection ?? 'dita_ot_github'}</code> ={' '}
              <strong>{ragStatus.dita_ot_github?.chunk_count ?? 0}</strong> chunks ·{' '}
              <code className="text-xs">{ragStatus.jira_qa?.collection ?? 'jira_qa'}</code> ={' '}
              <strong>{ragStatus.jira_qa?.chunk_count ?? 0}</strong> chunks.
            </p>

            <p className="text-sm text-slate-600">
              Tavily web search (chat):{' '}
              {ragStatus.tavily?.configured ? (
                ragStatus.tavily.chat_enabled ? (
                  <span className="font-medium text-green-700">enabled</span>
                ) : (
                  <span className="font-medium text-amber-700">key set, chat disabled (CHAT_TAVILY_ENABLED=false)</span>
                )
              ) : (
                <span className="font-medium text-slate-500">
                  not configured — set <code className="text-xs">TAVILY_API_KEY</code> in{' '}
                  <code className="text-xs">backend/.env</code>, then restart
                </span>
              )}
            </p>

            {/* AEM Guides */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-slate-600" />
                <span className="font-medium">AEM Guides &amp; Assets (Experience League)</span>
              </div>
              <p className="text-sm text-slate-600 mb-2">
                {ragStatus.aem_guides?.source ?? 'Experience League documentation crawl for chat RAG.'}
              </p>
              <p className="text-sm font-mono mb-3">
                Chunks in <code className="text-xs">{ragStatus.aem_guides?.collection ?? 'aem_guides'}</code>:{' '}
                <strong>{ragStatus.aem_guides?.chunk_count ?? 0}</strong>
              </p>

              {/* Custom URL indexing */}
              <div className="border border-blue-100 rounded-lg p-3 bg-blue-50/40 mb-3">
                <div className="flex items-center gap-2 mb-2">
                  <Link className="w-4 h-4 text-blue-600" />
                  <span className="text-sm font-medium text-blue-900">Add URLs to Knowledge Base</span>
                </div>
                <p className="text-xs text-slate-500 mb-2">
                  Paste one Experience League (or other) URL per line. Each page is crawled, chunked, and added to the RAG index immediately. URLs are also saved for future full re-crawls.
                </p>
                <textarea
                  value={customUrlsText}
                  onChange={e => {
                    setCustomUrlsText(e.target.value);
                    setCustomUrlsResult(null);
                  }}
                  placeholder={`https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/...\nhttps://experienceleague.adobe.com/en/docs/...`}
                  rows={4}
                  className="w-full text-xs font-mono border border-slate-200 rounded-md p-2 bg-white resize-y focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                {customUrlsResult && (
                  <div className={`flex items-start gap-2 mt-2 text-xs rounded-md p-2 ${customUrlsResult.isError ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
                    {customUrlsResult.isError
                      ? <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                      : <CheckCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />}
                    <span>{customUrlsResult.message}</span>
                  </div>
                )}
                <button
                  onClick={handleIndexCustomUrls}
                  disabled={indexingCustomUrls || validUrlCount === 0}
                  className="mt-2 px-3 py-1.5 bg-blue-600 text-white rounded-md text-xs font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                >
                  {indexingCustomUrls ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Indexing {validUrlCount} URL{validUrlCount !== 1 ? 's' : ''}…
                    </>
                  ) : (
                    <>
                      <Plus className="w-3.5 h-3.5" />
                      {validUrlCount > 0
                        ? `Index ${validUrlCount} URL${validUrlCount !== 1 ? 's' : ''}`
                        : 'Index URLs'}
                    </>
                  )}
                </button>
              </div>

              <button
                onClick={handleCrawlAem}
                disabled={crawlingAem}
                className="px-4 py-2 bg-slate-700 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {crawlingAem ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Re-crawling all URLs…
                  </>
                ) : (
                  'Re-crawl All AEM Guides URLs'
                )}
              </button>
            </div>

            {/* DITA Spec */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-slate-600" />
                <span className="font-medium">DITA Spec PDFs</span>
              </div>
              <p className="text-sm text-slate-600 mb-2">
                {ragStatus.dita_spec?.source ?? 'DITA 1.2 + 1.3 Part 1 Base PDFs in Chroma `dita_spec`.'}
              </p>
              <p className="text-sm font-mono mb-3">
                Chunks in <code className="text-xs">{ragStatus.dita_spec?.collection ?? 'dita_spec'}</code>:{' '}
                <strong>{ragStatus.dita_spec?.chunk_count ?? 0}</strong>
              </p>
              <button
                onClick={handleIndexDita}
                disabled={indexingDita}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {indexingDita ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Indexing…
                  </>
                ) : (
                  'Index DITA PDF'
                )}
              </button>
            </div>

            {/* DITA OT GitHub */}
            <div className="rounded-lg border border-slate-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-slate-500" />
                <span className="font-medium">DITA OT GitHub Issues</span>
              </div>
              <p className="text-sm text-slate-600 mb-2">
                {ragStatus.dita_ot_github?.source ?? 'dita-ot/dita-ot GitHub issues for DITA Open Toolkit RAG.'}
              </p>
              <p className="text-sm font-mono mb-3">
                Chunks in <code className="text-xs">{ragStatus.dita_ot_github?.collection ?? 'dita_ot_github'}</code>:{' '}
                <strong>{ragStatus.dita_ot_github?.chunk_count ?? 0}</strong>
              </p>
              <button
                onClick={handleIndexDitaOt}
                disabled={indexingDitaOt}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {indexingDitaOt ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Indexing…
                  </>
                ) : (
                  'Index DITA OT GitHub'
                )}
              </button>
            </div>

            {/* Jira QA */}
            <div className="rounded-lg border border-slate-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-slate-500" />
                <span className="font-medium">Jira QA Knowledge Base</span>
              </div>
              <p className="text-sm text-slate-600 mb-2">
                {ragStatus.jira_qa?.source ?? 'Indexed Jira QA issues (bug reports, QA patterns, past resolutions) for chat RAG.'}
              </p>
              <p className="text-sm font-mono mb-3">
                Chunks in <code className="text-xs">{ragStatus.jira_qa?.collection ?? 'jira_qa'}</code>:{' '}
                <strong>{ragStatus.jira_qa?.chunk_count ?? 0}</strong>
              </p>
              <p className="text-xs text-slate-500 mb-3">
                Uses <code className="text-xs">sync_mode=incremental</code> with <code className="text-xs">project_key=GUIDES</code>.
              </p>
              <button
                onClick={handleIndexJiraQa}
                disabled={indexingJiraQa}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {indexingJiraQa ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Indexing…
                  </>
                ) : (
                  'Index Jira QA'
                )}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
