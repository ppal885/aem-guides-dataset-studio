import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { ChatWorkspacePanel } from '@/components/Chat/ChatWorkspacePanel';
import { PanelResizeHandle } from '@/components/Chat/PanelResizeHandle';
import { useHorizontalPanelResize } from '@/components/Chat/usePanelResize';
import { ChatSidebar } from '@/components/Chat/ChatSidebar';
import { ChatMessageList } from '@/components/Chat/ChatMessageList';
import { ChatInput } from '@/components/Chat/ChatInput';
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
  type ChatAgentExecution,
  type ChatAgentPlan,
  type ChatApprovalState,
  type AgentState,
  type AgentStateInfo,
  type JobProgressInfo,
  type SuggestedFollowup,
} from '@/api/chat';
import { apiUrl } from '@/utils/api';
import { useAppFeedback } from '@/components/feedback/useAppFeedback';
import { resolvePendingWorkflowGuideWithKey } from '@/components/Chat/pendingWorkflowUtils';

const HUMAN_PROMPTS_STORAGE_KEY = 'chatHumanPrompts';
const CHAT_PANEL_WIDTH_KEY = 'chatPanelWidth';
const CHAT_PANEL_MIN = 300;
const CHAT_PANEL_MAX = 760;
const CHAT_PANEL_DEFAULT = 440;

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
  const [streamingToolResults, setStreamingToolResults] = useState<Record<string, unknown> | null>(null);
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
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const {
    width: chatPanelWidth,
    dragging: chatPanelDragging,
    onMouseDown: onChatPanelResize,
    resetWidth: resetChatPanelWidth,
  } = useHorizontalPanelResize({
    storageKey: CHAT_PANEL_WIDTH_KEY,
    defaultWidth: CHAT_PANEL_DEFAULT,
    minWidth: CHAT_PANEL_MIN,
    maxWidth: CHAT_PANEL_MAX,
    invertDelta: true,
  });

  const { guide: rawPendingWorkflowGuide, sourceKey: pendingWorkflowSourceKey } = useMemo(
    () => resolvePendingWorkflowGuideWithKey(messages, streamingToolResults),
    [messages, streamingToolResults]
  );
  const [dismissedPendingWorkflowKey, setDismissedPendingWorkflowKey] = useState<string | null>(null);

  const pendingWorkflowGuide =
    rawPendingWorkflowGuide && pendingWorkflowSourceKey !== dismissedPendingWorkflowKey
      ? rawPendingWorkflowGuide
      : null;

  const dismissPendingWorkflowGuide = useCallback(() => {
    if (pendingWorkflowSourceKey) setDismissedPendingWorkflowKey(pendingWorkflowSourceKey);
  }, [pendingWorkflowSourceKey]);

  useEffect(() => {
    setDismissedPendingWorkflowKey(null);
  }, [currentSession?.id]);

  useEffect(() => {
    if (!rawPendingWorkflowGuide || !pendingWorkflowSourceKey) {
      setDismissedPendingWorkflowKey(null);
    }
  }, [rawPendingWorkflowGuide, pendingWorkflowSourceKey]);

  useEffect(() => {
    try {
      localStorage.setItem(HUMAN_PROMPTS_STORAGE_KEY, humanPrompts ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [humanPrompts]);

  useEffect(() => {
    if (window.matchMedia('(max-width: 767px)').matches) {
      setSidebarOpen(false);
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const { sessions: list } = await listSessions(50, 0);
      setSessions(list);
    } catch {
      setSessions([]);
    }
  }, []);

  const loadSession = useCallback(async (id: string) => {
    setMessagesLoading(true);
    try {
      const { session, messages: msgs } = await getSession(id);
      setCurrentSession(session);
      setMessages(msgs);
    } catch {
      setCurrentSession(null);
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const checkBackend = useCallback(async () => {
    try {
      const r = await fetch(apiUrl('/api/v1/limits'));
      setBackendReachable(r.ok);
      return r.ok;
    } catch {
      setBackendReachable(false);
      return false;
    }
  }, []);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | undefined;
    const tick = async () => {
      const ok = await checkBackend();
      if (ok && intervalId !== undefined) {
        clearInterval(intervalId);
        intervalId = undefined;
      }
    };
    void tick();
    intervalId = setInterval(() => void tick(), 4000);
    return () => {
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, [checkBackend]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void checkBackend();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [checkBackend]);

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
      setStreamingToolResults(null);
    } catch (e) {
      console.error('Create session failed:', e);
    } finally {
      setCreatingSession(false);
    }
  }, [loadSessions, loadSession]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleNewChat]);

  const handleSelectSession = useCallback(
    (id: string) => {
      abortRef.current?.abort();
      abortRef.current = null;
      setMessages([]);
      setMessagesLoading(true);
      setStreamingContent(null);
      setStreamingToolResults(null);
      setSuggestedFollowups([]);
      setThinking(null);
      setAgentState(null);
      setAgentStateMessage(null);
      setAgentStateInfo(null);
      setJobProgress(null);
      setLoading(false);
      void loadSession(id);
      if (window.matchMedia('(max-width: 767px)').matches) {
        setSidebarOpen(false);
      }
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
      setCurrentSession(null);
      setMessages([]);
      setSessions([]);
      setStreamingContent(null);
      setStreamingToolResults(null);
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

  const clearStreamingState = useCallback(() => {
    setStreamingContent(null);
    setStreamingToolResults(null);
    setGenerationRunId(null);
    setThinking(null);
    setAgentState(null);
    setAgentStateMessage(null);
    setAgentStateInfo(null);
    setApprovalMessage(null);
    setApprovalTools([]);
    setJobProgress(null);
  }, []);

  const streamCallbacks = useCallback(
    (sessionId: string) => ({
      onChunk: (chunk: string) => {
        setThinking(null);
        setAgentState(null);
        setAgentStateMessage(null);
        setAgentStateInfo(null);
        setStreamingContent((prev) => (prev || '') + chunk);
      },
      onDone: async () => {
        try {
          await loadSession(sessionId);
        } finally {
          clearStreamingState();
        }
      },
      onPlan: (plan: ChatAgentPlan) => {
        setStreamingToolResults((prev) => ({
          ...(prev || {}),
          _agent_plan: plan,
        }));
      },
      onApprovalRequired: (plan: ChatAgentPlan, approval: ChatApprovalState) => {
        setStreamingToolResults((prev) => ({
          ...(prev || {}),
          _agent_plan: plan,
          _approval_state: approval,
        }));
      },
      onStepStatus: (execution: ChatAgentExecution) => {
        setStreamingToolResults((prev) => ({
          ...(prev || {}),
          _agent_execution: execution,
        }));
      },
      onToolStart: (name: string, runId?: string) => {
        if (name === 'generate_dita' && runId) {
          setGenerationRunId(runId);
        }
      },
      onTool: (name: string, result: unknown) => {
        setStreamingToolResults((prev) => ({
          ...(prev || {}),
          [name]: result,
        }));
      },
      onGrounding: (grounding) => {
        setStreamingToolResults((prev) => ({
          ...(prev || {}),
          _grounding: grounding,
        }));
      },
      onThinking: (content: string) => {
        setThinking(content);
      },
      onState: (state: AgentState, message?: string, info?: AgentStateInfo) => {
        setAgentState(state);
        setAgentStateMessage(message ?? null);
        setAgentStateInfo(info ?? null);
      },
      onJobProgress: (progress: JobProgressInfo) => {
        setJobProgress(progress);
      },
      onSuggestedFollowups: (followups: SuggestedFollowup[]) => {
        setSuggestedFollowups(followups);
      },
      onError: (msg: string) => {
        clearStreamingState();
        const errBubble: ChatMessage = {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${msg}`,
          created_at: new Date().toISOString(),
        };
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
    [clearStreamingState, loadSession]
  );

  const submitTurn = useCallback(async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || !currentSession) return;
    setInput('');
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setStreamingContent('');
    setStreamingToolResults({});
    setSuggestedFollowups([]);
    setThinking(null);
    setAgentState(null);
    setAgentStateMessage(null);
    setAgentStateInfo(null);
    setJobProgress(null);

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    const context = {
      source_page: location.pathname || '/chat',
    };
    const cbs = streamCallbacks(currentSession.id);

    try {
      await sendMessage(currentSession.id, trimmed, cbs, {
        context,
        humanPrompts,
        signal: ac.signal,
      });
    } catch (e) {
      if (isAbortError(e)) {
        await loadSession(currentSession.id);
        return;
      }
      clearStreamingState();
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
      abortRef.current = null;
    }
  }, [
    currentSession,
    loadSession,
    location.pathname,
    humanPrompts,
    streamCallbacks,
    clearStreamingState,
  ]);

  const handleSend = useCallback(async () => {
    await submitTurn(input);
  }, [input, submitTurn]);

  const handleQuickReply = useCallback(async (reply: string) => {
    setInput('');
    await submitTurn(reply);
  }, [submitTurn]);

  const runRegenerateStream = useCallback(async () => {
    if (!currentSession) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setStreamingContent('');
    setStreamingToolResults({});
    setGenerationRunId(null);
    setSuggestedFollowups([]);
    setThinking(null);
    setAgentState(null);
    setAgentStateMessage(null);
    setAgentStateInfo(null);
    setJobProgress(null);
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
      clearStreamingState();
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
      abortRef.current = null;
    }
  }, [currentSession, loadSession, location.pathname, humanPrompts, streamCallbacks, clearStreamingState]);

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
      setStreamingToolResults({});
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
        setStreamingToolResults(null);
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
        setStreamingToolResults(null);
        abortRef.current = null;
      }
    },
    [currentSession, loadSession, location.pathname, humanPrompts, streamCallbacks]
  );

  const handleCopyMessage = useCallback(
    async (content: string) => {
      try {
        await navigator.clipboard.writeText(content);
        feedback.success('Copied to clipboard');
      } catch {
        feedback.error('Copy failed', 'Could not copy message text.');
      }
    },
    [feedback]
  );

  const handleGenerationComplete = useCallback(() => {
    setGenerationRunId(null);
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
    const params = new URLSearchParams(location.search);
    const sessionFromUrl = params.get('session')?.trim();
    if (sessionFromUrl && sessions.some((s) => s.id === sessionFromUrl)) {
      if (currentSession?.id !== sessionFromUrl) {
        void loadSession(sessionFromUrl);
      }
      return;
    }
    if (sessions.length > 0 && !currentSession) {
      void loadSession(sessions[0].id);
    }
  }, [sessions, currentSession, loadSession, location.search]);

  const streaming = streamingContent !== null && loading;
  const isEmptyThread =
    Boolean(currentSession) &&
    !messagesLoading &&
    messages.length === 0 &&
    streamingContent === null;

  const composer = (
    <ChatInput
      value={input}
      onChange={setInput}
      onSend={handleSend}
      onQuickReply={handleQuickReply}
      onStop={handleStop}
      pendingWorkflowGuide={pendingWorkflowGuide}
      onDismissPendingWorkflowGuide={pendingWorkflowGuide ? dismissPendingWorkflowGuide : undefined}
      humanPrompts={humanPrompts}
      onHumanPromptsChange={setHumanPrompts}
      disabled={loading}
      loading={loading}
      streaming={streaming}
      showShortcutHint={!isEmptyThread}
      variant="cursor"
      centered={isEmptyThread}
    />
  );

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {backendReachable === false && (
          <div
            className="shrink-0 border-b border-amber-200/80 bg-amber-50 px-4 py-2 text-xs text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-100"
            role="alert"
          >
            <span className="font-medium">API unreachable.</span> Start backend with{' '}
            <code className="rounded bg-card px-1 py-0.5 font-mono">python run_local.py</code> in{' '}
            <code className="rounded bg-card px-1 py-0.5 font-mono">backend/</code>.
            <button
              type="button"
              className="ml-2 rounded border border-amber-300 px-2 py-0.5 hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-900/50"
              onClick={() => void checkBackend()}
            >
              Retry
            </button>
          </div>
        )}

        <div className="flex min-h-0 flex-1 overflow-hidden">
          {sidebarOpen && (
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
              variant="cursor"
              onClose={() => setSidebarOpen(false)}
            />
          )}

          <ChatWorkspacePanel
            session={currentSession}
            messageCount={messages.length}
            historyOpen={sidebarOpen}
            onToggleHistory={() => setSidebarOpen((v) => !v)}
          />

          <aside className="cursor-chat-panel min-h-0" style={{ width: chatPanelWidth }}>
            <PanelResizeHandle
              side="left"
              dragging={chatPanelDragging}
              onMouseDown={onChatPanelResize}
              onDoubleClick={resetChatPanelWidth}
              className="left-edge"
              title="Resize chat panel"
            />
            {currentSession ? (
              <>
                <div className="shrink-0 border-b border-border/60 px-3 py-2.5">
                  <p className="truncate text-[12px] font-medium text-foreground">
                    {currentSession.title?.trim() || 'New Chat'}
                  </p>
                </div>
                <ChatMessageList
                  messages={messages}
                  sessionId={currentSession.id}
                  streamingContent={streamingContent}
                  streamingToolResults={streamingToolResults}
                  streamingThinking={thinking}
                  streamingAgentState={agentState}
                  streamingAgentStateMessage={agentStateMessage}
                  streamingAgentStateInfo={agentStateInfo}
                  streamingJobProgress={jobProgress}
                  generationRunId={generationRunId}
                  messagesLoading={messagesLoading}
                  onGenerationComplete={handleGenerationComplete}
                  onCopyMessage={handleCopyMessage}
                  onExamplePromptSelect={(text) => setInput(text)}
                  onSaveUserMessage={handleSaveUserMessage}
                  actionDisabled={loading}
                  onRegenerate={handleRegenerate}
                  onRetry={handleRetry}
                  onQuickReply={handleQuickReply}
                  suggestedFollowups={suggestedFollowups}
                  onFollowupSelect={handleQuickReply}
                  variant="cursor"
                  inPanel
                  composerSlot={isEmptyThread ? <div className="cursor-composer-shell">{composer}</div> : undefined}
                />
                {!isEmptyThread && (
                  <div className="shrink-0 px-3 pb-3 pt-1">
                    <div className="cursor-composer-shell">{composer}</div>
                  </div>
                )}
              </>
            ) : (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
                <p className="text-[12px] text-muted-foreground">
                  {sessions.length === 0 ? 'Start your first chat.' : 'Pick a chat from history.'}
                </p>
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground hover:opacity-90"
                >
                  New chat
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
