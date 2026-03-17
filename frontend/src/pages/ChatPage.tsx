import { useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { ChatSidebar } from '@/components/Chat/ChatSidebar';
import { ChatMessageList } from '@/components/Chat/ChatMessageList';
import { ChatInput } from '@/components/Chat/ChatInput';
import { GenerationProgressCard } from '@/components/Chat/GenerationProgressCard';
import {
  createSession,
  listSessions,
  getSession,
  deleteSession,
  sendMessage,
  type ChatSession,
  type ChatMessage,
} from '@/api/chat';
import { apiUrl } from '@/utils/api';

export function ChatPage() {
  const location = useLocation();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);
  const [generationRunId, setGenerationRunId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const { sessions: list } = await listSessions(50, 0);
      setSessions(list);
    } catch {
      setSessions([]);
    }
  }, []);

  const loadSession = useCallback(async (id: string) => {
    try {
      const { session, messages: msgs } = await getSession(id);
      setCurrentSession(session);
      setMessages(msgs);
    } catch {
      setCurrentSession(null);
      setMessages([]);
    }
  }, []);

  useEffect(() => {
    fetch(apiUrl('/api/v1/limits'))
      .then((r) => setBackendReachable(r.ok))
      .catch(() => setBackendReachable(false));
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleNewChat = useCallback(async () => {
    setCreatingSession(true);
    try {
      const { session_id } = await createSession();
      await loadSessions();
      await loadSession(session_id);
      setInput('');
      setStreamingContent(null);
    } catch (e) {
      console.error('Create session failed:', e);
    } finally {
      setCreatingSession(false);
    }
  }, [loadSessions, loadSession]);

  const handleSelectSession = useCallback(
    (id: string) => {
      loadSession(id);
      setStreamingContent(null);
    },
    [loadSession]
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      setDeletingId(id);
      try {
        await deleteSession(id);
        await loadSessions();
        if (currentSession?.id === id) {
          const remaining = sessions.filter((s) => s.id !== id);
          if (remaining.length > 0) {
            loadSession(remaining[0].id);
          } else {
            setCurrentSession(null);
            setMessages([]);
          }
        }
      } catch (e) {
        console.error('Delete failed:', e);
      } finally {
        setDeletingId(null);
      }
    },
    [currentSession, sessions, loadSessions, loadSession]
  );

  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || !currentSession) return;
    setInput('');
    setLoading(true);
    setStreamingContent('');

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const context = {
        source_page: location.pathname || '/chat',
      };
      await sendMessage(currentSession.id, content, {
        onChunk: (chunk) => {
          setStreamingContent((prev) => (prev || '') + chunk);
        },
        onDone: () => {
          setStreamingContent(null);
          setGenerationRunId(null);
          loadSession(currentSession.id);
        },
        onToolStart: (name, runId) => {
          if (name === 'generate_dita' && runId) {
            setGenerationRunId(runId);
          }
        },
        onTool: (name) => {
          const label = name === 'generate_dita' ? 'Generating DITA...' : name === 'create_job' ? 'Creating job...' : `Using ${name}...`;
          setStreamingContent((prev) => (prev || '') + `\n\n_(${label})_`);
        },
        onError: (msg) => {
          setStreamingContent(null);
          setGenerationRunId(null);
          setMessages((prev) => [
            ...prev,
            {
              id: `err-${Date.now()}`,
              role: 'assistant',
              content: `Error: ${msg}`,
              created_at: new Date().toISOString(),
            },
          ]);
        },
      }, context);
    } catch (e) {
      setStreamingContent(null);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${e instanceof Error ? e.message : String(e)}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, currentSession, loadSession, location.pathname]);

  const handleCopyMessage = useCallback((content: string) => {
    navigator.clipboard?.writeText(content);
  }, []);

  const handleExport = useCallback(
    async (sessionId: string) => {
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) return;
      const msgs =
        currentSession?.id === sessionId ? messages : (await getSession(sessionId)).messages;
      const lines: string[] = [`# ${session.title || 'Chat'}\n`];
      for (const m of msgs) {
        const role = m.role === 'user' ? 'You' : 'Assistant';
        lines.push(`## ${role}\n\n${m.content || ''}\n\n`);
      }
      const blob = new Blob([lines.join('')], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chat-${(session.title || session.id.slice(0, 8)).replace(/\s+/g, '-')}.md`;
      a.click();
      URL.revokeObjectURL(url);
    },
    [sessions, currentSession, messages]
  );

  useEffect(() => {
    if (sessions.length > 0 && !currentSession) {
      loadSession(sessions[0].id);
    }
  }, [sessions, currentSession, loadSession]);

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)]">
      {backendReachable === false && (
        <div
          className="p-4 rounded-lg bg-red-50 border-2 border-red-200 text-red-800 text-sm font-medium mb-4"
          role="alert"
        >
          <strong>Backend unreachable.</strong> Start the backend with{' '}
          <code className="bg-red-100 px-1.5 py-0.5 rounded">
            .\START_BACKEND_SIMPLE.ps1
          </code>{' '}
          or{' '}
          <code className="bg-red-100 px-1.5 py-0.5 rounded">.\RUN_BOTH.ps1</code>{' '}
          from the project root.
        </div>
      )}
      <div className="mb-4">
        <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
          AI Chat
        </h1>
        <p className="text-slate-600 mt-1">
          Paste Jira text, ask about DITA, or generate datasets. Powered by RAG and streaming.
        </p>
      </div>
      <div className="flex flex-1 min-h-0 border border-slate-200 rounded-lg bg-white shadow-sm overflow-hidden">
        <ChatSidebar
          sessions={sessions}
          currentId={currentSession?.id ?? null}
          onSelect={handleSelectSession}
          onNew={handleNewChat}
          onDelete={handleDeleteSession}
          onExport={handleExport}
          creatingSession={creatingSession}
          deletingId={deletingId}
        />
        <div className="flex-1 flex flex-col min-w-0">
          {currentSession ? (
            <>
              <ChatMessageList
                messages={messages}
                streamingContent={streamingContent}
                generationRunId={generationRunId}
                onGenerationComplete={() => setGenerationRunId(null)}
                onCopyMessage={handleCopyMessage}
              />
              <div className="p-4 border-t border-slate-200">
                <ChatInput
                  value={input}
                  onChange={setInput}
                  onSend={handleSend}
                  disabled={loading}
                  loading={loading}
                  placeholder="Paste Jira text, ask about DITA, or generate a dataset…"
                />
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-500">
              {sessions.length === 0 ? (
                <div className="text-center">
                  <p className="mb-4">No chats yet. Create one to get started.</p>
                  <button
                    type="button"
                    onClick={handleNewChat}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    New Chat
                  </button>
                </div>
              ) : (
                <p>Select a chat or create a new one</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
