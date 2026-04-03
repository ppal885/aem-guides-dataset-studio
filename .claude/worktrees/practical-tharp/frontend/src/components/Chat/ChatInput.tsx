import { useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Send, Loader2, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  loading?: boolean;
  placeholder?: string;
  helperText?: string;
  suggestions?: string[];
  onSuggestionClick?: (value: string) => void;
  modeLabel?: string | null;
  modeDescription?: string;
  onCancelMode?: () => void;
  sendLabel?: string;
  focusKey?: string | null;
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled,
  loading,
  placeholder = 'Type your message...',
  helperText,
  suggestions = [],
  onSuggestionClick,
  modeLabel,
  modeDescription,
  onCancelMode,
  sendLabel = 'Send',
  focusKey,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [value]);

  useEffect(() => {
    if (!focusKey) {
      return;
    }
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.focus();
    const length = textarea.value.length;
    textarea.setSelectionRange(length, length);
  }, [focusKey]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      {modeLabel && (
        <div className="mb-3 flex items-start justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <div>
            <div className="font-semibold">{modeLabel}</div>
            <div className="mt-1 text-xs leading-5 text-amber-800">
              {modeDescription || 'Update the prompt, then resend it from this point.'}
            </div>
          </div>
          {onCancelMode && (
            <Button type="button" variant="ghost" size="sm" onClick={onCancelMode} className="shrink-0">
              Cancel
            </Button>
          )}
        </div>
      )}
      {suggestions.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onSuggestionClick?.(suggestion)}
              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span className="max-w-[24rem] truncate">{suggestion}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex gap-3">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          className={cn(
            'min-h-[72px] flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 shadow-inner transition focus:border-blue-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-60',
            loading && 'cursor-progress'
          )}
        />
        <Button
          onClick={onSend}
          disabled={disabled || !value.trim() || loading}
          className="h-auto min-h-[72px] self-stretch rounded-xl px-5"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
          <span className="ml-2">{sendLabel}</span>
        </Button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-xs text-slate-500">
        <span>{helperText || 'Press Enter to send. Shift+Enter adds a new line.'}</span>
        <span className="text-right">{value.trim() ? `${value.trim().split(/\s+/).length} words` : 'No draft yet'}</span>
      </div>
    </div>
  );
}
