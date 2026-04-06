import { useState, useCallback, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChatSidebar } from '@/components/Chat/ChatSidebar';
import { ChatMessageList } from '@/components/Chat/ChatMessageList';
import { ChatInput } from '@/components/Chat/ChatInput';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  createSession,
  listSessions,
  getSession,
  deleteSession,
  deleteAllSessions,
  sendMessage,
  patchUserMessage,
  patchSessionTitle,
  regenerateAssistant,
  type ChatSession,
  type ChatMessage,
  type AgentState,
  type AgentStateInfo,
  type JobProgressInfo,
  type SuggestedFollowup,
} from '@/api/chat';
import { apiUrl } from '@/utils/api';
import { useAppFeedback } from '@/components/feedback/useAppFeedback';

const HUMAN_PROMPTS_STORAGE_KEY = 'chatHumanPrompts';

function readHumanPromptsDefault(): boolean {
  try {
    const v = localStorage.getItem(HUMAN_PROMPTS_STORAGE_KEY);
    if (v === null) return true;
    return v === '1' || v === 'true';
  } catch {
    return true;
  }
}

function isAbortError(e: unknown): boolean {
  if (e instanceof DOMException && e.name === 'AbortError') return true;
  if (e instanceof Error && e.name === 'AbortError') return true;
  return false;
}

