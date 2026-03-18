import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Layout } from './components/Layout'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Builder } from './pages/Builder'
import { Loader2 } from 'lucide-react'
import AuthoringPage from './pages/AuthoringPage'

const JobHistoryPage = lazy(() => import('./pages/JobHistoryPage').then(module => ({ default: module.JobHistoryPage })))
const DatasetExplorerPage = lazy(() => import('./pages/DatasetExplorerPage').then(module => ({ default: module.DatasetExplorerPage })))
const AemUploadPage = lazy(() => import('./pages/AemUploadPage').then(module => ({ default: module.AemUploadPage })))
const ChatPage = lazy(() => import('./pages/ChatPage').then(module => ({ default: module.ChatPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(module => ({ default: module.SettingsPage })))

function App() {
  return (
      <ErrorBoundary>
        <Router>
          <Layout>
            <ErrorBoundary>
              <Suspense fallback={
                <div className="flex items-center justify-center min-h-[400px]">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                </div>
              }>
                <Routes>
                  <Route path="/" element={<Builder />} />
                  <Route path="/builder" element={<Builder />} />
                  <Route path="/job-history" element={<JobHistoryPage />} />
                  <Route path="/dataset-explorer" element={<DatasetExplorerPage />} />
                  <Route path="/chat" element={<ChatPage />} />
                  <Route path="/upload" element={<AemUploadPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/authoring" element={<AuthoringPage />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </Layout>
        </Router>
      </ErrorBoundary>
  )
}

export default App
