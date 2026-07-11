import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { getGenerateStatus, type GenerateStatus } from '@/api/chat';
import { apiUrl } from '@/utils/api';

interface GenerationProgressCardProps {
  runId: string;
  onComplete?: (status: GenerateStatus) => void;
}

const STAGE_LABELS: Record<string, string> = {
  starting: 'Starting...',
  planning: 'Planning...',
  generating: 'Generating DITA...',
  enriching: 'Enriching DITA...',
  validating: 'Validating...',
  bundling: 'Building bundle...',
};

export function GenerationProgressCard({ runId, onComplete }: GenerationProgressCardProps) {
  const [status, setStatus] = useState<GenerateStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const s = await getGenerateStatus(runId);
      if (cancelled) return;
      setStatus(s || null);
      if (s?.status === 'completed' || s?.status === 'failed') {
        onComplete?.(s);
        return;
      }
      setTimeout(poll, 800);
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [runId, onComplete]);

  if (!status) {
    return (
      <div className="rounded-lg border border-border bg-muted p-4 text-sm">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-teal-600 dark:text-teal-400" />
          <span className="text-foreground">Connecting...</span>
        </div>
      </div>
    );
  }

  if (status.status === 'failed') {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
        <strong>Generation failed:</strong> {status.error || 'Unknown error'}
      </div>
    );
  }

  if (status.status === 'completed' && status.result?.download_url) {
    const url = apiUrl(status.result.download_url);
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm dark:border-emerald-900 dark:bg-emerald-950/40">
        <div className="flex items-center justify-between gap-4">
          <span className="font-medium text-emerald-900 dark:text-emerald-100">DITA bundle ready</span>
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="rounded bg-emerald-600 px-3 py-1.5 text-white hover:bg-emerald-700 dark:bg-emerald-700 dark:hover:bg-emerald-600"
          >
            Download
          </a>
        </div>
      </div>
    );
  }

  const stageLabel = status.stage ? STAGE_LABELS[status.stage] || status.message || status.stage : 'Processing...';
  return (
    <div className="rounded-lg border border-border bg-muted p-4 text-sm">
      <div className="flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-teal-600 dark:text-teal-400" />
        <span className="text-foreground">{stageLabel}</span>
      </div>
    </div>
  );
}
