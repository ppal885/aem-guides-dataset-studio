import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Settings2 } from 'lucide-react';
import { AssistantAvatar } from './AssistantAvatar';
import { ChatMessage } from './ChatMessage';
import { StreamingMessage } from './StreamingMessage';
import { GenerationProgressCard } from './GenerationProgressCard';
import { SuggestedFollowups } from './SuggestedFollowups';
import type { ChatMessage as ChatMessageType, AgentState, AgentStateInfo, JobProgressInfo, SuggestedFollowup } from '@/api/chat';

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

interface ChatMessageListProps {
  messages: ChatMessageType[];
  streamingContent: string | null;
  generationRunId?: string | null;
  onGenerationComplete?: () => void;
  onCopyMessage?: (content: string) => void;
  /** Fills the composer when the user picks an example prompt */
  onExamplePromptSelect?: (text: string) => void;
  /** messageIndex aligns rows with GET session order after sync (needed to resolve temp-* ids). */
  onSaveUserMessage?: (messageIndex: number, messageId: string, newContent: string) => Promise<void>;
  actionDisabled?: boolean;
  onRegenerate?: () => void;
  onRetry?: () => void;
  /** Agentic state props */
  thinking?: string | null;
  agentState?: AgentState | null;
  agentStateMessage?: string | null;
  agentStateInfo?: AgentStateInfo | null;
  /** Approval gate props */
  approvalMessage?: string | null;
  approvalTools?: string[];
  /** Job progress streaming */
  jobProgress?: JobProgressInfo | null;
  /** Suggested follow-ups after assistant response */
  suggestedFollowups?: SuggestedFollowup[];
  onFollowupSelect?: (text: string) => void;
}

export function ChatMessageList({
  messages,
  streamingContent,
  generationRunId,
  onGenerationComplete,
  onCopyMessage,
  onExamplePromptSelect,
  onSaveUserMessage,
  actionDisabled,
  onRegenerate,
  onRetry,
  thinking,
  agentState,
  agentStateMessage,
  agentStateInfo,
  approvalMessage,
  approvalTools,
  jobProgress,
  suggestedFollowups,
  onFollowupSelect,
}: ChatMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const lastIdx = messages.length - 1;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto scroll-smooth bg-gradient-to-b from-slate-50/50 to-white/30">
      <div className="mx-auto flex w-full max-w-[min(100%,56rem)] flex-col gap-5 px-4 py-6 sm:px-8">
      {messages.length === 0 && !streamingContent && (
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
            <div className="mt-8 w-full max-w-lg">
              <p className="mb-2 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Suggested starters
              </p>
              <div className="flex flex-wrap justify-center gap-2 sm:justify-start">
                {EXAMPLE_PROMPTS.map((ex) => (
                  <button
                    key={ex.label}
                    type="button"
                    onClick={() => onExamplePromptSelect(ex.text)}
                    className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-left text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
                  >
                    {ex.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
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
            role={m.role}
            content={m.content || ''}
            toolResults={m.tool_results ?? undefined}
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
            showRetry={showRetry}
            onRetry={onRetry}
          />
        );
      })}
      {streamingContent !== null && (
        <StreamingMessage
          content={streamingContent}
          thinking={thinking}
          agentState={agentState}
          agentStateMessage={agentStateMessage}
          agentStateInfo={agentStateInfo}
          approvalMessage={approvalMessage}
          approvalTools={approvalTools}
          jobProgress={jobProgress}
        />
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
