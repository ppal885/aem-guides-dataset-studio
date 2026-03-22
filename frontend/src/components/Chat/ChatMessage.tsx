import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { apiUrl } from '@/utils/api';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  toolResults?: Record<string, unknown>;
  onCopy?: () => void;
  onEdit?: () => void;
  isEditing?: boolean;
}

function getVerifiedBundleUrl(toolResults?: Record<string, unknown>): string {
  const result = toolResults?.generate_dita;
  if (!result || typeof result !== 'object') {
    return '';
  }
  const downloadUrl = String((result as Record<string, unknown>).download_url || '').trim();
  if (!downloadUrl.startsWith('/api/v1/ai/bundle/') || !downloadUrl.endsWith('/download')) {
    return '';
  }
  return apiUrl(downloadUrl);
}

function sanitizeAssistantContent(content: string, verifiedBundleUrl: string): string {
  if (!verifiedBundleUrl) {
    return content;
  }
  const placeholder = 'Use the Download DITA Bundle action below.';
  const zipUrlPattern = /\bhttps?:\/\/[^\s)]+\.zip\b/gi;
  const markdownLinkPattern = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/gi;
  return (content || '')
    .replace(markdownLinkPattern, (_match, label: string, href: string) => {
      return href === verifiedBundleUrl ? `[${label}](${href})` : `${label} (${placeholder})`;
    })
    .replace(zipUrlPattern, (href) => (href === verifiedBundleUrl ? href : placeholder));
}

export function ChatMessage({ role, content, toolResults, onCopy, onEdit, isEditing }: ChatMessageProps) {
  const isUser = role === 'user';
  const verifiedBundleUrl = getVerifiedBundleUrl(toolResults);
  const renderedContent = isUser ? content : sanitizeAssistantContent(content, verifiedBundleUrl);
  return (
    <div
      className={cn(
        'rounded-2xl border p-4 text-sm shadow-sm',
        isUser
          ? 'ml-8 border-sky-200 bg-sky-50 text-slate-900'
          : 'mr-8 border-slate-200 bg-white text-slate-800',
        isEditing &&
          (isUser
            ? 'border-sky-300 ring-2 ring-sky-100'
            : 'border-blue-200 ring-2 ring-blue-100')
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-medium opacity-80">{isUser ? 'You' : 'Assistant'}</span>
        <div className="flex items-center gap-1">
          {isUser && onEdit && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onEdit}
              title="Edit and resend"
              className={cn(
                'h-8 gap-1.5 px-2 text-xs',
                isUser ? 'text-sky-700 hover:bg-sky-100 hover:text-sky-900' : ''
              )}
            >
              <Pencil className="h-3.5 w-3.5" />
              <span>Edit</span>
            </Button>
          )}
          {onCopy && content && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onCopy}
              title="Copy"
              className={cn('h-8 px-2', isUser ? 'text-sky-700 hover:bg-sky-100 hover:text-sky-900' : '')}
            >
              <Copy className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {isEditing && isUser && (
        <div className="mb-3 rounded-xl border border-sky-200 bg-white/80 px-3 py-2 text-xs text-sky-900">
          Editing this prompt will create a new branch from this point.
        </div>
      )}
      <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{content}</div>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                const safeHref = String(href || '');
                const allowLink = !verifiedBundleUrl || safeHref === verifiedBundleUrl;
                if (!allowLink) {
                  return <span>{children} (Use the Download DITA Bundle action below.)</span>;
                }
                return (
                  <a href={safeHref} target="_blank" rel="noreferrer">
                    {children}
                  </a>
                );
              },
            }}
          >
            {renderedContent}
          </ReactMarkdown>
        )}
      </div>
      {toolResults && Object.keys(toolResults).length > 0 && (
        <div className="mt-3 space-y-2 border-t border-slate-200 pt-3">
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
      <div className="rounded bg-red-50 p-2 text-xs text-red-600">
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
              {jiraId} / {String(runId).slice(0, 8)}...
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
    <pre className="max-h-24 overflow-auto rounded bg-white/50 p-2 text-xs">
      {JSON.stringify(r, null, 2)}
    </pre>
  );
}
