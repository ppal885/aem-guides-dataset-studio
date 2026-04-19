import { cn } from '@/lib/utils';
import type { AgentState, AgentStateInfo, JobProgressInfo } from '@/api/chat';
import { AssistantAvatar } from './AssistantAvatar';
import { ChatMarkdown, CHAT_MARKDOWN_PROSE_CLASS } from './ChatMarkdown';
import { ToolResult } from './ChatMessage';

interface StreamingMessageProps {
  content: string;
  toolResults?: Record<string, unknown> | null;
  className?: string;
  thinking?: string | null;
  agentState?: AgentState | null;
  agentStateMessage?: string | null;
  agentStateInfo?: AgentStateInfo | null;
  approvalMessage?: string | null;
  approvalTools?: string[];
  jobProgress?: JobProgressInfo | null;
}

export function StreamingMessage({ content, toolResults, className }: StreamingMessageProps) {
  const showCursor = content.length > 0;

  return (
    <div className={cn('flex animate-fadeIn gap-3.5', className)}>
      <AssistantAvatar />
      <div className="min-w-0 w-full max-w-full flex-1 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Assistant</span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-slate-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-slate-600" />
            </span>
            Generating
          </span>
        </div>
        <AgentStateIndicator
          thinking={thinking}
          state={agentState}
          stateMessage={agentStateMessage}
          stateInfo={agentStateInfo}
          className="mb-2"
        />
        {approvalMessage && (
          <ApprovalGate
            message={approvalMessage}
            tools={approvalTools ?? []}
            className="mb-2"
          />
        )}
        {jobProgress && (
          <div className="mb-2">
            <DatasetJobStatusCard
              jobId={jobProgress.jobId}
              initialStatus={jobProgress.status}
              jobName={jobProgress.name}
              recipeType={jobProgress.recipeType}
              downloadUrl={jobProgress.downloadUrl}
            />
          </div>
        )}
        <div className="text-[0.9375rem] leading-relaxed text-slate-800" aria-live="polite" aria-busy="true">
          <div className={CHAT_MARKDOWN_PROSE_CLASS}>
            <ChatMarkdown content={content} />
          </div>
          {showCursor && (
            <span
              className="ml-0.5 inline-block h-[1.05em] w-0.5 translate-y-0.5 animate-pulse rounded-sm bg-slate-700 align-middle"
              aria-hidden
            />
          )}
        </div>
        {toolResults && Object.keys(toolResults).length > 0 && (
          <div className="mt-3 space-y-2 border-t border-slate-200/70 pt-3">
            {Object.entries(toolResults).map(([name, result]) => (
              <ToolResult key={name} name={name} result={result} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
