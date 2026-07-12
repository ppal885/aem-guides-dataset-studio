import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUp, AtSign, ChevronDown, ImagePlus, Loader2, Square, X } from 'lucide-react';
import type { PendingWorkflowGuide } from '@/components/Chat/pendingWorkflowUtils';
import {
  getActiveAuthoringMention,
  mentionTokenForFileName,
  replaceAuthoringMentionInValue,
} from '@/components/Chat/authoringMentionUtils';
import { CHAT_MENTION_ITEMS, filterChatMentionItems, type ChatMentionItem } from '@/components/Chat/chatMentionUtils';
import { ChatMentionMenu } from '@/components/Chat/ChatMentionMenu';
import { cn } from '@/lib/utils';

export type ChatComposerMode = 'agent' | 'ask';

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
  variant?: 'default' | 'cursor';
  centered?: boolean;
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
  variant = 'default',
  centered = false,
}: ChatInputProps) {
  const isCursor = variant === 'cursor';
  const showStop = Boolean(streaming && onStop);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const ditaInputRef = useRef<HTMLInputElement>(null);
  const canSend = Boolean(value.trim() && !loading && !disabled && !showStop);
  const mode: ChatComposerMode = humanPrompts ? 'ask' : 'agent';
  const [caret, setCaret] = useState(0);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [showModelMenu, setShowModelMenu] = useState(false);

  const activeMention = useMemo(
    () => (isCursor ? getActiveAuthoringMention(value, caret) : null),
    [isCursor, value, caret]
  );

  const mentionItems = useMemo(
    () => (activeMention ? filterChatMentionItems(CHAT_MENTION_ITEMS, activeMention.query) : []),
    [activeMention]
  );

  const showMentionMenu = Boolean(activeMention && mentionItems.length > 0);

  useEffect(() => {
    setMentionIndex(0);
  }, [activeMention?.query, mentionItems.length]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`;
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

  const syncCaret = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    setCaret(ta.selectionStart ?? value.length);
  }, [value.length]);

  const applyMentionInsert = useCallback(
    (text: string) => {
      if (!activeMention) return;
      const range = { start: activeMention.start, end: caret };
      const next = value.slice(0, range.start) + text + value.slice(range.end);
      onChange(next);
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (!ta) return;
        const pos = range.start + text.length;
        ta.focus();
        ta.setSelectionRange(pos, pos);
        setCaret(pos);
      });
    },
    [activeMention, caret, onChange, value]
  );

  const handleMentionSelect = useCallback(
    (item: ChatMentionItem) => {
      if (item.type === 'action') {
        if (item.id === 'pick-image') imageInputRef.current?.click();
        if (item.id === 'pick-dita') ditaInputRef.current?.click();
        return;
      }
      applyMentionInsert(item.insertText);
    },
    [applyMentionInsert]
  );

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

  const setMode = (next: ChatComposerMode) => {
    if (!onHumanPromptsChange) return;
    onHumanPromptsChange(next === 'ask');
  };

  const insertAt = () => {
    const ta = textareaRef.current;
    if (!ta) {
      onChange(value ? `${value} @` : '@');
      return;
    }
    const start = ta.selectionStart ?? value.length;
    const end = ta.selectionEnd ?? value.length;
    const next = `${value.slice(0, start)}@${value.slice(end)}`;
    onChange(next);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + 1;
      ta.setSelectionRange(pos, pos);
      setCaret(pos);
    });
  };

  const handleFilePicked = (file: File | undefined) => {
    if (!file) return;
    if (activeMention) {
      const { nextValue, caretAfter } = replaceAuthoringMentionInValue(
        value,
        { start: activeMention.start, end: caret },
        file.name
      );
      onChange(nextValue);
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (!ta) return;
        ta.focus();
        ta.setSelectionRange(caretAfter, caretAfter);
        setCaret(caretAfter);
      });
      return;
    }
    const token = mentionTokenForFileName(file.name);
    const spacer = value.length > 0 && !/\s$/.test(value) ? ' ' : '';
    const next = `${value}${spacer}${token} `;
    onChange(next);
    requestAnimationFrame(() => {
      const ta = textareaRef.current;
      if (!ta) return;
      const pos = next.length;
      ta.focus();
      ta.setSelectionRange(pos, pos);
      setCaret(pos);
    });
  };

  const cursorPlaceholder =
    mode === 'agent'
      ? 'Plan, search, or build DITA content…'
      : 'Ask a question about DITA or AEM Guides…';

  return (
    <div className={cn('relative flex min-h-0 flex-col gap-2', centered && 'w-full')}>
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          handleFilePicked(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
      <input
        ref={ditaInputRef}
        type="file"
        accept=".dita,.xml,.ditamap,text/xml,application/xml"
        className="hidden"
        onChange={(e) => {
          handleFilePicked(e.target.files?.[0]);
          e.target.value = '';
        }}
      />

      {pendingWorkflowGuide && (
        <div
          className={cn(
            'rounded-lg border px-3 py-3',
            pendingWorkflowGuide.kind === 'review'
              ? 'border-amber-200/80 bg-amber-50/80 dark:border-amber-900/50 dark:bg-amber-950/30'
              : 'border-border bg-muted/40'
          )}
          role="region"
          aria-label={pendingWorkflowGuide.title}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="min-w-0 text-xs font-medium text-foreground">{pendingWorkflowGuide.title}</p>
            {onDismissPendingWorkflowGuide && (
              <button
                type="button"
                onClick={onDismissPendingWorkflowGuide}
                className="shrink-0 rounded p-1 text-muted-foreground transition hover:bg-muted"
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-foreground">{pendingWorkflowGuide.helper}</p>
          {pendingWorkflowGuide.suggestedReplies.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {pendingWorkflowGuide.suggestedReplies.map((reply, idx) => (
                <button
                  key={reply}
                  type="button"
                  onClick={() => handleSuggestedReplyClick(reply)}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-[12px] font-medium transition',
                    idx === 0
                      ? 'bg-primary text-primary-foreground hover:opacity-90'
                      : 'border border-border bg-background text-foreground hover:bg-muted'
                  )}
                >
                  {reply}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="relative">
        {showMentionMenu && (
          <ChatMentionMenu
            items={mentionItems}
            activeIndex={mentionIndex}
            onSelect={handleMentionSelect}
            onHover={setMentionIndex}
          />
        )}

        <div
          className={cn(
            isCursor
              ? 'cursor-composer-box'
              : 'overflow-hidden rounded-2xl border border-border bg-muted/40 shadow-sm focus-within:border-ring/60 focus-within:ring-1 focus-within:ring-ring/20 dark:bg-muted/20'
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setCaret(e.target.selectionStart ?? e.target.value.length);
            }}
            onSelect={syncCaret}
            onKeyUp={syncCaret}
            onClick={syncCaret}
            onKeyDown={(e) => {
              if (showMentionMenu) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setMentionIndex((i) => (i + 1) % mentionItems.length);
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setMentionIndex((i) => (i - 1 + mentionItems.length) % mentionItems.length);
                  return;
                }
                if (e.key === 'Enter' || e.key === 'Tab') {
                  e.preventDefault();
                  const item = mentionItems[mentionIndex];
                  if (item) handleMentionSelect(item);
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  return;
                }
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!showStop && canSend) handleSendClick();
              }
            }}
            placeholder={
              pendingWorkflowGuide
                ? pendingWorkflowGuide.placeholder
                : isCursor
                  ? cursorPlaceholder
                  : placeholder
            }
            disabled={disabled}
            rows={1}
            style={{ minHeight: isCursor ? '72px' : '44px', maxHeight: '240px' }}
            className="w-full resize-none overflow-y-auto border-0 bg-transparent px-3.5 pb-2 pt-3 text-[13px] leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-0 disabled:opacity-60"
          />

          <div className="flex items-center justify-between gap-2 border-t border-border/40 px-2 py-1.5">
            <div className="flex min-w-0 flex-wrap items-center gap-1">
              {isCursor && onHumanPromptsChange && (
                <div className="flex items-center rounded-md border border-border/70 bg-muted/40 p-0.5">
                  <button
                    type="button"
                    onClick={() => setMode('agent')}
                    className={cn(
                      'rounded px-2 py-0.5 text-[11px] font-medium transition',
                      mode === 'agent'
                        ? 'bg-background text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    Agent
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode('ask')}
                    className={cn(
                      'rounded px-2 py-0.5 text-[11px] font-medium transition',
                      mode === 'ask'
                        ? 'bg-background text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    Ask
                  </button>
                </div>
              )}

              {isCursor && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowModelMenu((v) => !v)}
                    className="inline-flex items-center gap-0.5 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground transition hover:bg-muted hover:text-foreground"
                  >
                    DITA Expert
                    <ChevronDown className="h-3 w-3 opacity-60" />
                  </button>
                  {showModelMenu && (
                    <>
                      <button
                        type="button"
                        className="fixed inset-0 z-20 cursor-default"
                        aria-label="Close model menu"
                        onClick={() => setShowModelMenu(false)}
                      />
                      <div className="absolute bottom-full left-0 z-30 mb-1 min-w-[10rem] rounded-md border border-border bg-card py-1 shadow-md">
                        <p className="px-2.5 py-1.5 text-[11px] font-medium text-foreground">DITA Expert</p>
                        <p className="px-2.5 pb-1 text-[10px] text-muted-foreground">Default assistant model</p>
                      </div>
                    </>
                  )}
                </div>
              )}

              {isCursor && (
                <>
                  <button
                    type="button"
                    onClick={insertAt}
                    className={cn(
                      'rounded-md p-1.5 transition',
                      showMentionMenu
                        ? 'bg-muted text-foreground'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                    title="Add context (@)"
                  >
                    <AtSign className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => imageInputRef.current?.click()}
                    className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    title="Attach screenshot"
                  >
                    <ImagePlus className="h-3.5 w-3.5" />
                  </button>
                </>
              )}

              {!isCursor && onHumanPromptsChange && humanPrompts !== undefined && (
                <button
                  type="button"
                  onClick={() => onHumanPromptsChange(!humanPrompts)}
                  className="inline-flex items-center gap-0.5 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
                >
                  {humanPrompts ? 'Concise' : 'Detailed'}
                </button>
              )}

              {showStop && (
                <button
                  type="button"
                  onClick={onStop}
                  className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/60 px-2 py-1 text-[11px] font-medium text-foreground transition hover:bg-muted"
                >
                  <Square className="h-2.5 w-2.5 fill-current" />
                  Stop
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={handleSendClick}
              disabled={disabled || loading || showStop || !value.trim()}
              className={cn(
                'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition disabled:cursor-not-allowed disabled:opacity-25',
                isCursor
                  ? 'bg-foreground text-background hover:opacity-85'
                  : 'rounded-full bg-stone-200 text-stone-900 hover:bg-stone-300 dark:bg-stone-100 dark:text-stone-950'
              )}
              title="Send"
              aria-label="Send message"
            >
              {loading && !showStop ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
              )}
            </button>
          </div>
        </div>
      </div>

      {showShortcutHint && !pendingWorkflowGuide && !isCursor && (
        <p className="px-1 text-center text-[11px] text-muted-foreground">
          <kbd className="rounded border border-border bg-muted px-1">Enter</kbd> send ·{' '}
          <kbd className="rounded border border-border bg-muted px-1">Shift</kbd>+
          <kbd className="rounded border border-border bg-muted px-1">Enter</kbd> newline
        </p>
      )}
    </div>
  );
}
