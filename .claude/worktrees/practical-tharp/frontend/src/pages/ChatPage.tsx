import { useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Bot,
  BrainCircuit,
  FileCode2,
  MessageSquare,
  SearchCheck,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { ChatSidebar } from '@/components/Chat/ChatSidebar';
import { ChatMessageList } from '@/components/Chat/ChatMessageList';
import { ChatInput } from '@/components/Chat/ChatInput';
import { Button } from '@/components/ui/button';
import {
  branchSessionFromMessage,
  createSession,
  listSessions,
  getSession,
  deleteSession,
  sendMessage,
  type ChatSession,
  type ChatMessage,
  type ChatNotice,
} from '@/api/chat';
import { apiUrl, getTenantId } from '@/utils/api';

interface PromptCard {
  title: string;
  description: string;
  prompt: string;
  icon: typeof Sparkles;
}

interface EditingDraft {
  messageId: string;
  originalContent: string;
  previousComposerValue: string;
}

const PROMPT_CARDS: PromptCard[] = [
  {
    title: 'Summarize Jira discussion',
    description: 'Turn issue description and comments into clean author guidance.',
    prompt:
      'Summarize the Jira issue and comments into production-ready author guidance, then list the user-facing resolution steps.',
    icon: MessageSquare,
  },
  {
    title: 'Review DITA reuse',
    description: 'Ask for conref, conkeyref, keyref, and keyword improvements.',
    prompt:
      'Review this DITA topic for title conref, conkeyref, keyref, keyword metadata, and general reusability improvements.',
    icon: FileCode2,
  },
  {
    title: 'Research with examples',
    description: 'Blend tenant RAG, Oxygen examples, and AEM Guides knowledge.',
    prompt:
      'Research this topic using AEM Guides knowledge, tenant examples, and Oxygen DITA examples, then recommend the best structure.',
    icon: SearchCheck,
  },
  {
    title: 'Refine for production',
    description: 'Push a draft closer to publishable documentation.',
    prompt:
      'Refine this draft so it reads like production documentation, improves structure, and removes Jira bug-report phrasing.',
    icon: Wand2,
  },
];

function toAssistantErrorMessage(message: string): string {
  const cleaned = (message || '').trim();
  if (!cleaned) {
    return 'Assistant is temporarily unavailable.';
  }
  if (
    /rate-limited|rate limit|insufficient_quota|quota is exhausted|temporarily unavailable|try again in a moment/i.test(
      cleaned
    )
  ) {
    return 'Assistant is temporarily busy. Try again in a few minutes, or use one of the guided prompts below.';
  }
  if (
    /^assistant\b/i.test(cleaned) ||
    /^openai\b/i.test(cleaned) ||
    /^groq\b/i.test(cleaned) ||
    /^anthropic\b/i.test(cleaned) ||
    /^aws bedrock\b/i.test(cleaned)
  ) {
    return cleaned;
  }
  return `Assistant unavailable: ${cleaned}`;
}

function detectIssueKey(text: string): string | undefined {
  return text.match(/\b[A-Z][A-Z0-9]+-\d+\b/)?.[0];
}

function toSessionTitle(text: string): string {
  const trimmed = (text || '').trim();
  if (!trimmed) {
    return 'New Chat';
  }
  return trimmed.length > 80 ? `${trimmed.slice(0, 80)}...` : trimmed;
}

function buildChatSuggestions(input: string, hasMessages: boolean): string[] {
  const trimmed = input.trim();
  if (/<(task|concept|reference|topic|glossentry)\b/i.test(trimmed)) {
    return [
      'Suggest conref, conkeyref, keyref, and keyword improvements for this XML.',
      'Rewrite the title and shortdesc so they sound like production docs.',
      'Point out any missing reusable content or weak DITA structures.',
      'Recommend how to make this topic more AEM Guides ready.',
    ];
  }
  if (detectIssueKey(trimmed) || /\bcomment\b/i.test(trimmed)) {
    return [
      'Summarize the Jira comments into author-ready guidance.',
      'Convert this Jira issue into a clean task topic outline.',
      'List the likely user-facing resolution from the description and comments.',
      'Recommend follow-up research queries before writing the topic.',
    ];
  }
  if (hasMessages) {
    return [
      'Suggest how to make the answer more reusable across topics.',
      'Give me a cleaner DITA structure for this.',
      'Recommend conref and keyref opportunities.',
      'Turn this into authoring next steps.',
    ];
  }
  return PROMPT_CARDS.map((card) => card.prompt);
}

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
  const [editingDraft, setEditingDraft] = useState<EditingDraft | null>(null);
  const [chatNotice, setChatNotice] = useState<ChatNotice | null>(null);
  const tenantId = getTenantId();

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

  const createAndLoadSession = useCallback(async (): Promise<string | null> => {
    setCreatingSession(true);
    try {
      const { session_id } = await createSession();
      await loadSessions();
      await loadSession(session_id);
      setStreamingContent(null);
      return session_id;
    } catch (e) {
      console.error('Create session failed:', e);
      return null;
    } finally {
      setCreatingSession(false);
    }
  }, [loadSessions, loadSession]);

  useEffect(() => {
    fetch(apiUrl('/api/v1/limits'))
      .then((r) => setBackendReachable(r.ok))
      .catch(() => setBackendReachable(false));
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleNewChat = useCallback(async () => {
    const sessionId = await createAndLoadSession();
    if (sessionId) {
      setInput('');
      setEditingDraft(null);
      setChatNotice(null);
    }
  }, [createAndLoadSession]);

  const handleSelectSession = useCallback(
    (id: string) => {
      loadSession(id);
      setStreamingContent(null);
      setEditingDraft(null);
      setChatNotice(null);
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
          setEditingDraft(null);
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

  const handleEditMessage = useCallback(
    (message: ChatMessage) => {
      const content = (message.content || '').trim();
      if (!content) {
        return;
      }
      setEditingDraft({
        messageId: message.id,
        originalContent: content,
        previousComposerValue: input,
      });
      setInput(content);
    },
    [input]
  );

  const handleCancelEdit = useCallback(() => {
    setInput(editingDraft?.previousComposerValue || '');
    setEditingDraft(null);
  }, [editingDraft]);

  const handleSuggestionPick = useCallback(
    async (prompt: string) => {
      if (!currentSession) {
        await createAndLoadSession();
      }
      setEditingDraft(null);
      setInput(prompt);
    },
    [currentSession, createAndLoadSession]
  );

  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || !currentSession) return;
    setLoading(true);
    setStreamingContent('');
    setChatNotice(null);
    const pendingEdit = editingDraft;
    let targetSession = currentSession;
    let nextMessages = messages;
    let composerCleared = false;

    try {
      if (pendingEdit) {
        const branched = await branchSessionFromMessage(currentSession.id, pendingEdit.messageId);
        const optimisticSession: ChatSession = {
          ...branched.session,
          title: toSessionTitle(content),
          updated_at: new Date().toISOString(),
        };
        targetSession = optimisticSession;
        nextMessages = branched.messages;
        setCurrentSession(optimisticSession);
        setMessages(branched.messages);
        setSessions((prev) => [optimisticSession, ...prev.filter((session) => session.id !== optimisticSession.id)]);
        setEditingDraft(null);
        await loadSessions();
      }

      setInput('');
      composerCleared = true;
      const userMsg: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      };
      setMessages([...nextMessages, userMsg]);

      const issueKey = detectIssueKey(content);
      const context = {
        source_page: location.pathname || '/chat',
        issue_key: issueKey,
      };
      await sendMessage(
        targetSession.id,
        content,
        {
          onChunk: (chunk) => {
            setStreamingContent((prev) => (prev || '') + chunk);
          },
          onDone: () => {
            setStreamingContent(null);
            setGenerationRunId(null);
            void loadSessions();
            void loadSession(targetSession.id);
          },
          onToolStart: (name, runId) => {
            if (name === 'generate_dita' && runId) {
              setGenerationRunId(runId);
            }
          },
          onTool: (name) => {
            const label =
              name === 'generate_dita'
                ? 'Generating DITA...'
                : name === 'create_job'
                  ? 'Creating job...'
                  : `Using ${name}...`;
            setStreamingContent((prev) => (prev || '') + `\n\n_(${label})_`);
          },
          onNotice: (notice) => {
            setChatNotice(notice);
          },
          onError: (msg) => {
            setStreamingContent(null);
            setGenerationRunId(null);
            setChatNotice(null);
            setMessages((prev) => [
              ...prev,
              {
                id: `err-${Date.now()}`,
                role: 'assistant',
                content: toAssistantErrorMessage(msg),
                created_at: new Date().toISOString(),
              },
            ]);
          },
        },
        context
      );
    } catch (e) {
      setStreamingContent(null);
      setGenerationRunId(null);
      setChatNotice(null);
      if (pendingEdit && composerCleared) {
        setInput(content);
        setEditingDraft(pendingEdit);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: toAssistantErrorMessage(e instanceof Error ? e.message : String(e)),
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, currentSession, editingDraft, messages, loadSession, loadSessions, location.pathname]);

  const handleCopyMessage = useCallback((content: string) => {
    navigator.clipboard?.writeText(content);
  }, []);

  const handleExport = useCallback(
    async (sessionId: string) => {
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) return;
      const msgs = currentSession?.id === sessionId ? messages : (await getSession(sessionId)).messages;
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

  const quickSuggestions = buildChatSuggestions(input, messages.length > 0);

  const emptyState = (
    <div className="mx-auto flex h-full w-full max-w-5xl flex-col items-center justify-center px-6 py-10">
      <div className="max-w-2xl text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-100 text-blue-700">
          <Bot className="h-6 w-6" />
        </div>
        <h3 className="mt-4 text-2xl font-semibold text-slate-900">Start with a stronger prompt</h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Ask for Jira-comment summaries, DITA refinement, reuse opportunities, or research-backed structure
          suggestions.
        </p>
      </div>
      <div className="mt-6 grid w-full gap-4 md:grid-cols-2">
        {PROMPT_CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <button
              key={card.title}
              type="button"
              onClick={() => handleSuggestionPick(card.prompt)}
              className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <div className="font-semibold text-slate-900">{card.title}</div>
                  <div className="mt-1 text-sm text-slate-600">{card.description}</div>
                </div>
              </div>
              <div className="mt-4 text-xs font-medium text-blue-700">Use this prompt</div>
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="flex min-h-[calc(100vh-13rem)] flex-col gap-4">
      {backendReachable === false && (
        <div
          className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800"
          role="alert"
        >
          <strong>Backend unreachable.</strong> Start the backend with{' '}
          <code className="rounded bg-red-100 px-1.5 py-0.5">.\START_BACKEND_SIMPLE.ps1</code> or{' '}
          <code className="rounded bg-red-100 px-1.5 py-0.5">.\RUN_BOTH.ps1</code> from the project root.
        </div>
      )}

      <section className="rounded-3xl border border-slate-200 bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_52%,#f8fafc_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">
              <Sparkles className="h-3.5 w-3.5" />
              AI Chat
            </div>
            <h1 className="mt-3 text-3xl font-bold text-slate-950">Research, author, and refine in one place</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
              Use tenant RAG, Oxygen examples, Jira context, and authoring knowledge together. This workspace is best
              for comment summaries, DITA coaching, reuse guidance, and draft refinement.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-medium">
            <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700">
              Workspace: {tenantId}
            </span>
            <span
              className={`rounded-full border px-3 py-1.5 ${
                backendReachable === false
                  ? 'border-red-200 bg-red-50 text-red-700'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-700'
              }`}
            >
              {backendReachable === false ? 'Backend offline' : 'RAG connected'}
            </span>
            <span className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-violet-700">
              Jira-aware prompts
            </span>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-white/80 bg-white/80 p-4">
            <BrainCircuit className="h-5 w-5 text-blue-700" />
            <h2 className="mt-3 font-semibold text-slate-900">Smarter guidance</h2>
            <p className="mt-1 text-sm text-slate-600">
              Ask for conref, conkeyref, keyref, keyword, and reuse improvements.
            </p>
          </div>
          <div className="rounded-2xl border border-white/80 bg-white/80 p-4">
            <MessageSquare className="h-5 w-5 text-emerald-700" />
            <h2 className="mt-3 font-semibold text-slate-900">Jira discussion aware</h2>
            <p className="mt-1 text-sm text-slate-600">
              Pull issue discussion into cleaner author intent instead of relying on the title alone.
            </p>
          </div>
          <div className="rounded-2xl border border-white/80 bg-white/80 p-4">
            <FileCode2 className="h-5 w-5 text-violet-700" />
            <h2 className="mt-3 font-semibold text-slate-900">Authoring coach</h2>
            <p className="mt-1 text-sm text-slate-600">
              Refine XML, compare DITA types, and get research-backed draft improvements.
            </p>
          </div>
        </div>
      </section>

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
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
        <div className="flex min-w-0 flex-1 flex-col bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)]">
          {currentSession ? (
            <>
              <div className="border-b border-slate-200 bg-white/80 px-5 py-4 backdrop-blur-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Active conversation
                    </div>
                    <h2 className="mt-1 text-xl font-semibold text-slate-900">
                      {currentSession.title || 'New Chat'}
                    </h2>
                    <p className="mt-1 text-sm text-slate-600">
                      Ask for Jira comment summaries, DITA structure advice, authoring refinement, or reuse guidance.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                    Best results come from including the issue key, XML, or the draft you want improved.
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {quickSuggestions.slice(0, 4).map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => handleSuggestionPick(suggestion)}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
              {chatNotice && (
                <div className="border-b border-amber-200 bg-amber-50/80 px-5 py-3 text-sm text-amber-950">
                  <div className="flex flex-col gap-1 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="font-semibold">
                        {chatNotice.title || 'Live AI provider is temporarily limited'}
                      </div>
                      <div className="text-amber-900/90">
                        {chatNotice.message || 'Showing the best available local response for this reply.'}
                      </div>
                    </div>
                    <div className="text-xs font-medium uppercase tracking-[0.16em] text-amber-700">
                      {chatNotice.code === 'provider_rate_limited'
                        ? 'Provider Rate-Limited'
                        : chatNotice.code === 'provider_quota_exhausted'
                          ? 'Provider Quota Exhausted'
                          : 'Local Fallback Active'}
                    </div>
                  </div>
                </div>
              )}
              <ChatMessageList
                messages={messages}
                streamingContent={streamingContent}
                generationRunId={generationRunId}
                onGenerationComplete={() => setGenerationRunId(null)}
                onCopyMessage={handleCopyMessage}
                onEditMessage={handleEditMessage}
                editingMessageId={editingDraft?.messageId ?? null}
                emptyState={emptyState}
              />
              <div className="border-t border-slate-200 bg-white/90 p-4 backdrop-blur-sm">
                <ChatInput
                  value={input}
                  onChange={setInput}
                  onSend={handleSend}
                  disabled={loading}
                  loading={loading}
                  placeholder={
                    editingDraft
                      ? 'Update the earlier prompt, then resend to continue from that point...'
                      : 'Ask about DITA, paste Jira details, or request a stronger reusable draft...'
                  }
                  helperText={
                    editingDraft
                      ? 'Resend will create a fresh branch from the edited prompt. Enter sends, Shift+Enter adds a new line.'
                      : 'Use issue keys, XML, or Jira comments for stronger answers. Enter sends, Shift+Enter adds a new line.'
                  }
                  suggestions={quickSuggestions}
                  onSuggestionClick={handleSuggestionPick}
                  modeLabel={editingDraft ? 'Editing earlier prompt' : null}
                  modeDescription={
                    editingDraft
                      ? 'This keeps the original conversation intact and continues in a new branch, like ChatGPT-style edit and resend.'
                      : undefined
                  }
                  onCancelMode={handleCancelEdit}
                  sendLabel={editingDraft ? 'Resend' : 'Send'}
                  focusKey={editingDraft?.messageId ?? null}
                />
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center p-6">
              <div className="w-full max-w-4xl rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
                <div className="text-center">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100 text-blue-700">
                    <Bot className="h-7 w-7" />
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold text-slate-900">Create a chat to start working</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    Open a fresh session, then ask for Jira comment summaries, DITA reuse suggestions, or draft
                    improvements grounded in tenant knowledge.
                  </p>
                  <Button onClick={handleNewChat} className="mt-5">
                    Start New Chat
                  </Button>
                </div>
                <div className="mt-8 grid gap-4 md:grid-cols-2">
                  {PROMPT_CARDS.map((card) => {
                    const Icon = card.icon;
                    return (
                      <button
                        key={card.title}
                        type="button"
                        onClick={() => handleSuggestionPick(card.prompt)}
                        className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-left transition hover:border-blue-200 hover:bg-blue-50"
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-blue-700 shadow-sm">
                            <Icon className="h-5 w-5" />
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900">{card.title}</div>
                            <div className="mt-1 text-sm text-slate-600">{card.description}</div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
