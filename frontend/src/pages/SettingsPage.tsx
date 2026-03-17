import { useState, useCallback, useEffect } from 'react';
import { apiUrl, fetchJson } from '@/utils/api';
import { Settings, Database, FileText, Loader2, CheckCircle, XCircle } from 'lucide-react';

interface RagStatus {
  chroma_available: boolean;
  aem_guides?: {
    source: string;
    chunk_count: number;
    populate_via: string;
  };
  dita_spec?: {
    source: string;
    chunk_count: number;
    populate_via: string;
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
      const data = await fetchJson<RagStatus>(apiUrl('/api/v1/ai/rag-status'));
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

            {ragStatus.aem_guides && (
              <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
                <div className="flex items-center gap-2 mb-2">
                  <FileText className="w-4 h-4 text-slate-600" />
                  <span className="font-medium">AEM Guides (Experience League)</span>
                </div>
                <p className="text-sm text-slate-600 mb-2">{ragStatus.aem_guides.source}</p>
                <p className="text-sm font-mono">
                  Chunks: <strong>{ragStatus.aem_guides.chunk_count}</strong>
                </p>
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
            )}

            {ragStatus.dita_spec && (
              <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
                <div className="flex items-center gap-2 mb-2">
                  <FileText className="w-4 h-4 text-slate-600" />
                  <span className="font-medium">DITA Spec PDFs</span>
                </div>
                <p className="text-sm text-slate-600 mb-2">{ragStatus.dita_spec.source}</p>
                <p className="text-sm font-mono">
                  Chunks: <strong>{ragStatus.dita_spec.chunk_count}</strong>
                </p>
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
            )}

            {ragStatus.error && (
              <p className="text-sm text-amber-600">{ragStatus.error}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
