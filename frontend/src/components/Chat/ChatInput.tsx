import { useState, useRef, useCallback, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Send, Loader2, Square, Upload, X as XIcon, Image as ImageIcon, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface UploadedFile {
  file_id: string;
  filename: string;
  stored_name: string;
  size_bytes: number;
  is_image: boolean;
  extension: string;
}

interface SlashCommand {
  command: string;
  label: string;
  description: string;
  template: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { command: '/generate', label: '/generate', description: 'Generate DITA from text', template: 'Generate a DITA task topic about ' },
  { command: '/review', label: '/review', description: 'Review DITA XML', template: 'Review this DITA XML:\n```xml\n\n```' },
  { command: '/recipes', label: '/recipes', description: 'Find dataset recipes', template: 'What dataset recipes are available for ' },
  { command: '/jobs', label: '/jobs', description: 'List recent jobs', template: 'Show me my recent dataset jobs' },
  { command: '/search', label: '/search', description: 'Search Jira issues', template: 'Search Jira for issues about ' },
  { command: '/spec', label: '/spec', description: 'Look up DITA spec', template: 'Look up the DITA spec for ' },
  { command: '/aem', label: '/aem', description: 'Search AEM Guides docs', template: 'Search AEM Guides documentation for ' },
  { command: '/pdf', label: '/pdf', description: 'Native PDF config help', template: 'How do I configure Native PDF output for ' },
];

const INPUT_HISTORY_KEY = 'chat-input-history';
const MAX_HISTORY = 50;

function useInputHistory() {
  const [history, setHistory] = useState<string[]>(() => {
    try {
      const stored = sessionStorage.getItem(INPUT_HISTORY_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [historyIdx, setHistoryIdx] = useState(-1);
  const savedDraft = useRef('');

  const pushHistory = useCallback((text: string) => {
    if (!text.trim()) return;
    setHistory((prev) => {
      const filtered = prev.filter((h) => h !== text);
      const next = [text, ...filtered].slice(0, MAX_HISTORY);
      try { sessionStorage.setItem(INPUT_HISTORY_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
    setHistoryIdx(-1);
  }, []);

  const navigateHistory = useCallback(
    (direction: 'up' | 'down', currentValue: string): string | null => {
      if (history.length === 0) return null;
      if (direction === 'up') {
        if (historyIdx === -1) savedDraft.current = currentValue;
        const newIdx = Math.min(historyIdx + 1, history.length - 1);
        if (newIdx === historyIdx) return null;
        setHistoryIdx(newIdx);
        return history[newIdx];
      } else {
        if (historyIdx <= -1) return null;
        const newIdx = historyIdx - 1;
        setHistoryIdx(newIdx);
        return newIdx === -1 ? savedDraft.current : history[newIdx];
      }
    },
    [history, historyIdx]
  );

  const resetHistoryNav = useCallback(() => setHistoryIdx(-1), []);

  return { pushHistory, navigateHistory, resetHistoryNav };
}

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
  sessionId?: string;
  onFilesUploaded?: (files: UploadedFile[]) => void;
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
  sessionId,
  onFilesUploaded,
}: ChatInputProps) {
  const showStop = Boolean(streaming && onStop);
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { pushHistory, navigateHistory, resetHistoryNav } = useInputHistory();

  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);

  const filteredCommands = SLASH_COMMANDS.filter(
    (c) => !slashFilter || c.command.startsWith(`/${slashFilter}`)
  );

  const uploadFiles = useCallback(async (files: File[]) => {
    if (!sessionId || files.length === 0) return;
    setUploading(true);
    const results: UploadedFile[] = [];
    for (const file of files) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`/api/v1/chat/sessions/${sessionId}/upload`, {
          method: 'POST',
          body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          results.push(data);
        }
      } catch {
        // silently skip failed uploads
      }
    }
    if (results.length > 0) {
      setUploadedFiles(prev => [...prev, ...results]);
      onFilesUploaded?.(results);
    }
    setUploading(false);
  }, [sessionId, onFilesUploaded]);

  const removeFile = useCallback((idx: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== idx));
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (!sessionId) return;

    const files = Array.from(e.dataTransfer.files);
    await uploadFiles(files);
  }, [sessionId, uploadFiles]);

  const handleChange = useCallback(
    (newValue: string) => {
      onChange(newValue);
      // Detect slash command at start of input
      if (newValue.startsWith('/')) {
        const word = newValue.split(/\s/)[0].slice(1);
        setSlashFilter(word);
        setShowSlashMenu(true);
        setSelectedIdx(0);
      } else {
        setShowSlashMenu(false);
      }
    },
    [onChange]
  );

  const applyCommand = useCallback(
    (cmd: SlashCommand) => {
      onChange(cmd.template);
      setShowSlashMenu(false);
      textareaRef.current?.focus();
      // Place cursor at end
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (ta) {
          ta.selectionStart = ta.selectionEnd = cmd.template.length;
        }
      });
    },
    [onChange]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (showSlashMenu && filteredCommands.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedIdx((i) => Math.min(i + 1, filteredCommands.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedIdx((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
          e.preventDefault();
          applyCommand(filteredCommands[selectedIdx]);
          return;
        }
        if (e.key === 'Escape') {
          setShowSlashMenu(false);
          return;
        }
      }
      // Input history navigation (ArrowUp/Down when input is empty or cursor at start)
      if (!showSlashMenu && e.key === 'ArrowUp' && !e.shiftKey) {
        const ta = textareaRef.current;
        const atStart = !ta || ta.selectionStart === 0;
        if (atStart || !value.trim()) {
          const prev = navigateHistory('up', value);
          if (prev !== null) {
            e.preventDefault();
            onChange(prev);
            return;
          }
        }
      }
      if (!showSlashMenu && e.key === 'ArrowDown' && !e.shiftKey) {
        const ta = textareaRef.current;
        const atEnd = !ta || ta.selectionStart === value.length;
        if (atEnd || !value.trim()) {
          const next = navigateHistory('down', value);
          if (next !== null) {
            e.preventDefault();
            onChange(next);
            return;
          }
        }
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!showStop) {
          pushHistory(value);
          resetHistoryNav();
          setUploadedFiles([]);
          onSend();
        }
      }
    },
    [showSlashMenu, filteredCommands, selectedIdx, applyCommand, onSend, showStop, value, onChange, navigateHistory, pushHistory, resetHistoryNav]
  );

  // Close menu on blur (delayed to allow click)
  useEffect(() => {
    if (!value.startsWith('/')) setShowSlashMenu(false);
  }, [value]);

  return (
    <div className="flex flex-col gap-2">
      <div className="relative flex gap-3">
        {showSlashMenu && filteredCommands.length > 0 && (
          <div className="absolute bottom-full left-0 z-20 mb-1.5 w-80 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
            <div className="border-b border-slate-100 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
              Commands
            </div>
            {filteredCommands.map((cmd, i) => (
              <button
                key={cmd.command}
                type="button"
                className={`flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition ${
                  i === selectedIdx
                    ? 'bg-slate-100 text-slate-900'
                    : 'text-slate-600 hover:bg-slate-50'
                }`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  applyCommand(cmd);
                }}
                onMouseEnter={() => setSelectedIdx(i)}
              >
                <code className="rounded bg-slate-200/60 px-1.5 py-0.5 text-xs font-semibold text-slate-700">
                  {cmd.command}
                </code>
                <span className="text-xs text-slate-500">{cmd.description}</span>
              </button>
            ))}
          </div>
        )}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn("relative flex-1", isDragging && "ring-2 ring-blue-400 ring-offset-2 rounded-lg")}
        >
          {isDragging && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-blue-50/90 border-2 border-dashed border-blue-400">
              <div className="flex flex-col items-center gap-1 text-blue-600">
                <Upload className="h-6 w-6" />
                <span className="text-sm font-medium">Drop files here</span>
              </div>
            </div>
          )}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={3}
            className="min-h-[72px] w-full resize-y rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm leading-relaxed text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/25 disabled:opacity-60"
          />
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,.xml,.dita,.ditamap,.pdf"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) uploadFiles(Array.from(e.target.files));
            e.target.value = '';
          }}
        />
        <div className="flex shrink-0 flex-col gap-2 self-end">
          {sessionId && (
            <Button
              type="button"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || uploading}
              className="h-11 rounded-lg border-slate-300 text-slate-600 hover:bg-slate-50"
              title="Upload files (images, XML, DITA)"
            >
              <Upload className="h-4 w-4" />
            </Button>
          )}
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
      {uploadedFiles.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {uploadedFiles.map((f, i) => (
            <span
              key={f.file_id}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 border border-slate-200 px-2.5 py-1 text-xs text-slate-700"
            >
              {f.is_image ? <ImageIcon className="h-3 w-3 text-blue-500" /> : <FileText className="h-3 w-3 text-slate-500" />}
              <span className="max-w-[120px] truncate">{f.filename}</span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="ml-0.5 rounded-full p-0.5 hover:bg-slate-200 transition-colors"
              >
                <XIcon className="h-3 w-3" />
              </button>
            </span>
          ))}
          {uploading && <span className="text-xs text-slate-400 animate-pulse">Uploading...</span>}
        </div>
      )}
      {showShortcutHint && (
        <p className="text-xs text-slate-400">
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Enter</kbd> to send ·{' '}
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Shift</kbd>+
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Enter</kbd> for a new line ·{' '}
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">/</kbd> for commands ·{' '}
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1">&uarr;</kbd> for history
        </p>
      )}
    </div>
  );
}
