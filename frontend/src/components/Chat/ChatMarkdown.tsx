import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/lib/utils';
import { cursorVscodeDarkTheme } from './cursorPrismTheme';
import {
  classifyInlineCode,
  highlightEvidenceCitations,
  inlineCodeClassName,
  normalizeCodeBlockText,
  repairTextEncodingArtifacts,
  resolvePrismLanguage,
  resolveSectionHeadingClass,
  containsHtmlBreakToken,
} from './chatMarkdownUtils';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  Info,
  ListChecks,
  Lightbulb,
} from 'lucide-react';

type MarkdownVariant = 'default' | 'cursor';

type CalloutTone = {
  label: string;
  pattern: RegExp;
  container: string;
  badge: string;
  iconWrap: string;
  cursorContainer: string;
  cursorAccent: string;
  Icon: typeof Info;
};

interface ChatMarkdownProps {
  content: string;
  verifiedBundleUrl?: string;
  variant?: MarkdownVariant;
}

/** Cursor-style prose wrapper — detailed colors live in index.css `.cursor-chat-prose` */
export const CURSOR_MARKDOWN_PROSE_CLASS = 'cursor-chat-prose';

/** Shared Tailwind Typography wrapper for legacy chat markdown */
export const CHAT_MARKDOWN_PROSE_CLASS =
  'prose prose-base max-w-none ' +
  'prose-headings:text-slate-800 prose-headings:font-semibold prose-headings:mt-5 prose-headings:mb-2.5 ' +
  'prose-p:my-2 prose-p:leading-[1.75] ' +
  'prose-ul:my-2.5 prose-li:my-0.5 ' +
  'prose-table:border-collapse prose-table:w-full prose-table:text-sm ' +
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
    cursorContainer: 'border-l-sky-500/70 bg-sky-500/[0.06]',
    cursorAccent: 'text-sky-600 dark:text-sky-400',
    Icon: CheckCircle2,
  },
  {
    label: 'Note',
    pattern: /^(note|context|background):\s*/i,
    container: 'border-slate-200 bg-[linear-gradient(135deg,#f8fafc_0%,#ffffff_100%)] text-slate-900',
    badge: 'border-slate-200 bg-white text-slate-700',
    iconWrap: 'bg-slate-800 text-white',
    cursorContainer: 'border-l-border bg-muted/35',
    cursorAccent: 'text-muted-foreground',
    Icon: Info,
  },
  {
    label: 'Tip',
    pattern: /^(tip|best practice|recommendation):\s*/i,
    container: 'border-emerald-200 bg-[linear-gradient(135deg,#ecfdf5_0%,#f7fffb_100%)] text-emerald-950',
    badge: 'border-emerald-200 bg-white text-emerald-700',
    iconWrap: 'bg-emerald-600 text-white',
    cursorContainer: 'border-l-emerald-500/70 bg-emerald-500/[0.06]',
    cursorAccent: 'text-emerald-600 dark:text-emerald-400',
    Icon: Lightbulb,
  },
  {
    label: 'Warning',
    pattern: /^(warning|caution|risk|avoid):\s*/i,
    container: 'border-amber-200 bg-[linear-gradient(135deg,#fffbeb_0%,#fffdf8_100%)] text-amber-950',
    badge: 'border-amber-200 bg-white text-amber-700',
    iconWrap: 'bg-amber-600 text-white',
    cursorContainer: 'border-l-amber-500/75 bg-amber-500/[0.07]',
    cursorAccent: 'text-amber-600 dark:text-amber-400',
    Icon: AlertTriangle,
  },
  {
    label: 'Expected Result',
    pattern: /^(expected result|expected outcome|what you should see|output):\s*/i,
    container: 'border-emerald-200 bg-[linear-gradient(135deg,#ecfdf5_0%,#f7fffb_100%)] text-emerald-950',
    badge: 'border-emerald-200 bg-white text-emerald-700',
    iconWrap: 'bg-emerald-600 text-white',
    cursorContainer: 'border-l-emerald-500 bg-emerald-500/10',
    cursorAccent: 'text-emerald-600 dark:text-emerald-400',
    Icon: CheckCircle2,
  },
  {
    label: 'Common Mistakes',
    pattern: /^(common mistakes?|pitfalls?|watch out|gotchas?):\s*/i,
    container: 'border-amber-200 bg-[linear-gradient(135deg,#fffbeb_0%,#fffdf8_100%)] text-amber-950',
    badge: 'border-amber-200 bg-white text-amber-700',
    iconWrap: 'bg-amber-600 text-white',
    cursorContainer: 'border-l-orange-500 bg-orange-500/10',
    cursorAccent: 'text-orange-600 dark:text-orange-400',
    Icon: AlertTriangle,
  },
  {
    label: 'Sources',
    pattern: /^(sources?|references?|limits of evidence|evidence):\s*/i,
    container: 'border-violet-200 bg-[linear-gradient(135deg,#f5f3ff_0%,#faf8ff_100%)] text-violet-950',
    badge: 'border-violet-200 bg-white text-violet-700',
    iconWrap: 'bg-violet-600 text-white',
    cursorContainer: 'border-l-violet-500 bg-violet-500/10',
    cursorAccent: 'text-violet-600 dark:text-violet-400',
    Icon: Info,
  },
  {
    label: 'Next Steps',
    pattern: /^(next steps?|action items?):\s*/i,
    container: 'border-violet-200 bg-[linear-gradient(135deg,#f5f3ff_0%,#faf8ff_100%)] text-violet-950',
    badge: 'border-violet-200 bg-white text-violet-700',
    iconWrap: 'bg-violet-600 text-white',
    cursorContainer: 'border-l-violet-500/70 bg-violet-500/[0.06]',
    cursorAccent: 'text-violet-600 dark:text-violet-400',
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

const HTML_BREAK_RE = /<\s*br\s*\/?>/gi;

/** Render literal `<br>` tokens inside table cells as real line breaks. */
function expandHtmlBreaksInNodes(node: React.ReactNode): React.ReactNode {
  if (node == null || typeof node === 'boolean') {
    return node;
  }
  if (typeof node === 'string') {
    if (!containsHtmlBreakToken(node)) {
      return node;
    }
    const parts = node.split(HTML_BREAK_RE);
    return parts.map((part, index) => (
      <React.Fragment key={`br-${index}`}>
        {index > 0 ? <br /> : null}
        {part}
      </React.Fragment>
    ));
  }
  if (typeof node === 'number') {
    return node;
  }
  if (Array.isArray(node)) {
    return node.map((child, index) => (
      <React.Fragment key={`cell-${index}`}>{expandHtmlBreaksInNodes(child)}</React.Fragment>
    ));
  }
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    const nextChildren = expandHtmlBreaksInNodes(node.props.children);
    return React.cloneElement(node, undefined, nextChildren);
  }
  return node;
}

