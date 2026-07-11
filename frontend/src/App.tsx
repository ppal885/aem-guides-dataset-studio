import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Layout } from './components/Layout'
import { ErrorBoundary } from './components/ErrorBoundary'
import { FeedbackProvider } from './components/feedback/FeedbackProvider'
import { Builder } from './pages/Builder'
import { LandingDocsPage } from './pages/LandingDocsPage'
import { Loader2 } from 'lucide-react'

const JobHistoryPage = lazy(() => import('./pages/JobHistoryPage').then(module => ({ default: module.JobHistoryPage })))
const DatasetExplorerPage = lazy(() => import('./pages/DatasetExplorerPage').then(module => ({ default: module.DatasetExplorerPage })))
const ChatPage = lazy(() => import('./pages/ChatPage').then(module => ({ default: module.ChatPage })))
const ChatEvalDashboardPage = lazy(() => import('./pages/ChatEvalDashboardPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(module => ({ default: module.SettingsPage })))
function App() {
  return (
    <ErrorBoundary>
      <Router>
        <FeedbackProvider>
          <Layout>
            <ErrorBoundary>
              <Suspense fallback={
                <div className="flex items-center justify-center min-h-[400px]">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              }>
                <Routes>
                  <Route path="/" element={<LandingDocsPage />} />
                  <Route path="/builder" element={<Builder />} />
                  <Route path="/job-history" element={<JobHistoryPage />} />
                  <Route path="/dataset-explorer" element={<DatasetExplorerPage />} />
                  <Route path="/chat" element={<ChatPage />} />
                  <Route path="/chat-eval" element={<ChatEvalDashboardPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </Layout>
        </FeedbackProvider>
      </Router>
    </ErrorBoundary>
  )
}

export default App
