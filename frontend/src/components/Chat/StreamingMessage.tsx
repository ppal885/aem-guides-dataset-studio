import { cn } from '@/lib/utils';
import type { AgentState, AgentStateInfo, JobProgressInfo } from '@/api/chat';
import { AssistantAvatar } from './AssistantAvatar';
import { ToolResult } from './ChatMessage';
import { AgentStateIndicator } from './AgentStateIndicator';
import { ApprovalGate } from './ApprovalGate';
import { DatasetJobStatusCard } from './DatasetJobStatusCard';
import { sortToolResultEntries } from './toolResultOrder';

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

export function StreamingMessage({
  content,
  toolResults,
  className,
  thinking,
  agentState,
  agentStateMessage,
  agentStateInfo,
  approvalMessage,
  approvalTools,
  jobProgress,
}: StreamingMessageProps) {
  const showCursor = content.length > 0;
  const showStatus = Boolean(thinking || agentState || jobProgress || approvalMessage);
  const sortedToolEntries = toolResults ? sortToolResultEntries(Object.entries(toolResults)) : [];

  return (
    <div className={cn('flex animate-fadeIn gap-3.5', className)}>
      <AssistantAvatar />
      <div className="min-w-0 w-full max-w-full flex-1 rounded-xl border border-border bg-card px-5 py-3.5 shadow-sm">
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-border/80 pb-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-teal-600 dark:text-teal-400">
            Assistant
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-muted-foreground/40 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-muted-foreground" />
            </span>
            Generating
          </span>
        </div>
        {showStatus && (
          <>
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
          </>
        )}
        {(showCursor || !showStatus) && (
          <div className="text-[0.9375rem] leading-relaxed text-foreground" aria-live="polite" aria-busy="true">
            {showCursor ? (
              <div className="whitespace-pre-wrap break-words">{content}</div>
            ) : (
              <p className="text-sm text-muted-foreground">Working on your request…</p>
            )}
            {showCursor && (
              <span
                className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-foreground/70 align-[-2px]"
                aria-hidden
              />
            )}
          </div>
        )}
        {sortedToolEntries.length > 0 && (
          <div className="mt-3 space-y-2 border-t border-border/80 pt-3">
            {sortedToolEntries.map(([name, result]) => (
              <ToolResult key={name} name={name} result={result} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
