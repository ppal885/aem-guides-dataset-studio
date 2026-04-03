import { Button } from '@/components/ui/button';
import { MessageSquarePlus, Trash2, Loader2, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatSession as ChatSessionType } from '@/api/chat';

interface ChatSidebarProps {
  sessions: ChatSessionType[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onExport?: (id: string) => void;
  creatingSession?: boolean;
  deletingId?: string | null;
}

export function ChatSidebar({
  sessions,
  currentId,
  onSelect,
  onNew,
  onDelete,
  onExport,
  creatingSession,
  deletingId,
}: ChatSidebarProps) {
  return (
    <div className="w-72 flex-shrink-0 border-r border-slate-200 bg-slate-50/80 backdrop-blur-sm flex flex-col">
      <div className="border-b border-slate-200 px-4 py-4">
        <div className="mb-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            Sessions
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">AI workspace</h2>
          <p className="mt-1 text-sm text-slate-600">
            Keep drafting, refinement, and RAG answers in one thread.
          </p>
        </div>
        <Button
          onClick={onNew}
          variant="outline"
          className="w-full justify-center gap-2 border-blue-200 bg-white text-blue-700 hover:bg-blue-50"
          disabled={creatingSession}
        >
          <MessageSquarePlus className="w-4 h-4" />
          New Chat
        </Button>
      </div>
      <div className="flex items-center justify-between px-4 py-3 text-xs text-slate-500">
        <span>{sessions.length} conversation{sessions.length === 1 ? '' : 's'}</span>
        <span>Recent first</span>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {sessions.length === 0 && !creatingSession && (
          <p className="rounded-xl border border-dashed border-slate-200 bg-white px-3 py-4 text-sm text-slate-500">
            No chats yet. Start one from a suggestion card or the button above.
          </p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={cn(
              'group mb-2 rounded-2xl border px-3 py-3 transition cursor-pointer',
              currentId === s.id
                ? 'border-blue-200 bg-white text-blue-900 shadow-sm'
                : 'border-transparent bg-transparent hover:border-slate-200 hover:bg-white'
            )}
          >
            <button
              type="button"
              className="min-w-0 flex-1 text-left"
              onClick={() => onSelect(s.id)}
            >
              <div className="truncate text-sm font-medium">{s.title || 'New Chat'}</div>
              <div className="mt-1 text-xs text-slate-500">
                {s.updated_at || s.created_at
                  ? new Date(s.updated_at || s.created_at || '').toLocaleString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : 'No activity yet'}
              </div>
            </button>
            {onExport && currentId === s.id && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onExport(s.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-slate-100 text-slate-500 transition-opacity"
                title="Export as Markdown"
              >
                <Download className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s.id);
              }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-red-100 text-slate-500 hover:text-red-600 transition-opacity"
              title="Delete"
              disabled={deletingId === s.id}
            >
              {deletingId === s.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4" />
              )}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
