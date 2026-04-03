import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  DatabaseZap,
  Download,
  Loader2,
} from 'lucide-react';

import { getDatasetJobStatus, type DatasetJobStatus } from '@/api/chat';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { apiUrl } from '@/utils/api';

interface DatasetJobStatusCardProps {
  jobId: string;
  initialStatus?: string | null;
  jobName?: string | null;
  recipeType?: string | null;
  downloadUrl?: string | null;
}

const POLL_INTERVAL_MS = 1200;

export function DatasetJobStatusCard({
  jobId,
  initialStatus,
  jobName,
  recipeType,
  downloadUrl,
}: DatasetJobStatusCardProps) {
  const [status, setStatus] = useState<DatasetJobStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      const nextStatus = await getDatasetJobStatus(jobId);
      if (cancelled) {
        return;
      }
      if (nextStatus) {
        setStatus(nextStatus);
        if (nextStatus.status === 'completed' || nextStatus.status === 'failed') {
          return;
        }
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [jobId]);

  const currentStatus = status?.status || initialStatus || 'pending';
  const progressPercent =
    typeof status?.progress_percent === 'number'
      ? status.progress_percent
      : currentStatus === 'completed'
        ? 100
        : currentStatus === 'running'
          ? 18
          : 4;
  const resolvedDownloadUrl = useMemo(() => {
    if (!downloadUrl) {
      return '';
    }
    return downloadUrl.startsWith('/api/') ? apiUrl(downloadUrl) : downloadUrl;
  }, [downloadUrl]);

  if (currentStatus === 'failed') {
    return (
      <div className="rounded-2xl border border-rose-200 bg-[linear-gradient(135deg,#fff1f2_0%,#fff8f8_100%)] p-4 text-sm text-rose-950">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-rose-600 text-white shadow-sm">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Dataset generation failed</div>
            <div className="mt-1 text-sm leading-6 text-rose-900/90">
              {status?.error_message || 'The dataset ZIP could not be prepared.'}
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-medium text-rose-800/80">
              <span className="rounded-full border border-rose-200 bg-white px-3 py-1">Job ID: {jobId}</span>
              {recipeType ? <span className="rounded-full border border-rose-200 bg-white px-3 py-1">Recipe: {recipeType}</span> : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (currentStatus === 'completed') {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-[linear-gradient(135deg,#ecfdf5_0%,#f7fffb_100%)] p-4 text-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-sm">
                <CheckCircle2 className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-semibold text-emerald-950">Dataset ZIP ready</div>
                <div className="mt-1 text-sm leading-6 text-emerald-900/85">
                  {status?.result?.files_generated
                    ? `${status.result.files_generated} files generated and packaged successfully.`
                    : 'Generation completed successfully.'}
                </div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-medium text-emerald-800">
              <span className="rounded-full border border-emerald-200 bg-white px-3 py-1">Job ID: {jobId}</span>
              {recipeType ? <span className="rounded-full border border-emerald-200 bg-white px-3 py-1">Recipe: {recipeType}</span> : null}
            </div>
          </div>
          {resolvedDownloadUrl ? (
            <a href={resolvedDownloadUrl} target="_blank" rel="noreferrer" className="shrink-0">
              <Button size="sm" className="gap-2 rounded-full bg-emerald-600 px-4 text-white hover:bg-emerald-700">
                <Download className="h-4 w-4" />
                Download ZIP
              </Button>
            </a>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-sky-200 bg-[linear-gradient(135deg,#eff6ff_0%,#f8fbff_100%)] p-4 text-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-sky-600 text-white shadow-sm">
          {currentStatus === 'running' ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <DatabaseZap className="h-5 w-5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-semibold text-sky-950">
                {jobName || 'Dataset generation in progress'}
              </div>
              <div className="mt-1 text-sm leading-6 text-sky-900/85">
                {status?.current_stage || 'Preparing dataset files...'}
              </div>
            </div>
            <span className="w-fit rounded-full border border-sky-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-700">
              {currentStatus}
            </span>
          </div>

          <div className="mt-4">
            <Progress value={progressPercent} className="h-2.5 bg-sky-100 [&>*]:bg-sky-600" />
          </div>

          <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-medium text-sky-800/90">
            <span className="rounded-full border border-sky-200 bg-white px-3 py-1">Job ID: {jobId}</span>
            {recipeType ? <span className="rounded-full border border-sky-200 bg-white px-3 py-1">Recipe: {recipeType}</span> : null}
            {typeof status?.files_generated === 'number' ? (
              <span className="rounded-full border border-sky-200 bg-white px-3 py-1">Files: {status.files_generated}</span>
            ) : null}
            {typeof status?.total_files_estimated === 'number' ? (
              <span className="rounded-full border border-sky-200 bg-white px-3 py-1">Estimated: {status.total_files_estimated}</span>
            ) : null}
            {status?.estimated_time_remaining ? (
              <span className="rounded-full border border-sky-200 bg-white px-3 py-1">ETA: {status.estimated_time_remaining}</span>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
