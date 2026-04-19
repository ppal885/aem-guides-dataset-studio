import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/lib/utils';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  Info,
  ListChecks,
  Lightbulb,
} from 'lucide-react';

type CalloutTone = {
  label: string;
  pattern: RegExp;
  container: string;
  badge: string;
  iconWrap: string;
  Icon: typeof Info;
};

interface ChatMarkdownProps {
  content: string;
  verifiedBundleUrl?: string;
}

/** Shared Tailwind Typography wrapper for chat markdown (ChatMessage + StreamingMessage). */
export const CHAT_MARKDOWN_PROSE_CLASS =
  'prose prose-sm max-w-none ' +
  'prose-headings:text-slate-800 prose-headings:font-semibold prose-headings:mt-5 prose-headings:mb-2.5 ' +
  'prose-p:my-2 prose-p:leading-[1.75] ' +
  'prose-ul:my-2.5 prose-li:my-0.5 ' +
  'prose-table:border-collapse prose-table:w-full prose-table:text-[13px] ' +
  'prose-th:bg-slate-50 prose-th:border prose-th:border-slate-200 prose-th:px-3 prose-th:py-2.5 prose-th:text-left prose-th:font-semibold prose-th:text-slate-700 ' +
  'prose-td:border prose-td:border-slate-100 prose-td:px-3 prose-td:py-2 prose-td:text-slate-600 ' +
  'prose-code:text-slate-800 prose-code:text-[0.8125rem] prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:font-mono prose-code:font-normal ' +
  'prose-pre:bg-[#1e293b] prose-pre:text-slate-200 prose-pre:rounded-xl prose-pre:p-4 prose-pre:text-[0.8125rem] prose-pre:overflow-x-auto prose-pre:shadow-inner ' +
  'prose-strong:text-slate-900 prose-strong:font-semibold ' +
  'prose-a:text-teal-700 prose-a:no-underline hover:prose-a:underline ' +
  'prose-hr:border-slate-200 prose-hr:my-6';

const CALLOUT_TONES: CalloutTone[] = [
  {
    label: 'Summary',
    pattern: /^(summary|overview|key takeaways?|takeaway):\s*/i,
    container: 'border-teal-200 bg-[linear-gradient(135deg,#f0fdfa_0%,#f8fafc_100%)] text-teal-950',
    badge: 'border-teal-200 bg-white text-teal-800',
    iconWrap: 'bg-teal-600 text-white',
    Icon: CheckCircle2,
  },
  {
    label: 'Note',
    pattern: /^(note|context|background):\s*/i,
    container: 'border-slate-200 bg-[linear-gradient(135deg,#f8fafc_0%,#ffffff_100%)] text-slate-900',
    badge: 'border-slate-200 bg-white text-slate-700',
    iconWrap: 'bg-slate-800 text-white',
    Icon: Info,
  },
  {
    label: 'Tip',
    pattern: /^(tip|best practice|recommendation):\s*/i,
    container: 'border-emerald-200 bg-[linear-gradient(135deg,#ecfdf5_0%,#f7fffb_100%)] text-emerald-950',
    badge: 'border-emerald-200 bg-white text-emerald-700',
    iconWrap: 'bg-emerald-600 text-white',
    Icon: Lightbulb,
  },
  {
    label: 'Warning',
    pattern: /^(warning|caution|risk|avoid):\s*/i,
    container: 'border-amber-200 bg-[linear-gradient(135deg,#fffbeb_0%,#fffdf8_100%)] text-amber-950',
    badge: 'border-amber-200 bg-white text-amber-700',
    iconWrap: 'bg-amber-600 text-white',
    Icon: AlertTriangle,
  },
  {
    label: 'Next Steps',
    pattern: /^(next steps?|action items?):\s*/i,
    container: 'border-violet-200 bg-[linear-gradient(135deg,#f5f3ff_0%,#faf8ff_100%)] text-violet-950',
    badge: 'border-violet-200 bg-white text-violet-700',
    iconWrap: 'bg-violet-600 text-white',
    Icon: ListChecks,
  },
];

function getTextContent(node: React.ReactNode): string {
  if (node == null || typeof node === 'boolean') {
    return '';
  }
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(getTextContent).join('');
  }
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return getTextContent(node.props.children);
  }
  return '';
}

function findCalloutTone(text: string): CalloutTone | null {
  const trimmed = text.trim();
  for (const tone of CALLOUT_TONES) {
    if (tone.pattern.test(trimmed)) {
      return tone;
    }
  }
  return null;
}