export function ChatPage() {
  const feedback = useAppFeedback();
  const location = useLocation();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [clearingAllChats, setClearingAllChats] = useState(false);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);
  const [generationRunId, setGenerationRunId] = useState<string | null>(null);
  const [thinking, setThinking] = useState<string | null>(null);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [agentStateMessage, setAgentStateMessage] = useState<string | null>(null);
  const [agentStateInfo, setAgentStateInfo] = useState<AgentStateInfo | null>(null);
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);
  const [approvalTools, setApprovalTools] = useState<string[]>([]);
  const [jobProgress, setJobProgress] = useState<JobProgressInfo | null>(null);
  const [suggestedFollowups, setSuggestedFollowups] = useState<SuggestedFollowup[]>([]);
  const [humanPrompts, setHumanPrompts] = useState<boolean>(readHumanPromptsDefault);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(HUMAN_PROMPTS_STORAGE_KEY, humanPrompts ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [humanPrompts]);

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
      abortRef.current?.abort();
      abortRef.current = null;
      loadSession(id);
      setStreamingContent(null);
      setLoading(false);
    },
    [loadSession]
  );

  const handleDeleteAllChats = useCallback(async () => {
    if (sessions.length === 0) return;
    const confirmed = await feedback.confirm({
      title: 'Clear all chats?',
      message:
        'This removes every conversation and all messages. This action cannot be undone.',
      confirmLabel: 'Clear all',
      cancelLabel: 'Cancel',
      tone: 'danger',
    });
    if (!confirmed) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setClearingAllChats(true);
    try {
      await deleteAllSessions();
      // Clear UI immediately so the sidebar empties even if list refetch fails.
      setCurrentSession(null);
      setMessages([]);
      setSessions([]);
      setStreamingContent(null);
      setLoading(false);
      setGenerationRunId(null);
      setInput('');
      await loadSessions();
    } catch (e) {
      console.error('Clear all chats failed:', e);
      feedback.error(
        'Could not clear chats',
        e instanceof Error ? e.message : 'Request failed. Check the backend is running and try again.'
      );
    } finally {
      setClearingAllChats(false);
    }
  }, [sessions.length, loadSessions, feedback]);

  const handleDeleteSession = useCallback(
    async (id: string) => {
      const confirmed = await feedback.confirm({
        title: 'Delete this chat?',
        message: 'This chat and all of its messages will be removed. This cannot be undone.',
        confirmLabel: 'Delete chat',
        cancelLabel: 'Cancel',
        tone: 'danger',
      });
      if (!confirmed) return;
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
        feedback.error(
          'Could not delete chat',
          e instanceof Error ? e.message : 'Request failed. Try again.'
        );
      } finally {
        setDeletingId(null);
      }
    },
    [currentSession, sessions, loadSessions, loadSession, feedback]
  );

  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      try {
        const { session } = await patchSessionTitle(id, title);
        setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, ...session } : s)));
        setCurrentSession((prev) => (prev?.id === id ? { ...prev, ...session } : prev));
      } catch (e) {
        feedback.error(
          'Could not rename chat',
          e instanceof Error ? e.message : 'Request failed. Try again.'
        );
        throw e;
      }
    },
    [feedback]
  );

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setStreamingContent(null);
    setGenerationRunId(null);
    setThinking(null);
    setAgentState(null);
    setAgentStateMessage(null);
    setAgentStateInfo(null);
    setApprovalMessage(null);
    setApprovalTools([]);
    setJobProgress(null);
    setSuggestedFollowups([]);
    if (currentSession) {
      void loadSession(currentSession.id);
    }
  }, [currentSession, loadSession]);

  const streamCallbacks = useCallback(
    (sessionId: string) => ({
      onChunk: (chunk: string) => {
        // Clear thinking/state once real content starts flowing
        setThinking(null);
        setAgentState(null);
        setStreamingContent((prev) => (prev || '') + chunk);
      },
      onDone: () => {
        setStreamingContent(null);
        setGenerationRunId(null);
        setThinking(null);
        setAgentState(null);
        setAgentStateMessage(null);
        setAgentStateInfo(null);
        setApprovalMessage(null);
        setApprovalTools([]);
        setJobProgress(null);
        // Keep suggestedFollowups visible after done — they are shown below the last message
        void loadSession(sessionId);
      },
      onToolStart: (name: string, runId?: string) => {
        if (name === 'generate_dita' && runId) {
          setGenerationRunId(runId);
        }
      },
      onTool: (name: string) => {
        const label =
          name === 'generate_dita'
            ? 'Generating DITA...'
            : name === 'create_job'
              ? 'Creating job...'
              : `Using ${name}...`;
        setStreamingContent((prev) => (prev || '') + `\n\n_(${label})_`);
      },
      onThinking: (content: string) => {
        setThinking(content);
      },
      onState: (state: AgentState, message: string, info: AgentStateInfo) => {
        setAgentState(state);
        setAgentStateMessage(message);
        setAgentStateInfo(info);
      },
      onApprovalRequired: (message: string, tools: string[]) => {
        setApprovalMessage(message);
        setApprovalTools(tools);
      },
      onJobProgress: (info: JobProgressInfo) => {
        setJobProgress(info);
      },
      onSuggestedFollowups: (followups: SuggestedFollowup[]) => {
        setSuggestedFollowups(followups);
      },
      onError: (msg: string) => {
        setStreamingContent(null);
        setGenerationRunId(null);
        setThinking(null);
        setAgentState(null);
        setApprovalMessage(null);
        setJobProgress(null);
        const errBubble: ChatMessage = {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${msg}`,
          created_at: new Date().toISOString(),
        };
        // Sync user rows from server (real ids), then append error. loadSession alone would drop the
        // error bubble because failed turns are not persisted as assistant messages.
        void (async () => {
          try {
            const { session, messages: msgs } = await getSession(sessionId);
            setCurrentSession(session);
            setMessages([...msgs, errBubble]);
          } catch {
            setMessages((prev) => [...prev, errBubble]);
          }
        })();
      },
    }),
    [loadSession]
  );

  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || !currentSession) return;
    setInput('');
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setStreamingContent('');
    setSuggestedFollowups([]);

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    const context = {
      source_page: location.pathname || '/chat',
    };
    const cbs = streamCallbacks(currentSession.id);

    try {
      await sendMessage(currentSession.id, content, cbs, {
        context,
        humanPrompts,
        signal: ac.signal,
      });
    } catch (e) {
      if (isAbortError(e)) {
        await loadSession(currentSession.id);
        return;
      }
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
      setStreamingContent(null);
      abortRef.current = null;
    }
  }, [input, currentSession, loadSession, location.pathname, humanPrompts, streamCallbacks]);

  const runRegenerateStream = useCallback(async () => {
    if (!currentSession) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setStreamingContent('');
    setGenerationRunId(null);
    const context = {
      source_page: location.pathname || '/chat',
    };
    const cbs = streamCallbacks(currentSession.id);
    try {
      await regenerateAssistant(currentSession.id, cbs, {
        context,
        humanPrompts,
        signal: ac.signal,
      });
    } catch (e) {
      if (isAbortError(e)) {
        await loadSession(currentSession.id);
        return;
      }
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
      setStreamingContent(null);
      abortRef.current = null;
    }
  }, [currentSession, loadSession, location.pathname, humanPrompts, streamCallbacks]);

  const handleRegenerate = useCallback(() => {
    void runRegenerateStream();
  }, [runRegenerateStream]);

  const handleRetry = useCallback(() => {
    setMessages((prev) => {
      const next = [...prev];
      while (next.length > 0 && next[next.length - 1]!.id.startsWith('err-')) {
        next.pop();
      }
      return next;
    });
    void runRegenerateStream();
  }, [runRegenerateStream]);

  const handleSaveUserMessage = useCallback(
    async (messageIndex: number, messageId: string, newContent: string) => {
      if (!currentSession) return;

      // Always sync from server first: client-only rows (e.g. err-*) can desync indices/ids from DB.
      const { session: syncedSession, messages: fresh } = await getSession(currentSession.id);
      const serverSessionId = (syncedSession?.id || currentSession.id).trim();
      if (!serverSessionId) {
        throw new Error('Session not found. Refresh the page and try again.');
      }
      let resolvedId: string;
      if (messageId.startsWith('temp-')) {
        const row = fresh[messageIndex];
        if (!row || row.role !== 'user') {
          throw new Error(
            'This message is still syncing. Wait for the assistant reply to finish, then try editing again.'
          );
        }
        resolvedId = row.id;
      } else {
        const byId = fresh.find((m) => m.id === messageId && m.role === 'user');
        if (byId) {
          resolvedId = byId.id;
        } else {
          const row = fresh[messageIndex];
          if (row?.role === 'user') {
            resolvedId = row.id;
          } else {
            throw new Error(
              'Could not find this message on the server. Refresh the page or wait for sync, then try again.'
            );
          }
        }
      }
      setMessages(fresh);

      const { messages: next } = await patchUserMessage(
        serverSessionId,
        resolvedId.trim(),
        newContent
      );
      setMessages(next);

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setLoading(true);
      setStreamingContent('');
      setGenerationRunId(null);
      const context = {
        source_page: location.pathname || '/chat',
      };
      const cbs = streamCallbacks(serverSessionId);
      try {
        await regenerateAssistant(serverSessionId, cbs, {
          context,
          humanPrompts,
          signal: ac.signal,
        });
      } catch (e) {
        if (isAbortError(e)) {
          await loadSession(serverSessionId);
          return;
        }
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
        // Patch already applied; show error in-thread only — do not rethrow (closes edit UI).
      } finally {
        setLoading(false);
        setStreamingContent(null);
        abortRef.current = null;
      }
    },
    [currentSession, loadSession, location.pathname, humanPrompts, streamCallbacks]
  );

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

  const streaming = streamingContent !== null && loading;

  return (
    <div className="flex h-[calc(100dvh-10.5rem)] min-h-[28rem] flex-col gap-3">
      {backendReachable === false && (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 shadow-sm"
          role="alert"
        >
          <span className="font-semibold">Backend unreachable.</span>{' '}
          Start the backend with{' '}
          <code className="rounded border border-amber-200 bg-white px-1.5 py-0.5 font-mono text-xs">
            .\START_BACKEND_SIMPLE.ps1
          </code>{' '}
          or{' '}
          <code className="rounded border border-amber-200 bg-white px-1.5 py-0.5 font-mono text-xs">
            .\RUN_BOTH.ps1
          </code>{' '}
          from the project root.
        </div>
      )}
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <ChatSidebar
          sessions={sessions}
          currentId={currentSession?.id ?? null}
          onSelect={handleSelectSession}
          onNew={handleNewChat}
          onDelete={handleDeleteSession}
          onDeleteAll={handleDeleteAllChats}
          onExport={handleExport}
          onRenameSession={handleRenameSession}
          creatingSession={creatingSession}
          deletingId={deletingId}
          clearingAll={clearingAllChats}
        />
        <div className="flex min-w-0 flex-1 flex-col bg-slate-50/40">
          {currentSession ? (
            <>
              <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200/80 bg-white/90 backdrop-blur-sm px-5 py-2.5">
                <div className="min-w-0">
                  <h2 className="truncate text-[13px] font-semibold text-slate-800">
                    {currentSession.title?.trim() || 'Conversation'}
                  </h2>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    DITA · AEM Guides · Dataset Generation
                  </p>
                </div>
                <Link
                  to="/settings"
                  className="shrink-0 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-500 shadow-sm transition hover:border-slate-300 hover:text-slate-700"
                >
                  RAG &amp; search
                </Link>
              </div>
              <ChatMessageList
                messages={messages}
                streamingContent={streamingContent}
                generationRunId={generationRunId}
                onGenerationComplete={() => setGenerationRunId(null)}
                onCopyMessage={handleCopyMessage}
                onExamplePromptSelect={(text) => setInput(text)}
                onSaveUserMessage={handleSaveUserMessage}
                actionDisabled={loading}
                onRegenerate={handleRegenerate}
                onRetry={handleRetry}
                thinking={thinking}
                agentState={agentState}
                agentStateMessage={agentStateMessage}
                agentStateInfo={agentStateInfo}
                approvalMessage={approvalMessage}
                approvalTools={approvalTools}
                jobProgress={jobProgress}
                suggestedFollowups={suggestedFollowups}
                onFollowupSelect={(text) => {
                  setInput(text);
                  setSuggestedFollowups([]);
                }}
              />
              <div className="shrink-0 space-y-2.5 border-t border-slate-200/80 bg-white/95 backdrop-blur-sm px-5 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Switch
                      id="human-prompts"
                      checked={humanPrompts}
                      onCheckedChange={setHumanPrompts}
                    />
                    <Label htmlFor="human-prompts" className="cursor-pointer text-sm text-slate-700">
                      Precise answers
                    </Label>
                  </div>
                  <p className="max-w-md text-right text-xs leading-relaxed text-slate-500">
                    Fewer disclaimers and filler; stricter answer shape when enabled.
                  </p>
                </div>
                <ChatInput
                  value={input}
                  onChange={setInput}
                  onSend={handleSend}
                  onStop={handleStop}
                  disabled={loading}
                  loading={loading}
                  streaming={streaming}
                  showShortcutHint
                  sessionId={currentSession?.id}
                  placeholder="Paste Jira text, ask a DITA question, or request a dataset job..."
                />
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center text-slate-600">
              {sessions.length === 0 ? (
                <>
                  <div>
                    <p className="text-sm font-medium text-slate-900">No conversations yet</p>
                    <p className="mt-1 max-w-sm text-sm text-slate-500">
                      Start a chat to ask about DITA, AEM Guides, or generate content from Jira.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleNewChat}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
                  >
                    New conversation
                  </button>
                </>
              ) : (
                <p className="text-sm text-slate-500">Select a conversation from the list or create a new one.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
