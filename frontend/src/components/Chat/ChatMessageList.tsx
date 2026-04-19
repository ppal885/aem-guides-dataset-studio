import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Settings2, ArrowDown } from 'lucide-react';
import { AssistantAvatar } from './AssistantAvatar';
import { ChatMessage } from './ChatMessage';
import { StreamingMessage } from './StreamingMessage';
import { GenerationProgressCard } from './GenerationProgressCard';
import type { ChatMessage as ChatMessageType, ChatDitaGenerationOptions } from '@/api/chat';
import type { AuthoringVisualContext } from '@/components/Authoring/AuthoringGenerationSplitReview';

const EXAMPLE_PROMPTS: { label: string; text: string }[] = [
  {
    label: 'DITA Elements',
    text: 'What is the difference between conref, conkeyref, and keyref? Show XML examples.',
  },
  {
    label: 'Generate DITA',
    text: 'Generate a task topic for configuring PDF output in AEM Guides',
  },
  {
    label: 'Native PDF',
    text: 'How do I customize Native PDF templates (page layouts, CSS, headers/footers) in AEM Guides?',
  },
  {
    label: 'Map & Chunking',
    text: 'Explain DITA map cascading and chunk attributes with examples',
  },
  {
    label: 'Output Presets',
    text: 'What are the 7 output preset types in AEM Guides and when to use each?',
  },
  {
    label: 'Tables',
    text: 'What is the difference between choicetable, simpletable, and table in DITA?',
  },
  {
    label: 'Translation',
    text: 'How does the translation workflow work in AEM Guides?',
  },
  {
    label: 'Content Reuse',
    text: 'When should I use conref vs conkeyref vs keyref vs content snippets in AEM Guides?',
  },
  {
    label: 'Baselines',
    text: 'Explain the difference between label-based and date-based baselines in AEM Guides',
  },
  {
    label: 'Search Jira',
    text: 'Search Jira for open issues about map validation or reltable in our documentation project.',
  },
];

function isErrorAssistantMessage(m: ChatMessageType): boolean {
  return (
    m.role === 'assistant' &&
    (m.id.startsWith('err-') || (m.content?.startsWith('Error:') ?? false))
  );
}

function indexOfLatestAuthoringResult(messages: ChatMessageType[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== 'assistant' || !m.tool_results) continue;
    const raw = m.tool_results.generate_dita_from_attachments;
    if (raw != null && typeof raw === 'object' && !('error' in raw && (raw as { error?: string }).error)) {
      return i;
    }
  }
  return -1;
}

interface ChatMessageListProps {
  messages: ChatMessageType[];
  sessionId?: string;
  streamingContent: string | null;
  streamingToolResults?: Record<string, unknown> | null;
  generationRunId?: string | null;
  messagesLoading?: boolean;
  onGenerationComplete?: () => void;
  onCopyMessage?: (content: string) => void;
  /** Fills the composer when the user picks an example prompt */
  onExamplePromptSelect?: (text: string) => void;
  /** messageIndex aligns rows with GET session order after sync (needed to resolve temp-* ids). */
  onSaveUserMessage?: (messageIndex: number, messageId: string, newContent: string) => Promise<void>;
  actionDisabled?: boolean;
  onRegenerate?: () => void;
  /** Screenshot authoring result panel: regenerate with optional generation option overrides. */
  onRegenerateAuthoring?: (options: ChatDitaGenerationOptions) => void;
  onRetry?: () => void;
  /** Screenshot thumbnail + filenames + options for the latest authoring result row only. */
  authoringVisualContext?: AuthoringVisualContext | null;
}

