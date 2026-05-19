import { cn } from '@/lib/utils';

export interface SuggestedFollowupChipsProps {
  questions: string[];
  /** Put the question in the composer for the user to edit before sending. */
  onUseQuestion: (question: string) => void;
  /** Send the question immediately as the next user turn. */
  onAskNow?: (question: string) => void;
  disabled?: boolean;
  className?: string;
  /** Override list heading for the chip list. */
  chipListTitle?: string;
  chipListAriaLabel?: string;
  /** Label for the immediate-send button (default "Ask"). */
  askButtonLabel?: string;
}

export function SuggestedFollowupChips({
  questions,
  onUseQuestion,
  onAskNow,
  disabled,
  className,
  chipListTitle = 'Suggested next questions',
  chipListAriaLabel,
  askButtonLabel = 'Ask',
}: SuggestedFollowupChipsProps) {
  if (!questions.length) return null;

  const aria = chipListAriaLabel ?? chipListTitle;

  return (
    <div
      className={cn(
        'rounded-xl border border-teal-100/90 bg-gradient-to-b from-teal-50/50 to-white px-3 py-2.5 shadow-sm',
        className
      )}
      role="region"
      aria-label={aria}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-teal-900/80 mb-2">
        {chipListTitle}
      </p>
      <ul className="flex flex-col gap-2">
        {questions.map((q, i) => (
          <li key={`${i}-${q.slice(0, 32)}`} className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onUseQuestion(q)}
              className={cn(
                'min-w-0 flex-1 rounded-lg border border-teal-200/80 bg-white px-3 py-2 text-left text-sm leading-snug text-slate-800',
                'transition hover:border-teal-400 hover:bg-teal-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40',
                disabled && 'cursor-not-allowed opacity-50'
              )}
            >
              {q}
            </button>
            {onAskNow ? (
              <button
                type="button"
                disabled={disabled}
                onClick={() => onAskNow(q)}
                className={cn(
                  'shrink-0 rounded-lg border border-teal-600 bg-teal-600 px-2.5 py-1.5 text-xs font-semibold text-white',
                  'transition hover:bg-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50',
                  disabled && 'cursor-not-allowed opacity-50'
                )}
              >
                {askButtonLabel}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
