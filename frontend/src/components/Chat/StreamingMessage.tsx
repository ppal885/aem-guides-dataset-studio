import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface StreamingMessageProps {
  content: string;
  className?: string;
}

export function StreamingMessage({ content, className }: StreamingMessageProps) {
  return (
    <div
      className={cn(
        'mr-8 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-800 shadow-sm',
        className
      )}
    >
      <div className="font-medium text-xs opacity-80 mb-2">Assistant</div>
      <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || '\u00A0'}</ReactMarkdown>
      </div>
    </div>
  );
}
