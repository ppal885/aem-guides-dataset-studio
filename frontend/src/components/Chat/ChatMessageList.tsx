import { useState, useEffect, useRef, useCallback } from 'react';

import { ArrowDown } from 'lucide-react';

import { AssistantAvatar } from './AssistantAvatar';

import { ChatMessage } from './ChatMessage';

import { StreamingMessage } from './StreamingMessage';

import { GenerationProgressCard } from './GenerationProgressCard';

import type {

  AgentState,

  AgentStateInfo,

  ChatMessage as ChatMessageType,

  JobProgressInfo,

  SuggestedFollowup,

} from '@/api/chat';

import { getSuggestedPrompts } from '@/api/chat';

import { SuggestedFollowups } from './SuggestedFollowups';



const EXAMPLE_PROMPTS: { label: string; text: string }[] = [

  {

    label: 'DITA Elements',

    text: 'What is the difference between conref, conkeyref, and keyref? Show XML examples.',

  },

  {

    label: 'Conref vs keyref',

    text: 'What is the difference between conref, conkeyref, and keyref? Show XML examples.',

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



function promptLabel(text: string): string {

  const firstLine = text.split('\n')[0]?.trim() || text;

  if (firstLine.length <= 40) return firstLine;

  return `${firstLine.slice(0, 37)}…`;

}



function isErrorAssistantMessage(m: ChatMessageType): boolean {

  return (

    m.role === 'assistant' &&

    (m.id.startsWith('err-') || (m.content?.startsWith('Error:') ?? false))

  );

}



interface ChatMessageListProps {

  messages: ChatMessageType[];

  sessionId?: string;

  streamingContent: string | null;

  streamingToolResults?: Record<string, unknown> | null;

  streamingThinking?: string | null;

  streamingAgentState?: AgentState | null;

  streamingAgentStateMessage?: string | null;

  streamingAgentStateInfo?: AgentStateInfo | null;

  streamingJobProgress?: JobProgressInfo | null;

  generationRunId?: string | null;

  messagesLoading?: boolean;

  onGenerationComplete?: () => void;

  onCopyMessage?: (content: string) => void;

  onExamplePromptSelect?: (text: string) => void;

  onSaveUserMessage?: (messageIndex: number, messageId: string, newContent: string) => Promise<void>;

  actionDisabled?: boolean;

  onRegenerate?: () => void;

  onRetry?: () => void;

  suggestedFollowups?: SuggestedFollowup[];

  onFollowupSelect?: (text: string) => void;

  onQuickReply?: (text: string) => void;

}



function MessageSkeleton() {

  return (

    <div className="animate-pulse space-y-6 p-4">

      {[1, 2, 3].map((i) => (

        <div key={i} className={`flex gap-3 ${i % 2 === 0 ? 'flex-row-reverse' : ''}`}>

          <div className="h-9 w-9 shrink-0 rounded-lg bg-muted" />

          <div className="max-w-[70%] flex-1 space-y-2.5">

            <div className="h-3 w-20 rounded bg-muted" />

            <div className="h-4 w-full rounded bg-muted/80" />

            <div className="h-4 w-3/4 rounded bg-muted/60" />

            {i % 2 !== 0 && <div className="h-4 w-1/2 rounded bg-muted/40" />}

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

  streamingThinking,

  streamingAgentState,

  streamingAgentStateMessage,

  streamingAgentStateInfo,

  streamingJobProgress,

  generationRunId,

  messagesLoading,

  onGenerationComplete,

  onCopyMessage,

  onExamplePromptSelect,

  onSaveUserMessage,

  actionDisabled,

  onRegenerate,

  onRetry,

  suggestedFollowups,

  onFollowupSelect,

  onQuickReply,

}: ChatMessageListProps) {

  const endRef = useRef<HTMLDivElement>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  const stickToBottomRef = useRef(true);

  const lastIdx = messages.length - 1;

  const isEmpty = !messagesLoading && messages.length === 0 && streamingContent === null;

  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const [examplePrompts, setExamplePrompts] = useState(EXAMPLE_PROMPTS);



  useEffect(() => {

    let cancelled = false;

    void getSuggestedPrompts().then((prompts) => {

      if (cancelled || !Array.isArray(prompts) || prompts.length === 0) return;

      const fromApi = prompts.slice(0, 6).map((text) => ({

        label: promptLabel(text),

        text,

      }));

      setExamplePrompts(fromApi);

    });

    return () => {

      cancelled = true;

    };

  }, []);



  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {

    const el = scrollRef.current;

    if (!el) return;

    el.scrollTo({ top: el.scrollHeight, behavior });

  }, []);



  useEffect(() => {

    if (!stickToBottomRef.current) return;

    scrollToBottom(streamingContent !== null ? 'auto' : 'smooth');

  }, [messages, streamingContent, streamingToolResults, scrollToBottom]);



  useEffect(() => {

    const el = scrollRef.current;

    if (!el) return;

    const handleScroll = () => {

      if (messages.length === 0) {

        setShowScrollBtn(false);

        stickToBottomRef.current = true;

        return;

      }

      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;

      stickToBottomRef.current = distFromBottom < 120;

      setShowScrollBtn(distFromBottom > 200);

    };

    handleScroll();

    el.addEventListener('scroll', handleScroll, { passive: true });

    return () => el.removeEventListener('scroll', handleScroll);

  }, [messages.length]);



  const handleCopy = useCallback(

    (content: string) => {

      onCopyMessage?.(content);

    },

    [onCopyMessage]

  );



  return (

    <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-y-auto bg-background [scroll-behavior:auto]">

      {messagesLoading && messages.length > 0 && (

        <div className="pointer-events-none absolute inset-0 z-10 bg-background/45" aria-hidden />

      )}

      {showScrollBtn && messages.length > 0 && (

        <button

          type="button"

          onClick={() => {

            stickToBottomRef.current = true;

            scrollToBottom('smooth');

          }}

          className="absolute bottom-4 right-4 z-20 flex h-8 w-8 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-md transition hover:bg-muted hover:text-foreground"

          title="Scroll to bottom"

        >

          <ArrowDown className="h-4 w-4" aria-hidden />

        </button>

      )}

      <div

        className={

          isEmpty

            ? 'mx-auto flex min-h-full w-full max-w-2xl flex-col items-center justify-center px-6 py-10 text-center'

            : 'mx-auto flex w-full max-w-[min(100%,72rem)] flex-col gap-6 px-4 py-6 sm:px-6'

        }

      >

        {messagesLoading && messages.length === 0 && <MessageSkeleton />}

        {isEmpty && (

          <>

            <AssistantAvatar size="lg" className="mb-5" />

            <p className="text-base font-semibold tracking-tight text-foreground">DITA Expert</p>

            <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">

              Ask about DITA structure, AEM Guides, maps and keys, validation, or output presets.

            </p>

            {onExamplePromptSelect && (

              <div className="mt-8 w-full">

                <p className="mb-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">

                  Try one of these

                </p>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">

                  {examplePrompts.slice(0, 6).map((ex) => (

                    <button

                      key={ex.text}

                      type="button"

                      onClick={() => onExamplePromptSelect(ex.text)}

                      className="group flex flex-col items-start rounded-lg border border-border bg-card p-3 text-left transition hover:bg-muted"

                    >

                      <span className="text-xs font-semibold text-foreground">{ex.label}</span>

                      <span className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">

                        {ex.text}

                      </span>

                    </button>

                  ))}

                </div>

              </div>

            )}

          </>

        )}

        {messages.map((m, i) => {

          if (m.role !== 'user' && m.role !== 'assistant') return null;

          const showRetry = i === lastIdx && isErrorAssistantMessage(m);

          const showRegenerate =

            i === lastIdx && m.role === 'assistant' && !isErrorAssistantMessage(m) && Boolean(onRegenerate);

          return (

            <ChatMessage

              key={m.id}

              messageId={m.id}

              sessionId={sessionId}

              role={m.role}

              content={m.content || ''}

              createdAt={m.created_at}

              toolResults={m.tool_results ?? undefined}

              onCopy={m.content && onCopyMessage ? () => handleCopy(m.content!) : undefined}

              onSaveEdit={
                m.role === 'user' && onSaveUserMessage
                  ? (id, text) => onSaveUserMessage(i, id, text)
                  : undefined
              }

              actionDisabled={actionDisabled}

              showRegenerate={showRegenerate}

              onRegenerate={onRegenerate}

              showRetry={showRetry}

              onRetry={onRetry}

              onQuickReply={onQuickReply}

            />

          );

        })}

        {streamingContent !== null && (

          <StreamingMessage

            content={streamingContent}

            toolResults={streamingToolResults}

            thinking={streamingThinking}

            agentState={streamingAgentState}

            agentStateMessage={streamingAgentStateMessage}

            agentStateInfo={streamingAgentStateInfo}

            jobProgress={streamingJobProgress}

          />

        )}

        {generationRunId && (

          <div className="mt-2">

            <GenerationProgressCard runId={generationRunId} onComplete={onGenerationComplete} />

          </div>

        )}

        {suggestedFollowups && suggestedFollowups.length > 0 && onFollowupSelect && !streamingContent && (

          <SuggestedFollowups followups={suggestedFollowups} onSelect={onFollowupSelect} />

        )}



        <div ref={endRef} />

      </div>

    </div>

  );

}

