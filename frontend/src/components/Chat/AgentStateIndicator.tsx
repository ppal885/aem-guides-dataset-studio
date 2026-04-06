import { cn } from '@/lib/utils';
import type { AgentState, AgentStateInfo } from '@/api/chat';

interface AgentStateIndicatorProps {
  thinking?: string | null;
  state?: AgentState | null;
  stateMessage?: string | null;
  stateInfo?: AgentStateInfo | null;
  className?: string;
}

const STATE_CONFIG: Record<AgentState, { label: string; color: string; icon: string }> = {
  analyzing: {
    label: 'Analyzing',
    color: 'text-blue-600 bg-blue-50 border-blue-200',
    icon: '\u{1F50D}',
  },
  tool_calling: {
    label: 'Using tools',
    color: 'text-amber-700 bg-amber-50 border-amber-200',
    icon: '\u{2699}\u{FE0F}',
  },
  synthesizing: {
    label: 'Synthesizing',
    color: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    icon: '\u{2728}',
  },
  retrying: {
    label: 'Retrying',
    color: 'text-orange-700 bg-orange-50 border-orange-200',
    icon: '\u{1F504}',
  },
};

export function AgentStateIndicator({
  thinking,
  state,
  stateMessage,
  stateInfo,
  className,
}: AgentStateIndicatorProps) {
  if (!thinking && !state) return null;

  const config = state ? STATE_CONFIG[state] : null;

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {thinking && (
        <div className="flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50/60 px-3 py-2 text-xs text-indigo-700">
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
