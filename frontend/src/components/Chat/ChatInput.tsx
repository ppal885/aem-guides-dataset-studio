import { Button } from '@/components/ui/button';
import { Send, Loader2, Square } from 'lucide-react';

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop?: () => void;
  disabled?: boolean;
  loading?: boolean;
  streaming?: boolean;
  placeholder?: string;
  showShortcutHint?: boolean;
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  disabled,
  loading,
  streaming,
  placeholder = 'Type your message...',
  showShortcutHint = true,
}: ChatInputProps) {
  const showStop = Boolean(streaming && onStop);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-3">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (!showStop) onSend();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          className="min-h-[72px] flex-1 resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm leading-relaxed text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/25 disabled:opacity-60"
        />
        <div className="flex shrink-0 flex-col gap-2 self-end">
          {showStop && (
            <Button
              type="button"
              variant="outline"
              onClick={onStop}
              className="h-11 rounded-lg border-amber-300 text-amber-900 hover:bg-amber-50"
            >
              <Square className="mr-2 h-3.5 w-3.5 fill-current" />
              Stop
            </Button>
          )}
          <Button
            onClick={onSend}
            disabled={disabled || !value.trim() || loading || showStop}
            className="h-11 rounded-lg bg-slate-900 px-5 font-medium text-white shadow-sm transition hover:bg-slate-800"
          >
            {loading && !showStop ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            <span className="ml-2">Send</span>
          </Button>
        </div>
      </div>
      {showShortcutHint && (
        <p className="text-xs text-slate-400">
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Enter</kbd> to send ·{' '}
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Shift</kbd>+
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Enter</kbd> for a new line
        </p>
      )}
    </div>
  );
}
