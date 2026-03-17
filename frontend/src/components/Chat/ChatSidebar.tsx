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
    <div className="w-64 flex-shrink-0 border-r border-slate-200 bg-white/50 flex flex-col">
      <Button
        onClick={onNew}
        variant="outline"
        className="m-3 flex items-center gap-2"
        disabled={creatingSession}
      >
        <MessageSquarePlus className="w-4 h-4" />
        New Chat
      </Button>
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {sessions.length === 0 && !creatingSession && (
          <p className="text-sm text-slate-500 px-2 py-4">No chats yet</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={cn(
              'group flex items-center gap-2 rounded-lg px-3 py-2 mb-1 cursor-pointer',
              currentId === s.id ? 'bg-blue-100 text-blue-800' : 'hover:bg-slate-100'
            )}
          >
            <button
              type="button"
              className="flex-1 text-left truncate text-sm min-w-0"
              onClick={() => onSelect(s.id)}
            >
              {s.title || 'New Chat'}
            </button>
            {onExport && currentId === s.id && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onExport(s.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-slate-200 text-slate-500 transition-opacity"
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
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 text-slate-500 hover:text-red-600 transition-opacity"
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