function stripLeadingPattern(children: React.ReactNode, pattern: RegExp): React.ReactNode {
  let removed = false;

  const walk = (value: React.ReactNode): React.ReactNode => {
    if (removed || value == null || typeof value === 'boolean') {
      return value;
    }
    if (typeof value === 'string') {
      const next = value.replace(pattern, '');
      if (next !== value) {
        removed = true;
        return next;
      }
      return value;
    }
    if (typeof value === 'number') {
      return value;
    }
    if (Array.isArray(value)) {
      return value.map((item) => walk(item));
    }
    if (React.isValidElement<{ children?: React.ReactNode }>(value)) {
      const nextChildren = walk(value.props.children);
      return React.cloneElement(value, undefined, nextChildren);
    }
    return value;
  };

  return walk(children);
}

/** Fenced code block with syntax highlighting and one-click copy. */
function CodeBlock({ className, children }: { className?: string; children: string }) {
  const [copied, setCopied] = useState(false);
  const lang = className?.replace('language-', '') || 'text';
  const code = String(children).replace(/\n$/, '');

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-3 rounded-lg overflow-hidden border border-slate-700/30">
      <div className="flex items-center justify-between px-4 py-1.5 bg-slate-800 text-xs text-slate-400 border-b border-slate-700/40">
        <span className="font-mono">{lang}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition-colors"
          title="Copy code"
        >
          {copied ? (
            <><Check className="w-3.5 h-3.5 text-emerald-400" /> <span className="text-emerald-400">Copied</span></>
          ) : (
            <><Copy className="w-3.5 h-3.5" /> Copy</>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={lang}
        style={oneDark}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.8125rem' }}
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

function CalloutCard({
  tone,
  children,
}: {
  tone: CalloutTone;
  children: React.ReactNode;
}) {
  const Icon = tone.Icon;

  return (
    <div className={`my-4 rounded-2xl border p-4 ${tone.container}`}>
      <div className="flex items-start gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${tone.iconWrap}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${tone.badge}`}>
            {tone.label}
          </div>
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </div>
  );
}

export function ChatMarkdown({ content, verifiedBundleUrl = '' }: ChatMarkdownProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          const safeHref = String(href || '');
          const allowLink = !verifiedBundleUrl || safeHref === verifiedBundleUrl;
          if (!allowLink) {
            return (
              <span className="text-slate-700">
                {children} (Use the Download DITA Bundle action below.)
              </span>
            );
          }
          return (
            <a
              href={safeHref}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-teal-700 no-underline hover:underline"
            >
              {children}
            </a>
          );
        },
        table: ({ children }) => (
          <div className="my-4 overflow-x-auto rounded-xl border border-slate-200/80 shadow-sm">
            <table className="min-w-full divide-y divide-slate-200">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-slate-50/80">{children}</thead>
        ),
        tr: ({ children }) => (
          <tr className="transition-colors hover:bg-slate-50/50">{children}</tr>
        ),
        pre: ({ children }) => <>{children}</>,
        code: ({ className, children, ...rest }) => {
          const inlineFlag = (rest as { inline?: boolean }).inline;
          const hasLanguage = Boolean(className && /\blanguage-/.test(className));
          const text = String(children).replace(/\n$/, '');
          const multiline = text.includes('\n');
          const isBlock =
            inlineFlag === false || hasLanguage || (inlineFlag === undefined && multiline);
          if (!isBlock) {
            return (
              <code className="break-words rounded-md border border-slate-200/80 bg-slate-100/80 px-1.5 py-0.5 font-mono text-[0.8125rem] font-normal text-slate-800">
                {children}
              </code>
            );
          }
          return <CodeBlock className={className}>{text}</CodeBlock>;
        },
        h2: ({ children }) => (
          <h2 className="flex items-center gap-2.5 mt-6 mb-3 text-base font-bold text-slate-800">
            <span className="inline-block w-1 h-5 rounded-full bg-gradient-to-b from-teal-600 to-teal-500" />
            <span>{children}</span>
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="flex items-center gap-2 mt-5 mb-2 text-[0.9375rem] font-semibold text-slate-700">
            <span className="inline-block w-0.5 h-4 rounded-full bg-gradient-to-b from-slate-400 to-slate-300" />
            <span>{children}</span>
          </h3>
        ),
        p: ({ children }) => {
          const text = getTextContent(children);
          const tone = findCalloutTone(text);
          if (!tone) {
            return <p>{children}</p>;
          }
          return <CalloutCard tone={tone}>{stripLeadingPattern(children, tone.pattern)}</CalloutCard>;
        },
        blockquote: ({ children }) => {
          const text = getTextContent(children);
          const tone = findCalloutTone(text) || CALLOUT_TONES[1];
          return <CalloutCard tone={tone}>{stripLeadingPattern(children, tone.pattern)}</CalloutCard>;
        },
        ol: ({ children }) => <ol className="chat-step-list">{children}</ol>,
        ul: ({ children }) => <ul className="chat-bullet-list">{children}</ul>,
      }}
    >
      {content || '\u00A0'}
    </ReactMarkdown>
  );
}