/** Skeleton placeholder while messages are loading. */
function MessageSkeleton() {
  return (
    <div className="animate-pulse space-y-6 p-4">
      {[1, 2, 3].map(i => (
        <div key={i} className={`flex gap-3 ${i % 2 === 0 ? 'flex-row-reverse' : ''}`}>
          <div className="w-9 h-9 rounded-lg bg-slate-200 shrink-0" />
          <div className="space-y-2.5 flex-1 max-w-[70%]">
            <div className="h-3 bg-slate-200 rounded w-20" />
            <div className="h-4 bg-slate-200/80 rounded w-full" />
            <div className="h-4 bg-slate-200/60 rounded w-3/4" />
            {i % 2 !== 0 && <div className="h-4 bg-slate-200/40 rounded w-1/2" />}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ChatMessageList({
  messages,
  sessionId,
  streamingContent,
  streamingToolResults,
  generationRunId,
  messagesLoading,
  onGenerationComplete,
  onCopyMessage,
  onExamplePromptSelect,
  onSaveUserMessage,
  actionDisabled,
  onRegenerate,
  onRegenerateAuthoring,
  onRetry,
  authoringVisualContext,
}: ChatMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastIdx = messages.length - 1;
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollBtn(distFromBottom > 200);
    };
    el.addEventListener('scroll', handleScroll);
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-y-auto scroll-smooth bg-slate-50/70">
      {showScrollBtn && (
        <button
          type="button"
          onClick={() => endRef.current?.scrollIntoView({ behavior: 'smooth' })}
          className="absolute bottom-20 right-6 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white shadow-lg transition-all hover:bg-slate-50 hover:shadow-xl"
          title="Scroll to bottom"
        >
          <ArrowDown className="h-4 w-4 text-slate-600" />
        </button>
      )}
      <div className="mx-auto flex w-full max-w-[min(100%,72rem)] flex-col gap-6 px-4 py-6 sm:px-6">
      {messagesLoading && messages.length === 0 && <MessageSkeleton />}
      {!messagesLoading && messages.length === 0 && !streamingContent && (
        <div className="flex min-h-[12rem] flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
          <AssistantAvatar size="lg" className="mb-4 opacity-90" />
          <p className="text-sm font-semibold text-slate-900">This conversation is empty</p>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-600">
            Ask about DITA structure, AEM Guides authoring, maps and keys, or paste Jira text for bundle generation.
            You can also start dataset recipes, search Jira, and review pasted XML. Answers use your indexed docs plus
            tools when relevant. Turn on <span className="font-medium text-slate-700">Human precision</span> for shorter replies.
          </p>
          <p className="mt-4 text-xs text-slate-500">
            <Link
              to="/settings"
              className="inline-flex items-center gap-1 font-medium text-slate-700 underline-offset-4 hover:text-slate-900 hover:underline"
            >
              <Settings2 className="h-3.5 w-3.5" aria-hidden />
              Configure RAG and Tavily in Settings
            </Link>
          </p>
          {onExamplePromptSelect && (
            <div className="mt-8 w-full max-w-xl">
              <p className="mb-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Try one of these
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {EXAMPLE_PROMPTS.map((ex) => (
                  <button
                    key={ex.label}
                    type="button"
                    onClick={() => onExamplePromptSelect(ex.text)}
                    className="group flex flex-col items-start rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:border-slate-300 hover:bg-slate-50 hover:shadow-md"
                  >
                    <span className="text-xs font-semibold text-slate-800 group-hover:text-teal-700 transition-colors">{ex.label}</span>
                    <span className="mt-1 text-[11px] leading-relaxed text-slate-500 line-clamp-2">{ex.text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {(() => {
        const latestAuthoringIdx = indexOfLatestAuthoringResult(messages);
        return messages.map((m, i) => {
        if (m.role !== 'user' && m.role !== 'assistant') return null;
        const showRetry = i === lastIdx && isErrorAssistantMessage(m);
        const showRegenerate =
          i === lastIdx && m.role === 'assistant' && !isErrorAssistantMessage(m) && Boolean(onRegenerate);
        const authoringCtxForRow =
          m.role === 'assistant' && i === latestAuthoringIdx ? authoringVisualContext : undefined;
        return (
          <ChatMessage
            key={m.id}
            messageId={m.id}
            sessionId={sessionId}
            role={m.role}
            content={m.content || ''}
            createdAt={m.created_at}
            toolResults={m.tool_results ?? undefined}
            authoringVisualContext={authoringCtxForRow}
            onCopy={
              m.content && onCopyMessage ? () => onCopyMessage(m.content!) : undefined
            }
            onSaveEdit={
              m.role === 'user' && onSaveUserMessage
                ? (id, text) => onSaveUserMessage(i, id, text)
                : undefined
            }
            actionDisabled={actionDisabled}
            showRegenerate={showRegenerate}
            onRegenerate={onRegenerate}
            onRegenerateAuthoring={
              showRegenerate && onRegenerateAuthoring ? onRegenerateAuthoring : undefined
            }
            showRetry={showRetry}
            onRetry={onRetry}
          />
        );
      });
      })()}
      {streamingContent !== null && (
        <StreamingMessage content={streamingContent} toolResults={streamingToolResults} />
      )}
      {generationRunId && (
        <div className="mt-2">
          <GenerationProgressCard
            runId={generationRunId}
            onComplete={onGenerationComplete}
          />
        </div>
      )}
      {suggestedFollowups && suggestedFollowups.length > 0 && onFollowupSelect && !streamingContent && (
        <SuggestedFollowups
          followups={suggestedFollowups}
          onSelect={onFollowupSelect}
          className="mt-1"
        />
      )}
      <div ref={endRef} />
      </div>
    </div>
  );
}
