import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  FileText,
  FolderOpen,
  History,
  LayoutDashboard,
  Package,
  Settings,
  Sparkles,
  Upload,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation()

  const navItems = [
    { path: '/', label: 'Builder', icon: LayoutDashboard },
    { path: '/chat', label: 'AI Chat', icon: Sparkles },
    { path: '/authoring', label: 'Authoring', icon: FileText },
    { path: '/job-history', label: 'Job History', icon: History },
    { path: '/dataset-explorer', label: 'Dataset Explorer', icon: FolderOpen },
    { path: '/upload', label: 'Upload to AEM', icon: Upload },
    { path: '/settings', label: 'Settings', icon: Settings },
  ]

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <header className="sticky top-0 z-50 border-b border-slate-200/50 bg-white/80 shadow-sm backdrop-blur-md">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600">
                <Package className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-xl font-bold text-transparent">
                  AEM Guides Dataset Studio
                </h1>
                <p className="text-xs text-slate-500">Generate and manage datasets</p>
              </div>
            </div>

            <nav className="flex items-center gap-1">
              {navItems.map(item => {
                const Icon = item.icon
                const isActive = location.pathname === item.path

                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all',
                      isActive
                        ? 'bg-blue-600 text-white shadow-md'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                )
              })}
            </nav>
          </div>
        </div>
      </header>

      <main className="container mx-auto min-h-0 flex-1 px-6 py-8">{children}</main>

      <footer className="shrink-0 border-t border-slate-200 bg-white/50 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4 text-center text-sm text-slate-500">
          Copyright 2024 AEM Guides Dataset Studio. Built with FastAPI and React.
        </div>
      </footer>
    </div>
  )
}
