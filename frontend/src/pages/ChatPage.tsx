import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChatSidebar } from '@/components/Chat/ChatSidebar';
import { ChatMessageList } from '@/components/Chat/ChatMessageList';
import { ChatInput } from '@/components/Chat/ChatInput';
import {
  createSession,
  listSessions,
  listChatTools,
  getSession,
  deleteSession,
  deleteAllSessions,
  sendMessage,
  patchUserMessage,
  patchSessionTitle,
  regenerateAssistant,
  type ChatSession,
  type ChatMessage,
  type ChatDitaGenerationOptions,
  type ChatAgentExecution,
  type ChatAgentPlan,
  type ChatApprovalState,
  type ChatToolCatalogItem,
  type ChatToolIntent,
} from '@/api/chat';
import { apiUrl } from '@/utils/api';
import { useAppFeedback } from '@/components/feedback/useAppFeedback';
import type { AuthoringVisualContext } from '@/components/Authoring/AuthoringGenerationSplitReview';
import type { ChatToolsStatus } from '@/components/Chat/toolCatalogStateUtils';
import { resolvePendingWorkflowGuideWithKey } from '@/components/Chat/pendingWorkflowUtils';

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
  const [chatTools, setChatTools] = useState<ChatToolCatalogItem[]>([]);
  const [chatToolsStatus, setChatToolsStatus] = useState<ChatToolsStatus>('idle');
  const [chatToolsErrorMessage, setChatToolsErrorMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const chatToolsLoadPromiseRef = useRef<Promise<void> | null>(null);
  const previousBackendReachableRef = useRef<boolean | null>(null);
  const lastAuthoringRegenOptionsRef = useRef<ChatDitaGenerationOptions | null>(null);
  const authoringPreviewObjectUrlRef = useRef<string | null>(null);
  const [authoringVisualContext, setAuthoringVisualContext] = useState<AuthoringVisualContext | null>(null);

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

  const revokeAuthoringScreenshotPreview = useCallback(() => {
    if (authoringPreviewObjectUrlRef.current) {
      URL.revokeObjectURL(authoringPreviewObjectUrlRef.current);
      authoringPreviewObjectUrlRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      revokeAuthoringScreenshotPreview();
    };
  }, [revokeAuthoringScreenshotPreview]);

  useEffect(() => {
    revokeAuthoringScreenshotPreview();
    setAuthoringVisualContext(null);
  }, [currentSession?.id, revokeAuthoringScreenshotPreview]);

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

  const loadChatTools = useCallback(async () => {
    if (chatToolsLoadPromiseRef.current) {
      return chatToolsLoadPromiseRef.current;
    }

    setChatToolsStatus('loading');
    setChatToolsErrorMessage(null);

    const request = (async () => {
      try {
        const { tools } = await listChatTools();
        setChatTools(tools || []);
        setChatToolsStatus('ready');
        setChatToolsErrorMessage(null);
      } catch (error) {
        const message =
          error instanceof Error && error.message.trim()
            ? error.message.trim()
            : 'The backend responded, but the tool catalog request failed.';
        setChatToolsStatus('error');
        setChatToolsErrorMessage(message);
      } finally {
        chatToolsLoadPromiseRef.current = null;
      }
    })();

    chatToolsLoadPromiseRef.current = request;
    return request;
  }, []);

  /** Probe on mount; keep retrying every 4s until the API responds (covers slow backend / start order). */
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
        if (chatToolsStatus !== 'ready') {
          void loadChatTools();
        }
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [chatToolsStatus, checkBackend, loadChatTools]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    void loadChatTools();
  }, [loadChatTools]);

  useEffect(() => {
    const previous = previousBackendReachableRef.current;
    previousBackendReachableRef.current = backendReachable;
    if (
      backendReachable === true &&
      previous !== true &&
      (chatToolsStatus === 'idle' || chatToolsStatus === 'error')
    ) {
      void loadChatTools();
    }
  }, [backendReachable, chatToolsStatus, loadChatTools]);

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

  // Ctrl+Shift+N / Cmd+Shift+N → new chat
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
      loadSession(id);
      setStreamingContent(null);
      setStreamingToolResults(null);
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
        setStreamingToolResults(null);
        setGenerationRunId(null);
        const regenOpts = lastAuthoringRegenOptionsRef.current;
        lastAuthoringRegenOptionsRef.current = null;
        void (async () => {
          await loadSession(sessionId);
          if (regenOpts) {
            setAuthoringVisualContext((prev) => (prev ? { ...prev, generationOptions: regenOpts } : prev));
          }
        })();
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
        const label =
          name === 'generate_dita'
            ? 'Generating DITA...'
            : name === 'create_job'
              ? 'Creating job...'
              : `Using ${name}...`;
        setStreamingContent((prev) => (prev || '') + `\n\n_(${label})_`);
      },
      onGrounding: (grounding) => {
        setStreamingToolResults((prev) => ({
          ...(prev || {}),
          _grounding: grounding,
        }));
      },
      onError: (msg: string) => {
        lastAuthoringRegenOptionsRef.current = null;
        setStreamingContent(null);
        setStreamingToolResults(null);
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

  const submitTurn = useCallback(async (
    content: string,
    options?: {
      toolIntent?: ChatToolIntent;
      attachments?: { imageFile?: File | null; referenceDitaFile?: File | null };
      generationOptions?: ChatDitaGenerationOptions;
      jiraContext?: string;
    }
  ) => {
    const trimmed = content.trim();
    if (!trimmed || !currentSession) return;
    const toolIntent = options?.toolIntent;
    const attachments = options?.attachments;
    const generationOptions = options?.generationOptions;
    const jiraContext = options?.jiraContext;
    if (attachments?.imageFile) {
      revokeAuthoringScreenshotPreview();
      const url = URL.createObjectURL(attachments.imageFile);
      authoringPreviewObjectUrlRef.current = url;
      setAuthoringVisualContext({
        screenshotObjectUrl: url,
        screenshotFileName: attachments.imageFile.name,
        referenceFileName: attachments.referenceDitaFile?.name ?? null,
        generationOptions: generationOptions ?? null,
      });
    } else if (!toolIntent) {
      revokeAuthoringScreenshotPreview();
      setAuthoringVisualContext(null);
    }
    if (!toolIntent) {
      setInput('');
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setStreamingContent('');
    setStreamingToolResults({});

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
      tool_results: attachments?.imageFile
        ? {
            _attachments: [
              {
                kind: 'image',
                filename: attachments.imageFile.name,
                mime_type: attachments.imageFile.type,
                size_bytes: attachments.imageFile.size,
              },
              ...(attachments.referenceDitaFile
                ? [
                    {
                      kind: 'reference_dita',
                      filename: attachments.referenceDitaFile.name,
                      mime_type: attachments.referenceDitaFile.type,
                      size_bytes: attachments.referenceDitaFile.size,
                    },
                  ]
                : []),
            ],
            _generation_options: generationOptions || {},
            ...(jiraContext?.trim() ? { _jira_context: jiraContext.trim() } : {}),
          }
        : undefined,
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
        toolIntent,
        attachments,
        generationOptions,
        jiraContext: jiraContext?.trim() || undefined,
        signal: ac.signal,
      });
    } catch (e) {
      if (isAbortError(e)) {
        await loadSession(currentSession.id);
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
  }, [
    currentSession,
    loadSession,
    location.pathname,
    humanPrompts,
    streamCallbacks,
    revokeAuthoringScreenshotPreview,
  ]);

  const handleSend = useCallback(async () => {
    await submitTurn(input);
  }, [input, submitTurn]);

  const handleQuickReply = useCallback(async (reply: string) => {
    setInput('');
    await submitTurn(reply);
  }, [submitTurn]);

  const handleSendTool = useCallback(async (payload: { displayText: string; toolIntent: ChatToolIntent }) => {
    await submitTurn(payload.displayText, { toolIntent: payload.toolIntent });
  }, [submitTurn]);

  const handleSendAuthoring = useCallback(async (payload: {
    content: string;
    jiraContext?: string;
    attachments: { imageFile: File; referenceDitaFile?: File | null };
    generationOptions: ChatDitaGenerationOptions;
  }) => {
    await submitTurn(payload.content, {
      attachments: payload.attachments,
      generationOptions: payload.generationOptions,
      jiraContext: payload.jiraContext,
    });
  }, [submitTurn]);

  const runRegenerateStream = useCallback(async (generationOptions?: ChatDitaGenerationOptions) => {
    if (!currentSession) return;
    if (generationOptions) {
      lastAuthoringRegenOptionsRef.current = generationOptions;
    } else {
      lastAuthoringRegenOptionsRef.current = null;
    }
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
    const cbs = streamCallbacks(currentSession.id);
    try {
      await regenerateAssistant(currentSession.id, cbs, {
        context,
        humanPrompts,
        signal: ac.signal,
        ...(generationOptions ? { generationOptions } : {}),
      });
    } catch (e) {
      if (isAbortError(e)) {
        lastAuthoringRegenOptionsRef.current = null;
        await loadSession(currentSession.id);
        return;
      }
      lastAuthoringRegenOptionsRef.current = null;
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
  }, [currentSession, loadSession, location.pathname, humanPrompts, streamCallbacks]);

  const handleRegenerate = useCallback(() => {
    void runRegenerateStream();
  }, [runRegenerateStream]);

  const handleRegenerateAuthoring = useCallback(
    (opts: ChatDitaGenerationOptions) => {
      void runRegenerateStream(opts);
    },
    [runRegenerateStream]
  );

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
      lastAuthoringRegenOptionsRef.current = null;
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
        // Patch already applied; show error in-thread only — do not rethrow (closes edit UI).
      } finally {
        setLoading(false);
        setStreamingContent(null);
        setStreamingToolResults(null);
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
    <div className="flex h-[calc(100dvh-10.5rem)] min-h-[28rem] flex-col gap-3 rounded-2xl border border-slate-200/90 bg-slate-100 p-3">
      {backendReachable === false && (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 shadow-sm"
          role="alert"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="min-w-0 flex-1">
              <span className="font-semibold">{"Can't reach the API."}</span>{' '}
              This page rechecks every few seconds. Start the backend from the repo root:{' '}
              <code className="rounded border border-amber-200 bg-white px-1.5 py-0.5 font-mono text-xs">
                .\START_BACKEND_SIMPLE.ps1
              </code>{' '}
              or{' '}
              <code className="rounded border border-amber-200 bg-white px-1.5 py-0.5 font-mono text-xs">
                .\RUN_BOTH.ps1
              </code>
              . Wrong port? Set{' '}
              <code className="rounded border border-amber-200 bg-white px-1.5 py-0.5 font-mono text-xs">
                VITE_PROXY_TARGET
              </code>{' '}
              in <span className="font-mono text-xs">frontend/.env</span> and restart{' '}
              <span className="font-mono text-xs">npm run dev</span>.
            </p>
            <button
              type="button"
              className="shrink-0 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-950 shadow-sm hover:bg-amber-100"
              onClick={() => void checkBackend()}
            >
              Check now
            </button>
          </div>
        </div>
      )}
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_4px_24px_-4px_rgba(15,23,42,0.08),0_8px_32px_-8px_rgba(15,23,42,0.06)]">
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
        <div className="flex min-w-0 flex-1 flex-col bg-slate-50/50">
          {currentSession ? (
            <>
              <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-3.5">
                <div className="min-w-0 border-l-4 border-teal-500 pl-3">
                  <h2 className="truncate text-base font-semibold tracking-tight text-slate-900">
                    {currentSession.title?.trim() || 'Conversation'}
                  </h2>
                  <p className="mt-0.5 truncate text-xs text-slate-500">
                    DITA · AEM Guides · dataset generation
                  </p>
                </div>
                <Link
                  to="/settings"
                  className="shrink-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-800 transition hover:border-teal-300 hover:bg-teal-50/60"
                >
                  RAG &amp; search
                </Link>
              </div>
              <ChatMessageList
                messages={messages}
                sessionId={currentSession?.id}
                streamingContent={streamingContent}
                streamingToolResults={streamingToolResults}
                generationRunId={generationRunId}
                messagesLoading={messagesLoading}
                onGenerationComplete={() => setGenerationRunId(null)}
                onCopyMessage={handleCopyMessage}
                onExamplePromptSelect={(text) => setInput(text)}
                onSaveUserMessage={handleSaveUserMessage}
                actionDisabled={loading}
                onRegenerate={handleRegenerate}
                onRegenerateAuthoring={handleRegenerateAuthoring}
                onRetry={handleRetry}
                authoringVisualContext={authoringVisualContext}
              />
              <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3 sm:px-5">
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSend}
            onQuickReply={handleQuickReply}
            onSendTool={handleSendTool}
            onSendAuthoring={handleSendAuthoring}
            onStop={handleStop}
            tools={chatTools}
            toolsUnavailable={chatToolsStatus === 'error' || backendReachable === false}
            pendingWorkflowGuide={pendingWorkflowGuide}
            onDismissPendingWorkflowGuide={pendingWorkflowGuide ? dismissPendingWorkflowGuide : undefined}
            disabled={loading}
            loading={loading}
            streaming={streaming}
            showShortcutHint
            placeholder="Paste Jira text, ask a DITA question, or request a dataset job..."
          />
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center text-slate-600">
              {sessions.length === 0 ? (
                <>
                  <div className="rounded-2xl border border-teal-100 bg-gradient-to-b from-white to-teal-50/40 px-8 py-8 shadow-md shadow-slate-900/5">
                    <p className="text-sm font-semibold text-slate-900">No conversations yet</p>
                    <p className="mt-2 max-w-sm text-sm leading-6 text-slate-600">
                      Start a chat to ask about DITA, AEM Guides, or generate content from Jira.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleNewChat}
                    className="rounded-full bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-teal-900/20 transition hover:bg-teal-700 hover:-translate-y-0.5"
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
