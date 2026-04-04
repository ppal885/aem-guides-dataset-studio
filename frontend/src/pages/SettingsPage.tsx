import { useState, useCallback, useEffect } from 'react';
import { apiUrl, fetchJson } from '@/utils/api';
import { Settings, Database, FileText, Loader2, CheckCircle, XCircle } from 'lucide-react';

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
  /** Tavily API for chat web search (no secrets exposed) */
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
  const [lastAction, setLastAction] = useState<string | null>(null);

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
              <strong>{ragStatus.dita_spec?.chunk_count ?? 0}</strong> chunks. Recipe catalog is not counted here.
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
                  <code className="text-xs">backend/.env</code> or project-root <code className="text-xs">.env</code>, then
                  restart the backend
                </span>
              )}
            </p>
            {ragStatus.tavily?.hint ? (
              <p className="text-xs text-slate-500 mt-1">{ragStatus.tavily.hint}</p>
            ) : null}

            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-slate-600" />
                <span className="font-medium">AEM Guides (Experience League)</span>
              </div>
              <p className="text-sm text-slate-600 mb-2">
                {ragStatus.aem_guides?.source ??
                  'Chroma `aem_guides`: Experience League documentation crawl for chat RAG.'}
              </p>
              <p className="text-sm font-mono">
                Chunks in <code className="text-xs">{ragStatus.aem_guides?.collection ?? 'aem_guides'}</code>:{' '}
                <strong>{ragStatus.aem_guides?.chunk_count ?? 0}</strong>
              </p>
              {ragStatus.aem_guides?.count_scope ? (
                <p className="text-xs text-slate-500 mt-2 leading-relaxed">{ragStatus.aem_guides.count_scope}</p>
              ) : null}
              <button
                onClick={handleCrawlAem}
                disabled={crawlingAem}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {crawlingAem ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Crawling...
                  </>
                ) : (
                  'Crawl AEM Guides'
                )}
              </button>
            </div>

            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="w-4 h-4 text-slate-600" />
                <span className="font-medium">DITA Spec PDFs</span>
              </div>
              <p className="text-sm text-slate-600 mb-2">
                {ragStatus.dita_spec?.source ?? 'DITA 1.2 + 1.3 Part 1 Base PDFs in Chroma `dita_spec`.'}
              </p>
              <p className="text-sm font-mono">
                Chunks in <code className="text-xs">{ragStatus.dita_spec?.collection ?? 'dita_spec'}</code>:{' '}
                <strong>{ragStatus.dita_spec?.chunk_count ?? 0}</strong>
              </p>
              {ragStatus.dita_spec?.count_scope ? (
                <p className="text-xs text-slate-500 mt-2 leading-relaxed">{ragStatus.dita_spec.count_scope}</p>
              ) : null}
              <button
                onClick={handleIndexDita}
                disabled={indexingDita}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {indexingDita ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Indexing...
                  </>
                ) : (
                  'Index DITA PDF'
                )}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
