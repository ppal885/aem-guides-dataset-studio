import { Link } from 'react-router-dom';
import {
  MessageSquarePlus,
  History,
  Settings,
  BarChart3,
  Boxes,
  Home,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ThemeToggle } from '@/components/ThemeToggle';

interface ChatIconRailProps {
  onNewChat: () => void;
  onToggleHistory: () => void;
  historyOpen: boolean;
  creatingSession?: boolean;
}

const railLinks = [
  { to: '/', icon: Home, label: 'Docs' },
  { to: '/builder', icon: Boxes, label: 'Builder' },
  { to: '/chat-eval', icon: BarChart3, label: 'Eval' },
  { to: '/settings', icon: Settings, label: 'Sources' },
];

export function ChatIconRail({
  onNewChat,
  onToggleHistory,
  historyOpen,
  creatingSession,
}: ChatIconRailProps) {
  return (
    <aside className="flex w-12 shrink-0 flex-col items-center border-r border-border bg-[hsl(var(--cursor-rail))] py-2">
      <button
        type="button"
        onClick={onNewChat}
        disabled={creatingSession}
        className="mb-1 rounded-md p-2 text-muted-foreground transition hover:bg-muted/60 hover:text-foreground disabled:opacity-50"
        title="New chat"
      >
        <MessageSquarePlus className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onToggleHistory}
        className={cn(
          'mb-3 rounded-md p-2 transition',
          historyOpen
            ? 'bg-muted text-foreground'
            : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
        )}
        title="Chat history"
      >
        <History className="h-4 w-4" />
      </button>

      <div className="flex flex-1 flex-col items-center gap-1">
        {railLinks.map(({ to, icon: Icon, label }) => (
          <Link
            key={to}
            to={to}
            className="rounded-md p-2 text-muted-foreground transition hover:bg-muted/60 hover:text-foreground"
            title={label}
          >
            <Icon className="h-4 w-4" />
          </Link>
        ))}
      </div>

      <div className="mt-auto pt-2">
        <ThemeToggle />
      </div>
    </aside>
  );
}
