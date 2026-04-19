import { useState, useCallback, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { MessageSquarePlus, Trash2, Loader2, Download, Pencil, Check, X, Eraser, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatSession as ChatSessionType } from '@/api/chat';

const MIN_WIDTH = 240;
const MAX_WIDTH = 520;
const DEFAULT_WIDTH = 320;
const STORAGE_KEY = 'chatSidebarWidth';
const COLLAPSED_KEY = 'chatSidebarCollapsed';

function readStoredWidth(): number {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v) {
      const n = parseInt(v, 10);
      if (n >= MIN_WIDTH && n <= MAX_WIDTH) return n;
    }
  } catch { /* ignore */ }
  return DEFAULT_WIDTH;
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1';
  } catch { return false; }
}

interface ChatSidebarProps {
  sessions: ChatSessionType[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  /** Remove every session in one action (caller should confirm). */
  onDeleteAll?: () => void | Promise<void>;
  onExport?: (id: string) => void;
  onRenameSession?: (id: string, title: string) => Promise<void>;
  creatingSession?: boolean;
  deletingId?: string | null;
  clearingAll?: boolean;
}

export function ChatSidebar({
  sessions,
  currentId,
  onSelect,
  onNew,
  onDelete,
  onDeleteAll,
  onExport,
  onRenameSession,
  creatingSession,
  deletingId,
  clearingAll,
}: ChatSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [savingTitle, setSavingTitle] = useState(false);
  const [width, setWidth] = useState(readStoredWidth);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [dragging, setDragging] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);

  // Persist width & collapsed state
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, String(width)); } catch { /* */ }
  }, [width]);
  useEffect(() => {
    try { localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0'); } catch { /* */ }
  }, [collapsed]);

  // Drag resize handler
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    const startX = e.clientX;
    const startWidth = width;
    const onMouseMove = (ev: MouseEvent) => {
      const delta = ev.clientX - startX;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta));
      setWidth(newWidth);
    };
    const onMouseUp = () => {
      setDragging(false);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [width]);

  const startRename = (s: ChatSessionType, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onRenameSession) return;
    setEditingId(s.id);
    setTitleDraft(s.title || 'New Chat');
  };

  const cancelRename = () => {
    setEditingId(null);
    setTitleDraft('');
  };

  const commitRename = async () => {
    if (!editingId || !onRenameSession) return;
    const t = titleDraft.trim();
    if (!t) {
      cancelRename();
      return;
    }
    setSavingTitle(true);
    try {
      await onRenameSession(editingId, t);
      setEditingId(null);
      setTitleDraft('');
    } catch (err) {
      console.error('Rename failed:', err);
    } finally {
      setSavingTitle(false);
    }
  };

  // Collapsed sidebar
  if (collapsed) {
    return (
      <div className="flex w-12 shrink-0 flex-col items-center gap-3 border-r border-slate-200 bg-slate-50 py-3">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm transition-colors hover:border-teal-300 hover:text-teal-700"
          title="Expand sidebar"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onNew}
          className="rounded-lg border border-slate-200 bg-white p-2 text-teal-600 shadow-sm transition-colors hover:border-teal-300 hover:bg-teal-50"
          title="New conversation"
          disabled={creatingSession || clearingAll}
        >
          <MessageSquarePlus className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      ref={sidebarRef}
      className="relative flex shrink-0 flex-col border-r border-slate-200 bg-slate-50"
      style={{ width }}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-3 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-600">Conversations</p>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
          title="Collapse sidebar"
        >
          <PanelLeftClose className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-1.5 px-2.5 py-2.5">
        <Button
          onClick={onNew}
          variant="outline"
          className="h-8 w-full items-center justify-center gap-2 rounded-lg border-0 bg-teal-600 font-semibold text-white shadow-sm hover:bg-teal-700"
          disabled={creatingSession || clearingAll}
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          New conversation
        </Button>
        {onDeleteAll && sessions.length > 0 && (
          <Button
            type="button"
            variant="ghost"
            className="flex h-7 w-full items-center justify-center gap-2 rounded-full text-rose-600 hover:bg-rose-50/80 hover:text-rose-700 text-xs"
            disabled={creatingSession || clearingAll || Boolean(deletingId)}
            onClick={() => void onDeleteAll()}
            aria-label="Clear all chats"
          >
            {clearingAll ? (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
            ) : (
              <Eraser className="h-3.5 w-3.5 shrink-0" />
            )}
            Clear all
          </Button>
        )}
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {sessions.length === 0 && !creatingSession && (
          <p className="px-3 py-6 text-center text-xs leading-relaxed text-slate-400">
            No history yet.
          </p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={cn(
              'group mb-1 flex cursor-pointer items-center gap-1.5 rounded-xl border border-transparent px-2.5 py-2.5 transition-all duration-150',
              currentId === s.id
                ? 'border-teal-200 bg-teal-50/90 shadow-sm'
                : 'hover:border-slate-200 hover:bg-white'
            )}
          >
            {editingId === s.id ? (
              <div className="flex min-w-0 flex-1 items-center gap-1">
                <input
                  type="text"
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void commitRename();
                    if (e.key === 'Escape') cancelRename();
                  }}
                  className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/25"
                  disabled={savingTitle}
                  autoFocus
                />
                <button
                  type="button"
                  className="rounded-md p-1 text-emerald-600 hover:bg-emerald-100"
                  onClick={() => void commitRename()}
                  disabled={savingTitle}
                  title="Save"
                >
                  {savingTitle ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                </button>
                <button
                  type="button"
                  className="p-1 rounded-md hover:bg-slate-200 text-slate-500"
                  onClick={cancelRename}
                  disabled={savingTitle}
                  title="Cancel"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className={cn(
                    "flex-1 min-w-0 text-left text-[13px] leading-5",
                    currentId === s.id ? "font-semibold text-slate-900" : "text-slate-700"
                  )}
                  onClick={() => onSelect(s.id)}
                  title={s.title || 'New Chat'}
                >
                  <span className="block max-h-10 overflow-hidden whitespace-normal break-words">{s.title || 'New Chat'}</span>
                </button>
                {onRenameSession && currentId === s.id && (
                  <button
                    type="button"
                    onClick={(e) => startRename(s, e)}
                    className="rounded-md p-1 text-slate-400 opacity-0 transition-all hover:bg-white hover:text-teal-700 group-hover:opacity-100"
                    title="Rename chat"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                )}
                {onExport && currentId === s.id && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onExport(s.id);
                    }}
                    className="rounded-md p-1 text-slate-400 opacity-0 transition-all hover:bg-white hover:text-teal-700 group-hover:opacity-100"
                    title="Export as Markdown"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.id);
                  }}
                    className="rounded-md p-1 text-slate-400 opacity-0 transition-all hover:bg-rose-50 hover:text-rose-500 group-hover:opacity-100"
                  title="Delete"
                  disabled={deletingId === s.id}
                >
                  {deletingId === s.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Drag handle */}
      <div
        className={cn(
          "absolute right-0 top-0 bottom-0 w-1 cursor-col-resize transition-colors z-10",
          dragging ? "bg-teal-500" : "bg-transparent hover:bg-teal-400/30"
        )}
        onMouseDown={handleMouseDown}
        title="Drag to resize"
      />
    </div>
  );
}
