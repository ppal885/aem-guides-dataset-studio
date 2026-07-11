import { useCallback, useEffect, useRef } from 'react';
import { ArrowUp, ChevronDown, Loader2, Square, X } from 'lucide-react';
import type { PendingWorkflowGuide } from '@/components/Chat/pendingWorkflowUtils';

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onQuickReply?: (reply: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  loading?: boolean;
  streaming?: boolean;
  placeholder?: string;
  showShortcutHint?: boolean;
  pendingWorkflowGuide?: PendingWorkflowGuide | null;
  onDismissPendingWorkflowGuide?: () => void;
  humanPrompts?: boolean;
  onHumanPromptsChange?: (value: boolean) => void;
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onQuickReply,
  onStop,
  disabled,
  loading,
  streaming,
  placeholder = 'Ask about DITA, AEM Guides, DITA-OT, or paste XML to review…',
  showShortcutHint = true,
  pendingWorkflowGuide = null,
  onDismissPendingWorkflowGuide,
  humanPrompts,
  onHumanPromptsChange,
}: ChatInputProps) {
  const showStop = Boolean(streaming && onStop);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = Boolean(value.trim() && !loading && !disabled && !showStop);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  }, [value]);

  useEffect(() => {
    if (!pendingWorkflowGuide || !onDismissPendingWorkflowGuide) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (e.defaultPrevented) return;
      onDismissPendingWorkflowGuide();
      e.preventDefault();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [pendingWorkflowGuide, onDismissPendingWorkflowGuide]);

  const handleSuggestedReplyClick = useCallback(
    (reply: string) => {
      if (onQuickReply && !disabled && !loading && !showStop) {
        onQuickReply(reply);
        return;
      }
      onChange(reply);
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
        const length = reply.length;
        textareaRef.current?.setSelectionRange(length, length);
      });
    },
    [disabled, loading, onChange, onQuickReply, showStop]
  );

  const handleSendClick = () => {
    if (!canSend) return;
    onSend();
  };

  return (
    <div className="relative flex min-h-0 flex-col gap-3">
      {pendingWorkflowGuide && (
        <div
          className={`rounded-lg border px-4 py-3.5 ${
            pendingWorkflowGuide.kind === 'review'
              ? 'border-amber-200 bg-amber-50/90 dark:border-amber-900/50 dark:bg-amber-950/40'
              : 'border-border bg-muted'
          }`}
          role="region"
          aria-label={pendingWorkflowGuide.title}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="min-w-0 text-xs font-semibold text-foreground">{pendingWorkflowGuide.title}</p>
            {onDismissPendingWorkflowGuide && (
              <button
                type="button"
                onClick={onDismissPendingWorkflowGuide}
                className="shrink-0 rounded-md p-1.5 text-muted-foreground transition hover:bg-muted"
                aria-label="Dismiss workflow prompt"
                title="Dismiss (Esc)"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <p className="mt-2 text-sm leading-relaxed text-foreground">{pendingWorkflowGuide.helper}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{pendingWorkflowGuide.detail}</p>
          {pendingWorkflowGuide.suggestedReplies.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {pendingWorkflowGuide.suggestedReplies.map((reply, idx) => (
                <button
                  key={reply}
                  type="button"
                  onClick={() => handleSuggestedReplyClick(reply)}
                  className={
                    idx === 0
                      ? 'rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90'
                      : 'rounded-md border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition hover:bg-muted'
                  }
                >
                  {reply}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-border bg-muted/40 shadow-sm transition focus-within:border-ring/60 focus-within:ring-1 focus-within:ring-ring/20 dark:bg-muted/20">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (!showStop && canSend) handleSendClick();
            }
          }}
          placeholder={pendingWorkflowGuide ? pendingWorkflowGuide.placeholder : placeholder}
          disabled={disabled}
          rows={1}
          style={{ minHeight: '44px', maxHeight: '220px' }}
          className="w-full resize-none overflow-y-auto border-0 bg-transparent px-4 pb-1 pt-3 text-[15px] leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-0 disabled:opacity-60"
        />

        <div className="flex items-center justify-between gap-2 px-3 pb-2.5 pt-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {onHumanPromptsChange && humanPrompts !== undefined && (
              <button
                type="button"
                onClick={() => onHumanPromptsChange(!humanPrompts)}
                className="inline-flex items-center gap-1 rounded-full border border-transparent bg-card/80 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-border hover:text-foreground"
                title={humanPrompts ? 'Concise replies (precision mode)' : 'Detailed replies'}
              >
                {humanPrompts ? 'Concise' : 'Detailed'}
                <ChevronDown className="h-3 w-3 opacity-70" />
              </button>
            )}

            {showStop && (
              <button
                type="button"
                onClick={onStop}
                className="inline-flex items-center gap-1 rounded-full border border-amber-300/80 bg-amber-50/90 px-2.5 py-1 text-xs font-medium text-amber-950 transition hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-900/50"
              >
                <Square className="h-3 w-3 fill-current" />
                Stop
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={handleSendClick}
            disabled={disabled || loading || showStop || !value.trim()}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-200 text-stone-900 transition hover:bg-stone-300 disabled:cursor-not-allowed disabled:opacity-35 dark:bg-stone-100 dark:text-stone-950 dark:hover:bg-white"
            title="Send message"
            aria-label="Send message"
          >
            {loading && !showStop ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowUp className="h-4 w-4" strokeWidth={2.25} />
            )}
          </button>
        </div>
      </div>

      {showShortcutHint && !pendingWorkflowGuide && (
        <p className="px-1 text-xs text-muted-foreground">
          Ask about DITA structure, AEM Guides, or DITA-OT. Paste XML to review.{' '}
          <kbd className="rounded border border-border bg-muted px-1">Enter</kbd> to send ·{' '}
          <kbd className="rounded border border-border bg-muted px-1">Shift</kbd>+
          <kbd className="rounded border border-border bg-muted px-1">Enter</kbd> new line
        </p>
      )}
    </div>
  );
}
