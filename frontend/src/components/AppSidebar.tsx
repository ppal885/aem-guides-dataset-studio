import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  BarChart3,
  BookOpen,
  Boxes,
  ChevronLeft,
  ChevronRight,
  FolderSearch,
  MessageSquare,
  Settings,
  ListTodo,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ThemeToggle } from '@/components/ThemeToggle';
import { PanelResizeHandle } from '@/components/Chat/PanelResizeHandle';
import { useHorizontalPanelResize } from '@/components/Chat/usePanelResize';

const COLLAPSED_WIDTH = 48;
const EXPANDED_MIN = 180;
const EXPANDED_MAX = 280;
const EXPANDED_DEFAULT = 220;
const WIDTH_KEY = 'appSidebarWidth';
const EXPANDED_KEY = 'appSidebarExpanded';

export const appNavItems = [
  { path: '/', label: 'Docs', icon: BookOpen, match: (p: string) => p === '/' },
  {
    path: '/chat',
    label: 'AI Chat',
    icon: MessageSquare,
    match: (p: string) => p.startsWith('/chat') && !p.startsWith('/chat-eval'),
  },
  { path: '/chat-eval', label: 'Eval', icon: BarChart3, match: (p: string) => p.startsWith('/chat-eval') },
  { path: '/builder', label: 'Builder', icon: Boxes, match: (p: string) => p.startsWith('/builder') },
  { path: '/job-history', label: 'Jobs', icon: ListTodo, match: (p: string) => p.startsWith('/job-history') },
  {
    path: '/dataset-explorer',
    label: 'Explorer',
    icon: FolderSearch,
    match: (p: string) => p.startsWith('/dataset-explorer'),
  },
  { path: '/settings', label: 'Sources', icon: Settings, match: (p: string) => p.startsWith('/settings') },
] as const;

function readExpanded(): boolean {
  try {
    return localStorage.getItem(EXPANDED_KEY) !== '0';
  } catch {
    return true;
  }
}

function useExpandedState(): [boolean, (v: boolean) => void] {
  const [expanded, setExpanded] = useState(readExpanded);

  const setExpandedPersisted = (value: boolean) => {
    setExpanded(value);
    try {
      localStorage.setItem(EXPANDED_KEY, value ? '1' : '0');
    } catch {
      /* ignore */
    }
  };

  return [expanded, setExpandedPersisted];
}

export function AppSidebar() {
  const location = useLocation();
  const [expanded, setExpanded] = useExpandedState();
  const { width, dragging, onMouseDown, resetWidth } = useHorizontalPanelResize({
    storageKey: WIDTH_KEY,
    defaultWidth: EXPANDED_DEFAULT,
    minWidth: EXPANDED_MIN,
    maxWidth: EXPANDED_MAX,
  });

  const sidebarWidth = expanded ? width : COLLAPSED_WIDTH;

  return (
    <aside
      className="app-sidebar relative flex shrink-0 flex-col border-r border-border bg-[hsl(var(--app-rail))]"
      style={{ width: sidebarWidth }}
      data-collapsed={expanded ? undefined : ''}
    >
      <div
        className={cn(
          'flex shrink-0 items-center border-b border-border/60',
          expanded ? 'gap-2.5 px-3 py-3' : 'justify-center py-3'
        )}
      >
        <Link to="/" className="flex shrink-0 items-center gap-2.5" title="DITA Expert">
          <img
            src="/app-icon.svg"
            alt=""
            width={24}
            height={24}
            className="h-6 w-6 rounded-md ring-1 ring-border"
            decoding="async"
          />
          {expanded ? (
            <span className="truncate text-[13px] font-semibold tracking-tight text-foreground">DITA Expert</span>
          ) : null}
        </Link>
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {appNavItems.map((item) => {
          const active = item.match(location.pathname);
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              to={item.path}
              title={item.label}
              data-selected={active ? '' : undefined}
              className={cn(
                'cursor-list-item flex items-center',
                expanded ? 'gap-2.5 px-2.5 py-2 text-[13px]' : 'justify-center rounded-md p-2',
                active ? 'text-foreground' : 'text-muted-foreground'
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {expanded ? <span className="truncate font-medium">{item.label}</span> : null}
            </Link>
          );
        })}
      </nav>

      <div
        className={cn(
          'shrink-0 border-t border-border/60 p-2',
          expanded ? 'flex items-center justify-between gap-1' : 'flex flex-col items-center gap-1'
        )}
      >
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="rounded-md p-2 text-muted-foreground transition hover:bg-muted/60 hover:text-foreground"
          title={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <ThemeToggle />
      </div>

      {expanded ? (
        <PanelResizeHandle
          side="right"
          dragging={dragging}
          onMouseDown={onMouseDown}
          onDoubleClick={resetWidth}
          title="Resize sidebar"
        />
      ) : null}
    </aside>
  );
}