function TableCell({ as: Tag, children }: { as: 'td' | 'th'; children: React.ReactNode }) {
  return <Tag className="cursor-table-cell">{expandHtmlBreaksInNodes(children)}</Tag>;
}

function CodeBlock({
  className,
  children,
  variant = 'default',
}: {
  className?: string;
  children: string;
  variant?: MarkdownVariant;
}) {
  const [copied, setCopied] = useState(false);
  const rawLang = className?.replace('language-', '') || 'text';
  const lang = resolvePrismLanguage(rawLang);
  const displayLang = rawLang || 'text';
  const code = normalizeCodeBlockText(children, className);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (variant === 'cursor') {
    const isMarkup = lang === 'markup' || ['xml', 'dita', 'ditamap', 'html'].includes(displayLang.toLowerCase());
    return (
      <div className={cn('chat-code-block my-3', isMarkup && 'chat-code-block-xml')}>
        <div className="chat-code-block-header">
          <span className={cn('font-mono text-[11px] uppercase tracking-wide', isMarkup && 'text-sky-400')}>
            {displayLang}
          </span>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 transition-colors hover:text-foreground"
            title="Copy code"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                Copy
              </>
            )}
          </button>
        </div>
        <SyntaxHighlighter
          language={lang}
          style={isMarkup ? cursorVscodeDarkTheme : oneDark}
          customStyle={{
            margin: 0,
            borderRadius: 0,
            fontSize: '0.78rem',
            lineHeight: 1.55,
            padding: '0.85rem 1rem',
            background: '#1e1e1e',
          }}
          wrapLongLines
        >
          {code}
        </SyntaxHighlighter>
      </div>
    );
  }

  return (
    <div className="relative group my-3 rounded-lg overflow-hidden border border-slate-700/30">
      <div className="flex items-center justify-between px-4 py-1.5 bg-slate-800 text-xs text-slate-400 border-b border-slate-700/40">
        <span className="font-mono">{displayLang}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition-colors"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />{' '}
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" /> Copy
            </>
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
  variant = 'default',
}: {
  tone: CalloutTone;
  children: React.ReactNode;
  variant?: MarkdownVariant;
}) {
  if (variant === 'cursor') {
    const Icon = tone.Icon;
    return (
      <div className={cn('cursor-callout my-3 border-l-[3px] rounded-r-md px-3.5 py-2.5', tone.cursorContainer)}>
        <div className={cn('mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider', tone.cursorAccent)}>
          <Icon className="h-3 w-3 shrink-0" aria-hidden />
          {tone.label}
        </div>
        <div className="cursor-callout-body">{children}</div>
      </div>
    );
  }

  const Icon = tone.Icon;

  return (
    <div className={`my-4 rounded-2xl border p-4 ${tone.container}`}>
      <div className="flex items-start gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${tone.iconWrap}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div
            className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${tone.badge}`}
          >
            {tone.label}
          </div>
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </div>
  );
}

export function ChatMarkdown({ content, verifiedBundleUrl = '', variant = 'default' }: ChatMarkdownProps) {
  const isCursor = variant === 'cursor';
  let normalizedContent = repairTextEncodingArtifacts(content || '\u00A0');
  if (isCursor) {
    normalizedContent = highlightEvidenceCitations(normalizedContent);
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          const safeHref = String(href || '');
          const allowLink = !verifiedBundleUrl || safeHref === verifiedBundleUrl;
          if (!allowLink) {
            return (
              <span className={isCursor ? 'text-foreground/85' : 'text-slate-700'}>
                {children} (Use the Download DITA Bundle action below.)
              </span>
            );
          }
          return (
            <a
              href={safeHref}
              target="_blank"
              rel="noreferrer"
              className={isCursor ? 'cursor-prose-link' : 'font-semibold text-teal-700 no-underline hover:underline'}
            >
              {children}
            </a>
          );
        },
        table: ({ children }) =>
          isCursor ? (
            <div className="cursor-prose-table-wrap">
              <table>{children}</table>
            </div>
          ) : (
            <div className="my-4 overflow-x-auto rounded-xl border border-slate-200/80 shadow-sm">
              <table className="min-w-full divide-y divide-slate-200">{children}</table>
            </div>
          ),
        thead: ({ children }) =>
          isCursor ? <thead>{children}</thead> : <thead className="bg-slate-50/80">{children}</thead>,
        tr: ({ children }) =>
          isCursor ? <tr>{children}</tr> : <tr className="transition-colors hover:bg-slate-50/50">{children}</tr>,
        th: ({ children }) =>
          isCursor ? (
            <TableCell as="th">{children}</TableCell>
          ) : (
            <th className="chat-table-cell">{expandHtmlBreaksInNodes(children)}</th>
          ),
        td: ({ children }) =>
          isCursor ? (
            <TableCell as="td">{children}</TableCell>
          ) : (
            <td className="chat-table-cell">{expandHtmlBreaksInNodes(children)}</td>
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
            const kind = isCursor ? classifyInlineCode(text) : 'default';
            return (
              <code className={isCursor ? inlineCodeClassName(kind) : undefined}>{children}</code>
            );
          }
          return (
            <CodeBlock className={className} variant={variant}>
              {text}
            </CodeBlock>
          );
        },
        h1: ({ children }) => {
          if (!isCursor) return <h1>{children}</h1>;
          const section = resolveSectionHeadingClass(getTextContent(children));
          return <h1 className={cn('cursor-prose-h1', section)}>{children}</h1>;
        },
        h2: ({ children }) => {
          if (!isCursor) {
            return (
              <h2 className="flex items-center gap-2.5 mt-6 mb-3 text-base font-bold text-slate-800">
                <span className="inline-block w-1 h-5 rounded-full bg-gradient-to-b from-teal-600 to-teal-500" />
                <span>{children}</span>
              </h2>
            );
          }
          const section = resolveSectionHeadingClass(getTextContent(children));
          return <h2 className={cn('cursor-prose-h2', section)}>{children}</h2>;
        },
        h3: ({ children }) => {
          if (!isCursor) {
            return (
              <h3 className="flex items-center gap-2 mt-5 mb-2 text-[0.9375rem] font-semibold text-slate-700">
                <span className="inline-block w-0.5 h-4 rounded-full bg-gradient-to-b from-slate-400 to-slate-300" />
                <span>{children}</span>
              </h3>
            );
          }
          const section = resolveSectionHeadingClass(getTextContent(children));
          return <h3 className={cn('cursor-prose-h3', section)}>{children}</h3>;
        },
        h4: ({ children }) => (isCursor ? <h4 className="cursor-prose-h4">{children}</h4> : <h4>{children}</h4>),
        p: ({ children }) => {
          const text = getTextContent(children);
          const tone = findCalloutTone(text);
          if (!tone) {
            return isCursor ? <p className="cursor-prose-p">{children}</p> : <p>{children}</p>;
          }
          return (
            <CalloutCard tone={tone} variant={variant}>
              {stripLeadingPattern(children, tone.pattern)}
            </CalloutCard>
          );
        },
        blockquote: ({ children }) => {
          const text = getTextContent(children);
          const tone = findCalloutTone(text) || CALLOUT_TONES[1];
          if (isCursor) {
            return (
              <blockquote className="cursor-prose-blockquote">
                {stripLeadingPattern(children, tone.pattern)}
              </blockquote>
            );
          }
          return (
            <CalloutCard tone={tone} variant={variant}>
              {stripLeadingPattern(children, tone.pattern)}
            </CalloutCard>
          );
        },
        hr: () => (isCursor ? <hr className="cursor-prose-hr" /> : <hr />),
        strong: ({ children }) => {
          if (!isCursor) return <strong>{children}</strong>;
          const text = getTextContent(children);
          const isLabel = /:\s*$/.test(text.trim());
          return (
            <strong className={cn('cursor-prose-strong', isLabel && 'cursor-prose-label')}>{children}</strong>
          );
        },
        em: ({ children }) => (isCursor ? <em className="cursor-prose-em">{children}</em> : <em>{children}</em>),
        ol: ({ children }) => (
          <ol className={isCursor ? 'cursor-step-list' : 'chat-step-list'}>{children}</ol>
        ),
        ul: ({ children }) => (
          <ul className={isCursor ? 'cursor-bullet-list' : 'chat-bullet-list'}>{children}</ul>
        ),
        li: ({ children }) => (isCursor ? <li className="cursor-prose-li">{children}</li> : <li>{children}</li>),
      }}
    >
      {normalizedContent}
    </ReactMarkdown>
  );
}
