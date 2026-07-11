import { ReactNode } from 'react';

import { Link, useLocation } from 'react-router-dom';

import { Search } from 'lucide-react';

import { cn } from '@/lib/utils';

import { APP_HEADER_HEIGHT_PX } from '@/components/DocsShell';

import { ThemeToggle } from '@/components/ThemeToggle';



interface LayoutProps {

  children: ReactNode;

}



const primaryNav = [

  { path: '/', label: 'Docs', match: (p: string) => p === '/' },

  { path: '/chat', label: 'AI Chat', match: (p: string) => p.startsWith('/chat') && !p.startsWith('/chat-eval') },

  { path: '/chat-eval', label: 'Eval', match: (p: string) => p.startsWith('/chat-eval') },

  { path: '/builder', label: 'Builder', match: (p: string) => p.startsWith('/builder') },

  { path: '/job-history', label: 'Jobs', match: (p: string) => p.startsWith('/job-history') },

  { path: '/dataset-explorer', label: 'Explorer', match: (p: string) => p.startsWith('/dataset-explorer') },

  { path: '/settings', label: 'Sources', match: (p: string) => p.startsWith('/settings') },

];



function isFullBleedRoute(pathname: string): boolean {

  return pathname === '/' || pathname.startsWith('/chat');

}



export function Layout({ children }: LayoutProps) {

  const location = useLocation();

  const fullBleed = isFullBleedRoute(location.pathname);

  const onChatPage = location.pathname.startsWith('/chat');



  return (

    <div className="min-h-screen bg-background text-foreground">

      <header

        className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/90"

        style={{ height: APP_HEADER_HEIGHT_PX }}

      >

        <div className="mx-auto flex h-full max-w-[1400px] items-center gap-4 px-4 sm:px-6">

          <Link to="/" className="flex shrink-0 items-center gap-2.5 pr-2">

            <img

              src="/app-icon.svg"

              alt=""

              width={28}

              height={28}

              className="h-7 w-7 rounded-md ring-1 ring-border"

              decoding="async"

            />

            <span className="hidden text-[15px] font-semibold tracking-tight text-foreground sm:inline">

              DITA Expert

            </span>

          </Link>



          <nav className="hidden h-full items-stretch gap-1 md:flex">

            {primaryNav.map((item) => {

              const active = item.match(location.pathname);

              return (

                <Link

                  key={item.path}

                  to={item.path}

                  className={cn(

                    'flex h-full items-center border-b-2 px-2.5 text-[13px] font-medium transition-colors',

                    active

                      ? 'border-foreground text-foreground'

                      : 'border-transparent text-muted-foreground hover:text-foreground'

                  )}

                >

                  {item.label}

                </Link>

              );

            })}

          </nav>



          {!onChatPage && (

            <Link

              to="/chat"

              className="group mx-auto hidden max-w-md flex-1 items-center gap-2 rounded-lg border border-border bg-muted/60 px-3 py-1.5 text-[13px] text-muted-foreground transition hover:border-border hover:bg-muted lg:flex"

            >

              <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />

              <span className="truncate">Ask about DITA, AEM Guides, or DITA-OT…</span>

              <kbd className="ml-auto hidden rounded border border-border bg-card px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground xl:inline">

                /chat

              </kbd>

            </Link>

          )}



          <div className={cn('flex items-center gap-2', onChatPage ? 'ml-auto' : '')}>

            {!onChatPage && (

              <Link

                to="/chat"

                className="rounded-full bg-primary px-4 py-1.5 text-[13px] font-medium text-primary-foreground transition hover:opacity-90"

              >

                Open Chat

              </Link>

            )}

            <ThemeToggle />

          </div>

        </div>

      </header>



      <nav className="flex gap-1 overflow-x-auto border-b border-border px-4 py-2 md:hidden">

        {primaryNav.map((item) => {

          const active = item.match(location.pathname);

          return (

            <Link

              key={item.path}

              to={item.path}

              className={cn(

                'shrink-0 rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors',

                active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'

              )}

            >

              {item.label}

            </Link>

          );

        })}

      </nav>



      <main className={cn(fullBleed ? 'min-h-[calc(100vh-56px)]' : '')}>

        {fullBleed ? (

          children

        ) : (

          <div className="mx-auto max-w-[1400px]">{children}</div>

        )}

      </main>

    </div>

  );

}


