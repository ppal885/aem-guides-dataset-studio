import { cn } from '@/lib/utils';
import type { AgentState, AgentStateInfo } from '@/api/chat';

interface AgentStateIndicatorProps {
  thinking?: string | null;
  state?: AgentState | null;
  stateMessage?: string | null;
  stateInfo?: AgentStateInfo | null;
  className?: string;
  variant?: 'default' | 'cursor';
}

const STATE_LABELS: Record<AgentState, string> = {
  analyzing: 'Analyzing',
  tool_calling: 'Using tools',
  synthesizing: 'Synthesizing',
  retrying: 'Retrying',
};

export function AgentStateIndicator({
  thinking,
  state,
  stateMessage,
  stateInfo,
  className,
  variant = 'default',
}: AgentStateIndicatorProps) {
  if (!thinking && !state) return null;

  const isCursor = variant === 'cursor';
  const stateLabel = state ? STATE_LABELS[state] : null;

  if (isCursor) {
    return (
      <div className={cn('flex flex-col gap-1.5', className)}>
        {thinking && (
          <details className="cursor-thinking-block group">
            <summary className="cursor-pointer list-none px-3 py-2 text-[12px] font-medium text-muted-foreground select-none">
              Thought process
            </summary>
            <div className="border-t border-border/50 px-3 py-2 text-[12px] leading-relaxed">{thinking}</div>
          </details>
        )}
        {stateLabel && (
          <div className="flex items-center gap-2 px-1 text-[12px] text-muted-foreground">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-muted-foreground/50 opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-muted-foreground" />
            </span>
            <span>{stateMessage || stateLabel}</span>
            {stateInfo?.round != null && stateInfo.maxRounds != null && (
              <span className="opacity-60">
                {stateInfo.round}/{stateInfo.maxRounds}
              </span>
            )}
          </div>
        )}
      </div>
    );
  }

  const STATE_CONFIG: Record<AgentState, { label: string; color: string; icon: string }> = {
    analyzing: {
      label: 'Analyzing',
      color:
        'text-blue-700 bg-blue-50 border-blue-200 dark:text-blue-300 dark:bg-blue-950/40 dark:border-blue-900',
      icon: '\u{1F50D}',
    },
    tool_calling: {
      label: 'Using tools',
      color:
        'text-amber-800 bg-amber-50 border-amber-200 dark:text-amber-200 dark:bg-amber-950/40 dark:border-amber-900',
      icon: '\u{2699}\u{FE0F}',
    },
    synthesizing: {
      label: 'Synthesizing',
      color:
        'text-emerald-800 bg-emerald-50 border-emerald-200 dark:text-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-900',
      icon: '\u{2728}',
    },
    retrying: {
      label: 'Retrying',
      color:
        'text-orange-800 bg-orange-50 border-orange-200 dark:text-orange-200 dark:bg-orange-950/40 dark:border-orange-900',
      icon: '\u{1F504}',
    },
  };

  const config = state ? STATE_CONFIG[state] : null;

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {thinking && (
        <div className="flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50/60 px-3 py-2 text-xs text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200">
          <span className="mt-0.5 shrink-0 text-sm" aria-hidden>
            {'\u{1F4AD}'}
          </span>
          <span className="leading-relaxed">{thinking}</span>
        </div>
      )}
      {config && (
        <div
          className={cn(
            'flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-300',
            config.color
          )}
        >
          <span className="shrink-0 text-sm" aria-hidden>
            {config.icon}
          </span>
          <span>{stateMessage || config.label}</span>
          {stateInfo?.round != null && stateInfo.maxRounds != null && (
            <span className="ml-auto text-[10px] opacity-60">
              Round {stateInfo.round}/{stateInfo.maxRounds}
            </span>
          )}
          <span className="relative ml-1 flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-40" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-current opacity-70" />
          </span>
        </div>
      )}
    </div>
  );
}
