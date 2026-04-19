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
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
          <span className="text-blue-800">Connecting...</span>
        </div>
      </div>
    );
  }

  if (status.status === 'failed') {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <strong>Generation failed:</strong> {status.error || 'Unknown error'}
      </div>
    );
  }

  if (status.status === 'completed' && status.result?.download_url) {
    const url = apiUrl(status.result.download_url);
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm">
        <div className="flex items-center justify-between gap-4">
          <span className="text-green-800 font-medium">DITA bundle ready</span>
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="rounded bg-green-600 px-3 py-1.5 text-white hover:bg-green-700"
          >
            Download
          </a>
        </div>
      </div>
    );
  }

  const stageLabel = status.stage ? STAGE_LABELS[status.stage] || status.message || status.stage : 'Processing...';
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm">
      <div className="flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
        <span className="text-blue-800">{stageLabel}</span>
      </div>
    </div>
  );
}
