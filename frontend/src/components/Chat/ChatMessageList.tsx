import { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';
import { StreamingMessage } from './StreamingMessage';
import { GenerationProgressCard } from './GenerationProgressCard';
import type { ChatMessage as ChatMessageType } from '@/api/chat';

interface ChatMessageListProps {
  messages: ChatMessageType[];
  streamingContent: string | null;
  generationRunId?: string | null;
  onGenerationComplete?: () => void;
  onCopyMessage?: (content: string) => void;
}

export function ChatMessageList({
  messages,
  streamingContent,
  generationRunId,
  onGenerationComplete,
  onCopyMessage,
}: ChatMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  return (
    <div className="flex-1 overflow-y-auto space-y-4 p-4">
      {messages.length === 0 && !streamingContent && (
        <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
          Paste Jira text, ask about DITA, or generate a dataset.
        </div>
      )}
      {messages.map((m) => (
        <ChatMessage
          key={m.id}
          role={m.role as 'user' | 'assistant'}
          content={m.content || ''}
          toolResults={m.tool_results ?? undefined}
          onCopy={
            m.content && onCopyMessage
              ? () => onCopyMessage(m.content!)
              : undefined
          }
        />
      ))}
      {streamingContent !== null && (
        <StreamingMessage content={streamingContent} />
      )}
      {generationRunId && (
        <div className="mt-2">
          <GenerationProgressCard
            runId={generationRunId}
            onComplete={onGenerationComplete}
          />
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
