import { cn } from '@/lib/utils';
import type { AgentState, AgentStateInfo, JobProgressInfo } from '@/api/chat';
import { ToolResult } from './ChatMessage';
import { CursorToolAccordion } from './CursorToolAccordion';
import { AgentStateIndicator } from './AgentStateIndicator';
import { ApprovalGate } from './ApprovalGate';
import { DatasetJobStatusCard } from './DatasetJobStatusCard';
import { sortToolResultEntries } from './toolResultOrder';
import { CURSOR_MARKDOWN_PROSE_CLASS } from './ChatMarkdown';
import { ChatMarkdown } from './ChatMarkdown';

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
  variant?: 'default' | 'cursor';
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
  variant = 'cursor',
}: StreamingMessageProps) {
  const isCursor = variant === 'cursor';
  const showCursor = content.length > 0;
  const showStatus = Boolean(thinking || agentState || jobProgress || approvalMessage);
  const sortedToolEntries = toolResults ? sortToolResultEntries(Object.entries(toolResults)) : [];

  if (isCursor) {
    return (
      <div className={cn('group cursor-chat-turn animate-fadeIn', className)}>
        <div className="cursor-chat-content">
          {showStatus && (
            <div className="mb-2 space-y-2">
              <AgentStateIndicator
                thinking={thinking}
                state={agentState}
                stateMessage={agentStateMessage}
                stateInfo={agentStateInfo}
                variant="cursor"
              />
              {approvalMessage && <ApprovalGate message={approvalMessage} tools={approvalTools ?? []} />}
              {jobProgress && (
                <DatasetJobStatusCard
                  jobId={jobProgress.jobId}
                  initialStatus={jobProgress.status}
                  jobName={jobProgress.name}
                  recipeType={jobProgress.recipeType}
                  downloadUrl={jobProgress.downloadUrl}
                />
              )}
            </div>
          )}
          {sortedToolEntries.length > 0 && (
            <div className="mb-2 space-y-0">
              {sortedToolEntries.map(([name, result]) => (
                <CursorToolAccordion key={name} name={name} result={result} loading={!showCursor}>
                  <ToolResult name={name} result={result} />
                </CursorToolAccordion>
              ))}
            </div>
          )}
          <div className={cn(CURSOR_MARKDOWN_PROSE_CLASS, 'text-[13px]')} aria-live="polite" aria-busy="true">
            {showCursor ? (
              <>
                <ChatMarkdown content={content} variant="cursor" />
                <span
                  className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-foreground/60 align-[-2px]"
                  aria-hidden
                />
              </>
            ) : (
              <p className="text-[13px] text-muted-foreground">Working…</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('flex animate-fadeIn gap-3.5', className)}>
      <div className="min-w-0 w-full max-w-full flex-1 rounded-xl border border-border bg-card px-5 py-3.5 shadow-sm">
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-border/80 pb-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-teal-600 dark:text-teal-400">
            Assistant
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
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
              <ApprovalGate message={approvalMessage} tools={approvalTools ?? []} className="mb-2" />
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
              <ChatMarkdown content={content} />
            ) : (
              <p className="text-sm text-muted-foreground">Working on your request…</p>
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
