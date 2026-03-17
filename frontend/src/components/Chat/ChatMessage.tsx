import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { apiUrl } from '@/utils/api';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  toolResults?: Record<string, unknown>;
  onCopy?: () => void;
}

export function ChatMessage({ role, content, toolResults, onCopy }: ChatMessageProps) {
  const isUser = role === 'user';
  return (
    <div
      className={cn(
        'rounded-lg p-4 text-sm',
        isUser ? 'bg-blue-100 text-blue-900 ml-8' : 'bg-slate-100 text-slate-800 mr-8'
      )}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-medium text-xs opacity-80">{isUser ? 'You' : 'Assistant'}</span>
        {onCopy && content && (
          <Button variant="ghost" size="sm" onClick={onCopy} title="Copy">
            <Copy className="w-4 h-4" />
          </Button>
        )}
      </div>
      <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{content}</div>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        )}
      </div>
      {toolResults && Object.keys(toolResults).length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-200 space-y-2">
          {Object.entries(toolResults).map(([name, result]) => (
            <ToolResult key={name} name={name} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolResult({ name, result }: { name: string; result: unknown }) {
  const r = result as Record<string, unknown> | null;
  if (!r) return null;
  const err = r.error as string | undefined;
  if (err) {
    return (
      <div className="text-xs text-red-600 bg-red-50 p-2 rounded">
        {name}: {err}
      </div>
    );
  }
  const downloadUrl = r.download_url as string | undefined;
  const jiraId = r.jira_id as string | undefined;
  const runId = r.run_id as string | undefined;
  if (downloadUrl && name === 'generate_dita') {
    const fullUrl = apiUrl(downloadUrl);
    return (
      <div className="flex flex-col gap-2 rounded border border-green-200 bg-green-50 p-3">
        <div className="flex items-center gap-2">
          <a
            href={fullUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
          >
            Download DITA Bundle
          </a>
          {jiraId && runId && (
            <span className="text-xs text-slate-500">
              {jiraId} / {String(runId).slice(0, 8)}…
            </span>
          )}
        </div>
        <p className="text-xs text-slate-600">
          You can refine: &quot;Add a concept topic&quot;, &quot;Make steps more detailed&quot;, etc.
        </p>
      </div>
    );
  }
  const jobId = r.job_id as string | undefined;
  if (jobId && name === 'create_job') {
    return (
      <p className="text-xs">
        Job created: <span className="font-mono">{jobId}</span>. Check Job History to download.
      </p>
    );
  }
  return (
    <pre className="text-xs bg-white/50 p-2 rounded overflow-auto max-h-24">
      {JSON.stringify(r, null, 2)}
    </pre>
  );
}
