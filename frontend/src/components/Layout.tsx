import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Upload, History, FolderOpen, Sparkles, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Builder', icon: LayoutDashboard },
    { path: '/chat', label: 'AI Chat', icon: Sparkles },
    { path: '/job-history', label: 'Job History', icon: History },
    { path: '/dataset-explorer', label: 'Dataset Explorer', icon: FolderOpen },
    { path: '/upload', label: 'Upload to AEM', icon: Upload },
    { path: '/settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-teal-50/35 to-slate-100">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/50 sticky top-0 z-50 shadow-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <Link
              to="/"
              className="group flex items-center gap-3 rounded-xl outline-none ring-offset-2 transition hover:opacity-95 focus-visible:ring-2 focus-visible:ring-teal-500/40"
            >
              <img
                src="/app-icon.svg"
                alt=""
                width={40}
                height={40}
                className="h-10 w-10 shrink-0 rounded-xl shadow-md shadow-slate-900/10 ring-1 ring-slate-900/5 transition group-hover:ring-teal-500/25"
                decoding="async"
              />
              <div className="text-left">
                <p className="text-xl font-bold bg-gradient-to-r from-teal-800 via-teal-700 to-teal-600 bg-clip-text text-transparent">
                  AEM Guides Dataset Studio
                </p>
                <p className="text-xs text-slate-500">Generate &amp; manage datasets</p>
              </div>
            </Link>
            <nav className="flex items-center gap-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                      isActive
                        ? "bg-teal-600 text-white shadow-md shadow-teal-900/15"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="mt-auto border-t border-slate-200 bg-white/50 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4 text-center text-sm text-slate-500">
          © 2024 AEM Guides Dataset Studio. Built with FastAPI & React.
        </div>
      </footer>
    </div>
  );
}
