import { Link } from 'react-router-dom';
import { BookOpen, Boxes, FileSearch, History, Sparkles } from 'lucide-react';
import type { ChatSession } from '@/api/chat';

interface ChatWorkspacePanelProps {
  session: ChatSession | null;
  messageCount: number;
  historyOpen?: boolean;
  onToggleHistory?: () => void;
}

const shortcuts = [
  {
    to: '/builder',
    icon: Boxes,
    label: 'Dataset Builder',
    hint: 'Generate DITA training bundles',
  },
  {
    to: '/dataset-explorer',
    icon: FileSearch,
    label: 'Explorer',
    hint: 'Browse generated datasets',
  },
  {
    to: '/',
    icon: BookOpen,
    label: 'Docs',
    hint: 'Product documentation',
  },
];

export function ChatWorkspacePanel({
  session,
  messageCount,
  historyOpen = true,
  onToggleHistory,
}: ChatWorkspacePanelProps) {
  return (
    <div className="flex min-w-0 flex-1 flex-col cursor-chat-workspace overflow-y-auto px-8 py-10">
      <div className="mx-auto flex w-full max-w-xl flex-col">
        {!historyOpen && onToggleHistory ? (
          <button
            type="button"
            onClick={onToggleHistory}
            className="mb-4 inline-flex w-fit items-center gap-1.5 rounded-md border border-border/70 bg-card/50 px-2.5 py-1.5 text-[12px] text-muted-foreground transition hover:border-border hover:bg-card hover:text-foreground"
          >
            <History className="h-3.5 w-3.5" />
            Show chat history
          </button>
        ) : null}
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-foreground text-background">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-medium tracking-tight text-foreground">DITA Expert</h1>
            <p className="text-[12px] text-muted-foreground">AEM Guides authoring assistant</p>
          </div>
        </div>

        {session ? (
          <div className="mb-8 rounded-xl border border-border/70 bg-card/60 p-5">
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Active chat</p>
            <h2 className="mt-2 text-base font-medium leading-snug text-foreground">
              {session.title?.trim() || 'New Chat'}
            </h2>
            <p className="mt-2 text-[12px] text-muted-foreground">
              {messageCount === 0
                ? 'Ask in the panel on the right — use Agent for multi-step tasks or Ask for quick answers.'
                : `${messageCount} message${messageCount === 1 ? '' : 's'} in this thread`}
            </p>
          </div>
        ) : (
          <p className="mb-8 text-[13px] leading-relaxed text-muted-foreground">
            Select a past chat or start a new one. The conversation panel is docked on the right, like Cursor.
          </p>
        )}

        <div className="grid gap-2 sm:grid-cols-3">
          {shortcuts.map(({ to, icon: Icon, label, hint }) => (
            <Link
              key={to}
              to={to}
              className="rounded-lg border border-border/70 bg-card/50 px-3 py-3 transition hover:border-border hover:bg-card"
            >
              <Icon className="mb-2 h-4 w-4 text-muted-foreground" />
              <p className="text-[12px] font-medium text-foreground">{label}</p>
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{hint}</p>
            </Link>
          ))}
        </div>

        <div className="mt-10 rounded-lg border border-dashed border-border/80 px-4 py-3 text-[11px] leading-relaxed text-muted-foreground">
          Tip: type <kbd className="rounded border border-border bg-muted px-1">@</kbd> in the composer to add
          DITA spec, AEM Guides, Jira, or file context — same workflow as Cursor&apos;s @ menu.
        </div>
      </div>
    </div>
  );
}
