import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  MessageSquarePlus,
  PanelLeftClose,
  Trash2,
  Loader2,
  Download,
  Pencil,
  Check,
  X,
  Eraser,
  Search,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { PanelResizeHandle } from '@/components/Chat/PanelResizeHandle';
import { useHorizontalPanelResize } from '@/components/Chat/usePanelResize';
import type { ChatSession as ChatSessionType } from '@/api/chat';

const MIN_WIDTH = 200;
const MAX_WIDTH = 480;
const DEFAULT_WIDTH = 260;
const STORAGE_KEY = 'chatSidebarWidth';

interface ChatSidebarProps {
  sessions: ChatSessionType[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onDeleteAll?: () => void | Promise<void>;
  onExport?: (id: string) => void;
  onRenameSession?: (id: string, title: string) => Promise<void>;
  creatingSession?: boolean;
  deletingId?: string | null;
  clearingAll?: boolean;
  variant?: 'default' | 'cursor';
  onClose?: () => void;
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
  variant = 'default',
  onClose,
}: ChatSidebarProps) {
  const isCursor = variant === 'cursor';
  const [editingId, setEditingId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [savingTitle, setSavingTitle] = useState(false);
  const [search, setSearch] = useState('');
  const sidebarRef = useRef<HTMLDivElement>(null);
  const { width, dragging, onMouseDown, resetWidth } = useHorizontalPanelResize({
    storageKey: STORAGE_KEY,
    defaultWidth: DEFAULT_WIDTH,
    minWidth: MIN_WIDTH,
    maxWidth: MAX_WIDTH,
  });

  const filteredSessions = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.title || 'New Chat').toLowerCase().includes(q));
  }, [sessions, search]);

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

  return (
    <div
      ref={sidebarRef}
      className={cn(
        'relative flex shrink-0 flex-col',
        isCursor ? 'cursor-sidebar' : 'border-r border-border bg-muted'
      )}
      style={{ width }}
    >
      <div className="flex items-center justify-between border-b border-border/60 px-3 py-2.5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Past chats</p>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition hover:bg-muted/60 hover:text-foreground"
            title="Hide chat history"
          >
            <PanelLeftClose className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>
      <div className="flex flex-col gap-2 p-2.5">
        <button
          type="button"
          onClick={onNew}
          disabled={creatingSession || clearingAll}
          className={cn(
            'flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] font-medium transition',
            isCursor
              ? 'text-foreground hover:bg-muted/70'
              : 'border-0 bg-primary text-primary-foreground hover:opacity-90'
          )}
        >
          {creatingSession ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <MessageSquarePlus className="h-4 w-4 shrink-0" />
          )}
          New chat
        </button>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chats"
            className="w-full rounded-lg border border-border/70 bg-background/80 py-1.5 pl-8 pr-2 text-[12px] text-foreground placeholder:text-muted-foreground focus:border-ring/50 focus:outline-none focus:ring-1 focus:ring-ring/20"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {filteredSessions.length === 0 && !creatingSession && (
          <p className="px-2 py-6 text-center text-[11px] leading-relaxed text-muted-foreground">
            {search.trim() ? 'No matching chats.' : 'No history yet.'}
          </p>
        )}
        {filteredSessions.map((s) => (
          <div
            key={s.id}
            data-selected={currentId === s.id ? '' : undefined}
            className={cn(
              'cursor-list-item group mb-0.5 flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1.5',
              currentId === s.id ? 'text-foreground' : 'text-muted-foreground'
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
                  className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring/25"
                  disabled={savingTitle}
                  autoFocus
                />
                <button
                  type="button"
                  className="rounded p-1 text-emerald-600 hover:bg-muted"
                  onClick={() => void commitRename()}
                  disabled={savingTitle}
                  title="Save"
                >
                  {savingTitle ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                </button>
                <button
                  type="button"
                  className="rounded p-1 text-muted-foreground hover:bg-muted"
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
                  className="min-w-0 flex-1 truncate text-left text-[12px] leading-5"
                  onClick={() => onSelect(s.id)}
                  title={s.title || 'New Chat'}
                >
                  {s.title || 'New Chat'}
                </button>
                {onRenameSession && currentId === s.id && (
                  <button
                    type="button"
                    onClick={(e) => startRename(s, e)}
                    className="rounded p-1 opacity-0 transition hover:bg-background group-hover:opacity-100"
                    title="Rename"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                )}
                {onExport && currentId === s.id && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onExport(s.id);
                    }}
                    className="rounded p-1 opacity-0 transition hover:bg-background group-hover:opacity-100"
                    title="Export"
                  >
                    <Download className="h-3 w-3" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.id);
                  }}
                  className="rounded p-1 text-muted-foreground opacity-0 transition hover:bg-background hover:text-destructive group-hover:opacity-100"
                  title="Delete"
                  disabled={deletingId === s.id}
                >
                  {deletingId === s.id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {onDeleteAll && sessions.length > 0 && (
        <div className="border-t border-border/60 p-2">
          <button
            type="button"
            onClick={() => void onDeleteAll()}
            disabled={creatingSession || clearingAll || Boolean(deletingId)}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] text-muted-foreground transition hover:bg-muted hover:text-destructive"
          >
            {clearingAll ? <Loader2 className="h-3 w-3 animate-spin" /> : <Eraser className="h-3 w-3" />}
            Clear all chats
          </button>
        </div>
      )}

      <PanelResizeHandle
        side="right"
        dragging={dragging}
        onMouseDown={onMouseDown}
        onDoubleClick={resetWidth}
        className="right-edge"
        title="Resize history panel"
      />
    </div>
  );
}
