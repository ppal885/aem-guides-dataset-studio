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

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const chatRoute = isChatRoute(location.pathname);

  return (
    <div className="app-shell flex h-dvh overflow-hidden bg-background text-foreground">
      <AppSidebar />
      <main
        className={cn(
          'flex min-h-0 min-w-0 flex-1 flex-col',
          chatRoute ? 'overflow-hidden cursor-chat-shell' : 'overflow-y-auto'
        )}
      >
        {children}
      </main>
    </div>
  );
}
