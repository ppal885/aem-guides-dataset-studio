import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Package, Upload, History, FolderOpen, Sparkles, Settings, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    { path: '/',                 label: 'Builder',          icon: LayoutDashboard },
    { path: '/chat',             label: 'AI Chat',          icon: Sparkles },
    { path: '/authoring',        label: 'Authoring',        icon: FileText },   // ← ADDED
    { path: '/job-history',      label: 'Job History',      icon: History },
    { path: '/dataset-explorer', label: 'Dataset Explorer', icon: FolderOpen },
    { path: '/upload',           label: 'Upload to AEM',    icon: Upload },
    { path: '/settings',         label: 'Settings',         icon: Settings },
  ];

  return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/50 sticky top-0 z-50 shadow-sm">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg flex items-center justify-center">
                  <Package className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                    AEM Guides Dataset Studio
                  </h1>
                  <p className="text-xs text-slate-500">Generate & Manage Datasets</p>
                </div>
              </div>
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
                                  ? "bg-blue-600 text-white shadow-md"
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
