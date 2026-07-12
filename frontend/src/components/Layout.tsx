import { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { AppSidebar } from '@/components/AppSidebar';

interface LayoutProps {
  children: ReactNode;
}

function isChatRoute(pathname: string): boolean {
  return pathname.startsWith('/chat') && !pathname.startsWith('/chat-eval');
}

function isFullHeightRoute(pathname: string): boolean {
  return isChatRoute(pathname) || pathname.startsWith('/builder');
}

function usesCursorShell(pathname: string): boolean {
  return isFullHeightRoute(pathname);
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const fullHeight = isFullHeightRoute(location.pathname);
  const cursorShell = usesCursorShell(location.pathname);

  return (
    <div className="app-shell flex h-dvh overflow-hidden bg-background text-foreground">
      <AppSidebar />
      <main
        className={cn(
          'flex min-h-0 min-w-0 flex-1 flex-col',
          fullHeight ? 'overflow-hidden' : 'overflow-y-auto',
          cursorShell && 'cursor-chat-shell'
        )}
      >
        {children}
      </main>
    </div>
  );
}
