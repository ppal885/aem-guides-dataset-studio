import { useState, useCallback, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { MessageSquarePlus, Trash2, Loader2, Download, Pencil, Check, X, Eraser, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatSession as ChatSessionType } from '@/api/chat';

const MIN_WIDTH = 200;
const MAX_WIDTH = 480;
const DEFAULT_WIDTH = 288;
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
      <div className="flex w-12 shrink-0 flex-col items-center border-r border-slate-200 bg-slate-50/80 py-3 gap-3">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 hover:text-slate-700 transition-colors"
          title="Expand sidebar"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onNew}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 hover:text-slate-700 transition-colors"
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
      className="relative flex shrink-0 flex-col border-r border-slate-200 bg-slate-50/80 backdrop-blur-sm"
      style={{ width }}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Conversations</p>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="rounded-md p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600 transition-colors"
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
          className="flex w-full items-center justify-center gap-2 border-slate-200 bg-white font-medium text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-300 h-8 text-xs"
          disabled={creatingSession || clearingAll}
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          New conversation
        </Button>
        {onDeleteAll && sessions.length > 0 && (
          <Button
            type="button"
            variant="ghost"
            className="flex w-full items-center justify-center gap-2 text-red-600 hover:bg-red-50 hover:text-red-700 h-7 text-xs"
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
              'group mb-0.5 flex cursor-pointer items-center gap-1.5 rounded-lg border border-transparent px-2.5 py-2 transition-all duration-150',
              currentId === s.id
                ? 'border-indigo-200/60 bg-indigo-50/60 shadow-sm'
                : 'hover:bg-white/80 hover:shadow-sm'
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
                  className="min-w-0 flex-1 rounded-md border border-indigo-300 bg-white px-2 py-1 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
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
                    "flex-1 text-left truncate text-[13px] min-w-0",
                    currentId === s.id ? "font-medium text-indigo-900" : "text-slate-700"
                  )}
                  onClick={() => onSelect(s.id)}
                >
                  {s.title || 'New Chat'}
                </button>
                {onRenameSession && currentId === s.id && (
                  <button
                    type="button"
                    onClick={(e) => startRename(s, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-white text-slate-400 hover:text-slate-600 transition-all"
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
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-white text-slate-400 hover:text-slate-600 transition-all"
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
                  className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-red-50 text-slate-400 hover:text-red-500 transition-all"
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
          dragging ? "bg-indigo-400" : "bg-transparent hover:bg-indigo-300/50"
        )}
        onMouseDown={handleMouseDown}
        title="Drag to resize"
      />
    </div>
  );
}
