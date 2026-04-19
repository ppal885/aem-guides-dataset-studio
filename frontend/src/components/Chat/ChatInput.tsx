import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Send,
  Loader2,
  Square,
  Search,
  Wand2,
  X,
  Image as ImageIcon,
  FileCode2,
  Settings2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import type { ChatDitaGenerationOptions, ChatToolCatalogItem, ChatToolIntent } from '@/api/chat';
import {
  buildAuthoringMentionCandidates,
  filterAuthoringMentionCandidates,
  getActiveAuthoringMention,
  replaceAuthoringMentionInValue,
  type AuthoringMentionCandidate,
} from '@/components/Chat/authoringMentionUtils';
import {
  resolvedAuthoringDefaults,
  writeAuthoringGenerationDefaults,
} from '@/lib/authoringGenerationDefaults';
import type { PendingWorkflowGuide } from '@/components/Chat/pendingWorkflowUtils';

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onQuickReply?: (reply: string) => void;
  onSendTool?: (payload: { displayText: string; toolIntent: ChatToolIntent }) => void;
  onSendAuthoring?: (payload: {
    content: string;
    jiraContext?: string;
    attachments: { imageFile: File; referenceDitaFile?: File | null };
    generationOptions: ChatDitaGenerationOptions;
  }) => void;
  onStop?: () => void;
  tools?: ChatToolCatalogItem[];
  toolsUnavailable?: boolean;
  disabled?: boolean;
  loading?: boolean;
  streaming?: boolean;
  placeholder?: string;
  showShortcutHint?: boolean;
  pendingWorkflowGuide?: PendingWorkflowGuide | null;
  onDismissPendingWorkflowGuide?: () => void;
}

function getPrimaryArg(tool: ChatToolCatalogItem | null): string {
  if (!tool) return '';
  if (tool.primary_arg) return tool.primary_arg;
  const props = tool.args_schema?.properties || {};
  const required = new Set(tool.args_schema?.required || []);
  for (const preferred of ['xml', 'prompt', 'text', 'query', 'attribute_name', 'job_id']) {
    if (props[preferred]) return preferred;
  }
  for (const [key, spec] of Object.entries(props)) {
    if (spec?.type === 'string' && required.has(key)) return key;
  }
  for (const [key, spec] of Object.entries(props)) {
    if (spec?.type === 'string') return key;
  }
  return '';
}

function parseFieldValue(type: string | undefined, raw: string): unknown {
  if (type === 'integer' || type === 'number') {
    if (!raw.trim()) return undefined;
    const num = Number(raw);
    return Number.isFinite(num) ? num : raw;
  }
  if (type === 'array') {
    return raw
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
  }
  if (type === 'object') {
    if (!raw.trim()) return undefined;
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  return raw;
}

function buildSlashDisplay(tool: ChatToolCatalogItem, args: Record<string, unknown>): string {
  const primaryArg = getPrimaryArg(tool);
  const headerLines = [`/${tool.slash_alias}`];
  const bodyValue =
    typeof args[primaryArg] === 'string' ? String(args[primaryArg] || '') : '';

  for (const [key, value] of Object.entries(args)) {
    if (key === primaryArg || value === undefined || value === null || value === '') continue;
    const rendered =
      Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : String(value);
    headerLines.push(`${key}: ${rendered}`);
  }

  if (bodyValue.trim()) {
    headerLines.push('');
    headerLines.push(bodyValue.trim());
  }

  return headerLines.join('\n').trim();
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onQuickReply,
  onSendTool,
  onSendAuthoring,
  onStop,
  tools = [],
  toolsUnavailable = false,
  disabled,
  loading,
  streaming,
  placeholder = 'Type your message...',
  showShortcutHint = true,
  pendingWorkflowGuide = null,
  onDismissPendingWorkflowGuide,
}: ChatInputProps) {
  const showStop = Boolean(streaming && onStop);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [selectedToolName, setSelectedToolName] = useState<string | null>(null);
  const [argValues, setArgValues] = useState<Record<string, string>>({});
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [referenceDitaFile, setReferenceDitaFile] = useState<File | null>(null);
  const [showAuthoringOptions, setShowAuthoringOptions] = useState(false);
  const [jiraExpanded, setJiraExpanded] = useState(false);
  const [jiraContext, setJiraContext] = useState('');
  const [generationOptions, setGenerationOptions] = useState<ChatDitaGenerationOptions>(() =>
    resolvedAuthoringDefaults()
  );
  const imageInputRef = useRef<HTMLInputElement>(null);
  const ditaInputRef = useRef<HTMLInputElement>(null);
  /** When picking a file from the @ menu, replace this [start, end) range with @filename. */
  const pendingAuthoringMentionRangeRef = useRef<{ start: number; end: number } | null>(null);
  const pendingCaretAfterMentionRef = useRef<number | null>(null);
  const [caretPos, setCaretPos] = useState(0);
  const [authoringMentionHighlightIdx, setAuthoringMentionHighlightIdx] = useState(0);

  const selectedTool = useMemo(
    () => tools.find((tool) => tool.name === selectedToolName) || null,
    [selectedToolName, tools]
  );
  const primaryArg = getPrimaryArg(selectedTool);

  useEffect(() => {
    const id = window.setTimeout(() => {
      writeAuthoringGenerationDefaults(generationOptions);
    }, 400);
    return () => window.clearTimeout(id);
  }, [generationOptions]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  }, [value, selectedToolName]);

  useEffect(() => {
    if (!selectedTool && value.startsWith('/')) {
      setPaletteOpen(true);
      return;
    }
    if (!value.startsWith('/')) {
      setPaletteOpen(false);
    }
  }, [selectedTool, value]);

  const slashQuery = !selectedTool && value.startsWith('/') ? value.slice(1).trim().toLowerCase() : '';
  const filteredTools = useMemo(() => {
    if (!slashQuery) return tools;
    return tools.filter((tool) => {
      const haystack = `${tool.title} ${tool.name} ${tool.slash_alias} ${tool.description} ${tool.category}`.toLowerCase();
      return haystack.includes(slashQuery);
    });
  }, [slashQuery, tools]);

  const groupedTools = useMemo(() => {
    const groups: Record<string, ChatToolCatalogItem[]> = {};
    for (const tool of filteredTools) {
      const key = tool.category || 'General';
      if (!groups[key]) groups[key] = [];
      groups[key].push(tool);
    }
    return groups;
  }, [filteredTools]);

  const valueRef = useRef(value);
  valueRef.current = value;

  const activeAuthoringMention = useMemo(() => {
    if (selectedTool || !onSendAuthoring || paletteOpen) return null;
    return getActiveAuthoringMention(value, caretPos);
  }, [selectedTool, onSendAuthoring, paletteOpen, value, caretPos]);

  const authoringMentionCandidates = useMemo(() => {
    if (!activeAuthoringMention) return [];
    return filterAuthoringMentionCandidates(
      buildAuthoringMentionCandidates(imageFile, referenceDitaFile),
      activeAuthoringMention.query
    );
  }, [activeAuthoringMention, imageFile, referenceDitaFile]);

  const mentionMenuRangeRef = useRef({ start: 0, end: 0 });
  useEffect(() => {
    if (!activeAuthoringMention) return;
    mentionMenuRangeRef.current = { start: activeAuthoringMention.start, end: caretPos };
  }, [activeAuthoringMention, caretPos]);

  useEffect(() => {
    setAuthoringMentionHighlightIdx(0);
  }, [activeAuthoringMention?.start, activeAuthoringMention?.query]);

  const showAuthoringMentionMenu = Boolean(activeAuthoringMention && !paletteOpen);

  useLayoutEffect(() => {
    const pos = pendingCaretAfterMentionRef.current;
    if (pos == null) return;
    pendingCaretAfterMentionRef.current = null;
    const ta = textareaRef.current;
    if (ta) {
      ta.focus();
      const len = value.length;
      const safe = Math.min(Math.max(0, pos), len);
      ta.setSelectionRange(safe, safe);
      setCaretPos(safe);
    }
  }, [value]);

  const applyAuthoringMentionInsert = useCallback((range: { start: number; end: number }, fileName: string) => {
    const { nextValue, caretAfter } = replaceAuthoringMentionInValue(valueRef.current, range, fileName);
    pendingCaretAfterMentionRef.current = caretAfter;
    onChange(nextValue);
  }, [onChange]);

  const selectAuthoringMentionCandidate = useCallback(
    (candidate: AuthoringMentionCandidate) => {
      const active = getActiveAuthoringMention(valueRef.current, caretPos);
      const range = active
        ? { start: active.start, end: caretPos }
        : mentionMenuRangeRef.current;

      if (candidate.type === 'attachment' && !active) return;

      if (candidate.type === 'action') {
        if (candidate.kind === 'pick-image') {
          pendingAuthoringMentionRangeRef.current = range;
          imageInputRef.current?.click();
          return;
        }
        if (candidate.kind === 'pick-dita') {
          pendingAuthoringMentionRangeRef.current = range;
          ditaInputRef.current?.click();
          return;
        }
        return;
      }

      if (candidate.type === 'attachment') {
        applyAuthoringMentionInsert(range, candidate.fileName);
      }
    },
    [caretPos, applyAuthoringMentionInsert]
  );

  const additionalFields = useMemo(() => {
    if (!selectedTool) return [];
    const props = selectedTool.args_schema?.properties || {};
    return Object.entries(props).filter(([key]) => key !== primaryArg);
  }, [primaryArg, selectedTool]);

  const requiredFields = useMemo(() => selectedTool?.args_schema?.required || [], [selectedTool]);
  const primaryArgRequired = Boolean(primaryArg && requiredFields.includes(primaryArg));
  const missingRequiredFields = useMemo(() => {
    if (!selectedTool) return [] as string[];
    const missing: string[] = [];
    for (const key of requiredFields) {
      if (key === primaryArg) {
        if (!value.trim()) missing.push(key);
        continue;
      }
      if (!(argValues[key] || '').trim()) missing.push(key);
    }
    return missing;
  }, [argValues, primaryArg, requiredFields, selectedTool, value]);

  const missingRequired = useMemo(() => {
    if (!selectedTool) return false;
    return missingRequiredFields.length > 0;
  }, [missingRequiredFields, selectedTool]);

  const canSendTool = Boolean(selectedTool && !missingRequired && !loading && !disabled && !showStop);
  const canSendText = Boolean(!selectedTool && value.trim() && !loading && !disabled && !showStop);
  const canSendAuthoring = Boolean(
    !selectedTool && onSendAuthoring && imageFile && value.trim() && !loading && !disabled && !showStop
  );

  const selectTool = (tool: ChatToolCatalogItem) => {
    setSelectedToolName(tool.name);
    setPaletteOpen(false);
    setArgValues({});
    onChange('');
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const clearTool = () => {
    setSelectedToolName(null);
    setArgValues({});
    setPaletteOpen(false);
    onChange('');
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleSendClick = () => {
    if (selectedTool && onSendTool) {
      const args: Record<string, unknown> = {};
      const props = selectedTool.args_schema?.properties || {};
      if (primaryArg && value.trim()) {
        const primaryType = props[primaryArg]?.type;
        args[primaryArg] = parseFieldValue(primaryType, value.trim());
      }
      for (const [key, raw] of Object.entries(argValues)) {
        if (!raw.trim()) continue;
        args[key] = parseFieldValue(props[key]?.type, raw);
      }
      const displayText = buildSlashDisplay(selectedTool, args);
      onSendTool({
        displayText,
        toolIntent: {
          name: selectedTool.name,
          args,
          source: 'slash',
        },
      });
      clearTool();
      return;
    }
    if (!selectedTool && imageFile && onSendAuthoring) {
      onSendAuthoring({
        content: value.trim(),
        jiraContext: jiraContext.trim() || undefined,
        attachments: {
          imageFile,
          referenceDitaFile,
        },
        generationOptions: {
          dita_type: generationOptions.dita_type || undefined,
          save_path: generationOptions.save_path?.trim() || undefined,
          file_name: generationOptions.file_name?.trim() || undefined,
          strict_validation: generationOptions.strict_validation ?? true,
          style_strictness: generationOptions.style_strictness,
          preserve_prolog: generationOptions.preserve_prolog,
          xref_placeholders: generationOptions.xref_placeholders,
          auto_ids: generationOptions.auto_ids,
          output_mode: generationOptions.output_mode,
          authoring_pattern: generationOptions.authoring_pattern,
          preserve_reference_doctype: generationOptions.preserve_reference_doctype,
          screenshot_deliverable: generationOptions.screenshot_deliverable,
        },
      });
      setImageFile(null);
      setReferenceDitaFile(null);
      setShowAuthoringOptions(false);
      setJiraContext('');
      setGenerationOptions(resolvedAuthoringDefaults());
      return;
    }
    onSend();
  };

  const activeGuide = !selectedTool ? pendingWorkflowGuide : null;

  useEffect(() => {
    if (!activeGuide || !onDismissPendingWorkflowGuide) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (e.defaultPrevented) return;
      onDismissPendingWorkflowGuide();
      e.preventDefault();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeGuide, onDismissPendingWorkflowGuide]);
  const showAuthoringCard = !selectedTool && (!activeGuide || showAuthoringOptions || Boolean(imageFile) || Boolean(referenceDitaFile) || Boolean(jiraContext.trim()));
  const mainPlaceholder = activeGuide ? activeGuide.placeholder : placeholder;
  const helperText = selectedTool
    ? `/${selectedTool.slash_alias} - ${selectedTool.description}`
    : activeGuide
      ? ''
      : imageFile
        ? generationOptions.screenshot_deliverable === 'map_hierarchy'
          ? 'Map from diagram: vision reads hierarchy boxes (concept/task/reference), then generates a .ditamap with nested topicrefs and stub .dita files. Use a clear structure screenshot.'
          : 'Screenshot + prompt will run the staged DITA authoring pipeline: image understanding, semantic plan, XML render, validation, optional repair, then optional save. Type @ in the prompt to attach or mention files.'
        : toolsUnavailable
          ? 'Slash tools are unavailable because the backend tool catalog could not be loaded.'
          : showShortcutHint
            ? 'Type / to open the full tool palette.'
            : '';

  const handleSuggestedReplyClick = useCallback((reply: string) => {
    if (onQuickReply && !disabled && !loading && !showStop) {
      onQuickReply(reply);
      return;
    }
    onChange(reply);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      const length = reply.length;
      textareaRef.current?.setSelectionRange(length, length);
    });
  }, [disabled, loading, onChange, onQuickReply, showStop]);

  return (
    <div className="relative flex min-h-0 flex-col gap-3">
      <div className="flex max-h-[min(42vh,28rem)] flex-col gap-3 overflow-y-auto pr-1">
        {activeGuide && (
          <div
            className={`rounded-xl border px-4 py-3.5 shadow-sm ring-1 ring-slate-900/5 ${
              activeGuide.kind === 'review'
                ? 'border-amber-200 bg-amber-50/90'
                : 'border-teal-200 bg-teal-50/80'
            }`}
            role="region"
            aria-label={activeGuide.title}
          >
            <div className="flex items-start justify-between gap-2">
              <p
                className={`min-w-0 text-xs font-semibold ${
                  activeGuide.kind === 'review' ? 'text-amber-950' : 'text-teal-950'
                }`}
              >
                {activeGuide.title}
              </p>
              {onDismissPendingWorkflowGuide && (
                <button
                  type="button"
                  onClick={onDismissPendingWorkflowGuide}
                  className={`shrink-0 rounded-lg p-1.5 transition hover:bg-black/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/50 ${
                    activeGuide.kind === 'review' ? 'text-amber-900/80' : 'text-teal-900/80'
                  }`}
                  aria-label="Dismiss workflow prompt"
                  title="Dismiss (Esc)"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-800">{activeGuide.helper}</p>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{activeGuide.detail}</p>
            {activeGuide.suggestedReplies.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {activeGuide.suggestedReplies.map((reply, idx) => (
                  <button
                    key={reply}
                    type="button"
                    onClick={() => handleSuggestedReplyClick(reply)}
                    className={
                      idx === 0
                        ? 'rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-teal-800'
                        : 'rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm transition hover:border-slate-300 hover:bg-slate-50'
                    }
                  >
                    {reply}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {showAuthoringCard && (
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/[0.04]">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold tracking-tight text-slate-900">Screenshot → DITA</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Add a <strong className="font-medium text-slate-800">screenshot</strong>, then describe the topic in the box below. Optional: a reference{' '}
                <span className="font-mono text-[0.8125rem] text-slate-700">.dita</span> for layout — type{' '}
                <kbd className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-xs text-slate-800">@</kbd> to pick files.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 shrink-0"
              onClick={() => setShowAuthoringOptions((prev) => !prev)}
            >
              <Settings2 className="mr-1.5 h-3.5 w-3.5" />
              {showAuthoringOptions ? 'Hide options' : 'Options'}
            </Button>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-9 border-slate-200"
              onClick={() => {
                pendingAuthoringMentionRangeRef.current = null;
                imageInputRef.current?.click();
              }}
            >
              <ImageIcon className="mr-1.5 h-3.5 w-3.5" />
              {imageFile ? 'Replace screenshot' : 'Attach screenshot'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-9 border-slate-200"
              onClick={() => {
                pendingAuthoringMentionRangeRef.current = null;
                ditaInputRef.current?.click();
              }}
            >
              <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
              {referenceDitaFile ? 'Replace reference DITA' : 'Attach reference DITA'}
            </Button>
          </div>

          <div className="mt-3">
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-left text-sm font-medium text-slate-800 transition hover:bg-slate-100/80"
              onClick={() => setJiraExpanded((e) => !e)}
              aria-expanded={jiraExpanded}
            >
              {jiraExpanded ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" />
              )}
              <span>Ticket / Jira context (optional)</span>
              {jiraContext.trim() ? (
                <span className="ml-auto text-xs font-normal text-teal-800">Filled</span>
              ) : (
                <span className="ml-auto text-xs font-normal text-slate-500">Collapsed — expand to paste</span>
              )}
            </button>
            {jiraExpanded && (
              <label className="mt-2 flex flex-col gap-1.5">
                <span className="sr-only">Ticket or Jira text</span>
                <textarea
                  value={jiraContext}
                  onChange={(e) => setJiraContext(e.target.value)}
                  placeholder="Summary, acceptance criteria, or steps — used only for generation (not sent as a visible chat message)."
                  rows={3}
                  className="resize-y rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/25"
                />
              </label>
            )}
          </div>

          {(imageFile || referenceDitaFile) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {imageFile && (
                <div className="inline-flex items-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs text-teal-900">
                  <ImageIcon className="h-3.5 w-3.5" />
                  <span className="max-w-[18rem] truncate">{imageFile.name}</span>
                  <button
                    type="button"
                    className="rounded-full p-0.5 text-teal-700 hover:bg-teal-100"
                    onClick={() => setImageFile(null)}
                    title="Remove screenshot"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
              {referenceDitaFile && (
                <div className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-slate-50 px-3 py-1.5 text-xs text-slate-800">
                  <FileCode2 className="h-3.5 w-3.5" />
                  <span className="max-w-[18rem] truncate">{referenceDitaFile.name}</span>
                  <button
                    type="button"
                    className="rounded-full p-0.5 text-slate-600 hover:bg-slate-200"
                    onClick={() => setReferenceDitaFile(null)}
                    title="Remove reference DITA"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}

            {showAuthoringOptions && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs text-slate-700 sm:col-span-2">
                <span className="font-medium">Screenshot deliverable</span>
                <select
                  value={generationOptions.screenshot_deliverable || 'single_topic'}
                  onChange={(e) =>
                    setGenerationOptions((prev) => ({
                      ...prev,
                      screenshot_deliverable: e.target.value as ChatDitaGenerationOptions['screenshot_deliverable'],
                    }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                >
                  <option value="single_topic">Single DITA topic (screenshot pipeline)</option>
                  <option value="map_hierarchy">DITA map + stub topics (from diagram)</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-700">
                <span className="font-medium">DITA type</span>
                <select
                  value={generationOptions.dita_type || 'task'}
                  onChange={(e) =>
                    setGenerationOptions((prev) => ({ ...prev, dita_type: e.target.value as ChatDitaGenerationOptions['dita_type'] }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                >
                  <option value="task">task</option>
                  <option value="concept">concept</option>
                  <option value="reference">reference</option>
                  <option value="topic">topic</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-700">
                <span className="font-medium">File name</span>
                <input
                  type="text"
                  value={generationOptions.file_name || ''}
                  onChange={(e) => setGenerationOptions((prev) => ({ ...prev, file_name: e.target.value }))}
                  placeholder="generated-topic.dita"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-700 sm:col-span-2">
                <span className="font-medium">AEM save path</span>
                <input
                  type="text"
                  value={generationOptions.save_path || ''}
                  onChange={(e) => setGenerationOptions((prev) => ({ ...prev, save_path: e.target.value }))}
                  placeholder="/content/dam/my-project/topics"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-700">
                <span className="font-medium">Style strictness</span>
                <select
                  value={generationOptions.style_strictness || 'medium'}
                  onChange={(e) =>
                    setGenerationOptions((prev) => ({
                      ...prev,
                      style_strictness: e.target.value as ChatDitaGenerationOptions['style_strictness'],
                    }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                >
                  <option value="high">high (programmatic XML)</option>
                  <option value="medium">medium (programmatic)</option>
                  <option value="low">low (LLM XML)</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-700">
                <span className="font-medium">Output mode</span>
                <select
                  value={generationOptions.output_mode || 'xml_validation'}
                  onChange={(e) =>
                    setGenerationOptions((prev) => ({
                      ...prev,
                      output_mode: e.target.value as ChatDitaGenerationOptions['output_mode'],
                    }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                >
                  <option value="xml_validation">XML + validation summary</option>
                  <option value="xml_explanation">XML + explanation</option>
                  <option value="xml_only">XML only (minimal chat text)</option>
                  <option value="xml_style_diff">XML + style vs reference</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-700 sm:col-span-2">
                <span className="font-medium">Authoring pattern (reference-guided)</span>
                <select
                  value={generationOptions.authoring_pattern || 'auto'}
                  onChange={(e) =>
                    setGenerationOptions((prev) => ({
                      ...prev,
                      authoring_pattern: e.target.value as ChatDitaGenerationOptions['authoring_pattern'],
                    }))
                  }
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                >
                  <option value="auto">Auto-detect (Cisco-style task or reference from attachment)</option>
                  <option value="cisco_task">Cisco-style enterprise task</option>
                  <option value="cisco_reference">Cisco-style enterprise reference</option>
                  <option value="default">Default layout</option>
                </select>
              </label>
              <label className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 sm:col-span-2">
                <input
                  type="checkbox"
                  checked={generationOptions.preserve_reference_doctype ?? false}
                  onChange={(e) =>
                    setGenerationOptions((prev) => ({ ...prev, preserve_reference_doctype: e.target.checked }))
                  }
                  className="h-4 w-4 rounded border-slate-300"
                />
                Preserve reference DOCTYPE line when the root matches (task/reference). Cisco modes also preserve when declared.
              </label>
              <label className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={generationOptions.preserve_prolog ?? false}
                  onChange={(e) => setGenerationOptions((prev) => ({ ...prev, preserve_prolog: e.target.checked }))}
                  className="h-4 w-4 rounded border-slate-300"
                />
                Preserve prolog shape (when reference uses prolog)
              </label>
              <label className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={generationOptions.xref_placeholders ?? false}
                  onChange={(e) => setGenerationOptions((prev) => ({ ...prev, xref_placeholders: e.target.checked }))}
                  className="h-4 w-4 rounded border-slate-300"
                />
                Allow xref href placeholders
              </label>
              <label className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={generationOptions.auto_ids ?? true}
                  onChange={(e) => setGenerationOptions((prev) => ({ ...prev, auto_ids: e.target.checked }))}
                  className="h-4 w-4 rounded border-slate-300"
                />
                Auto-generate topic/step IDs
              </label>
              <label className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 sm:col-span-2">
                <input
                  type="checkbox"
                  checked={generationOptions.strict_validation ?? true}
                  onChange={(e) => setGenerationOptions((prev) => ({ ...prev, strict_validation: e.target.checked }))}
                  className="h-4 w-4 rounded border-slate-300"
                />
                Strict validation and one repair pass if needed
              </label>
              </div>
            )}
          </div>
        )}

        {selectedTool && (
          <div className="rounded-xl border border-teal-200 bg-teal-50/70 p-3 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-teal-800">Slash tool</p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-teal-200 bg-white px-2.5 py-1 text-sm font-medium text-teal-950">
                  /{selectedTool.slash_alias}
                </span>
                <span className="text-xs text-slate-600">{selectedTool.title}</span>
                {primaryArgRequired && (
                  <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-red-700">
                    Required input
                  </span>
                )}
                {selectedTool.approval_required && (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-700">
                    Approval required
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={clearTool}
              className="rounded-lg border border-teal-200 bg-white p-2 text-teal-700 transition hover:bg-teal-100"
              title="Cancel slash tool"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
            {additionalFields.length > 0 && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {additionalFields.map(([key, spec]) => {
                const label = key.replace(/_/g, ' ');
                const rawValue = argValues[key] || '';
                if (spec?.enum?.length) {
                  return (
                    <label key={key} className="flex flex-col gap-1 text-xs text-slate-700">
                      <span className="font-medium capitalize">
                        {label}
                        {requiredFields.includes(key) && (
                          <span className="ml-1 rounded-full border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-red-700">
                            Required
                          </span>
                        )}
                      </span>
                      <select
                        value={rawValue}
                        onChange={(e) => setArgValues((prev) => ({ ...prev, [key]: e.target.value }))}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20"
                      >
                        <option value="">Select...</option>
                        {spec.enum.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                }
                const multiline = spec?.type === 'object';
                const inputClassName =
                  'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/20';
                return (
                  <label key={key} className={`flex flex-col gap-1 text-xs text-slate-700 ${multiline ? 'sm:col-span-2' : ''}`}>
                    <span className="font-medium capitalize">
                      {label}
                      {requiredFields.includes(key) && (
                        <span className="ml-1 rounded-full border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-red-700">
                          Required
                        </span>
                      )}
                    </span>
                    {multiline ? (
                      <textarea
                        rows={3}
                        value={rawValue}
                        onChange={(e) => setArgValues((prev) => ({ ...prev, [key]: e.target.value }))}
                        placeholder={spec?.description || ''}
                        className={`${inputClassName} resize-y`}
                      />
                    ) : (
                      <input
                        type={spec?.type === 'integer' || spec?.type === 'number' ? 'number' : 'text'}
                        value={rawValue}
                        onChange={(e) => setArgValues((prev) => ({ ...prev, [key]: e.target.value }))}
                        placeholder={
                          spec?.type === 'array'
                            ? 'Comma-separated values'
                            : spec?.description || ''
                        }
                        className={inputClassName}
                      />
                    )}
                  </label>
                );
              })}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="relative flex gap-3">
        <div className="flex-1">
          {selectedTool && (
            <div className="mb-2 flex flex-wrap items-center gap-2 px-1">
              <span className="text-xs font-medium text-slate-700">
                {primaryArg ? primaryArg.replace(/_/g, ' ') : 'Main input'}
              </span>
              {primaryArgRequired && (
                <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-red-700">
                  Required
                </span>
              )}
            </div>
          )}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setCaretPos(e.target.selectionStart);
            }}
            onSelect={(e) => setCaretPos(e.currentTarget.selectionStart)}
            onClick={(e) => setCaretPos(e.currentTarget.selectionStart)}
            onKeyUp={(e) => setCaretPos(e.currentTarget.selectionStart)}
            onFocus={() => {
              if (!selectedTool && value.startsWith('/')) {
                setPaletteOpen(true);
              }
            }}
            onKeyDown={(e) => {
              if (paletteOpen && filteredTools.length > 0 && e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                selectTool(filteredTools[0]!);
                return;
              }
              if (e.key === 'Escape' && paletteOpen) {
                e.preventDefault();
                setPaletteOpen(false);
                return;
              }
              if (!selectedTool && onSendAuthoring && activeAuthoringMention) {
                if (authoringMentionCandidates.length > 0) {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setAuthoringMentionHighlightIdx((i) =>
                      Math.min(i + 1, authoringMentionCandidates.length - 1)
                    );
                    return;
                  }
                  if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setAuthoringMentionHighlightIdx((i) => Math.max(i - 1, 0));
                    return;
                  }
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const c = authoringMentionCandidates[authoringMentionHighlightIdx];
                    if (c) selectAuthoringMentionCandidate(c);
                    return;
                  }
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  const active = getActiveAuthoringMention(value, caretPos);
                  if (active) {
                    const next = value.slice(0, active.start) + value.slice(caretPos);
                    pendingCaretAfterMentionRef.current = active.start;
                    onChange(next);
                  }
                  return;
                }
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!showStop && (selectedTool ? canSendTool : canSendText)) {
                  handleSendClick();
                }
              }
            }}
            placeholder={
              selectedTool && primaryArg
                ? selectedTool.args_schema?.properties?.[primaryArg]?.description || `Enter ${primaryArg}`
                : selectedTool
                  ? 'No main text argument is required for this tool.'
                  : mainPlaceholder
            }
            disabled={disabled}
            rows={1}
            style={{ minHeight: '56px', maxHeight: '220px' }}
            className="w-full resize-none overflow-y-auto rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm leading-relaxed text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-400/25 disabled:opacity-60"
          />
          {selectedTool && missingRequiredFields.length > 0 && (
            <p className="mt-2 px-1 text-xs text-amber-700">
              Add the required input to enable this tool:
              {' '}
              {missingRequiredFields.map((field) => field.replace(/_/g, ' ')).join(', ')}.
            </p>
          )}
        </div>

        {showAuthoringMentionMenu && !selectedTool && (
          <div
            className="absolute inset-x-0 bottom-[calc(100%+0.6rem)] z-40 max-h-[14rem] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
            onMouseDown={(e) => e.preventDefault()}
          >
            <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5 text-xs text-slate-500">
              <Search className="h-3.5 w-3.5 shrink-0" />
              <span>Attach or mention — filter with the text after @</span>
            </div>
            <div className="max-h-[11rem] overflow-y-auto p-2">
              {authoringMentionCandidates.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 px-3 py-4 text-center text-xs text-slate-500">
                  No matches. Try another name, or choose “Attach screenshot…” / “Attach reference DITA…”.
                </div>
              ) : (
                <ul className="space-y-1" role="listbox">
                  {authoringMentionCandidates.map((c, idx) => (
                    <li key={c.id} role="none">
                      <button
                        type="button"
                        role="option"
                        aria-selected={idx === authoringMentionHighlightIdx}
                        className={`flex w-full items-start gap-3 rounded-xl border px-3 py-2 text-left text-sm transition ${
                          idx === authoringMentionHighlightIdx
                            ? 'border-teal-300 bg-teal-50'
                            : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
                        }`}
                        onMouseEnter={() => setAuthoringMentionHighlightIdx(idx)}
                        onClick={() => selectAuthoringMentionCandidate(c)}
                      >
                        <div className="mt-0.5 rounded-lg border border-slate-200 bg-slate-50 p-2 text-slate-600">
                          {c.type === 'action' ? (
                            c.kind === 'pick-image' ? (
                              <ImageIcon className="h-4 w-4" />
                            ) : (
                              <FileCode2 className="h-4 w-4" />
                            )
                          ) : c.kind === 'image' ? (
                            <ImageIcon className="h-4 w-4" />
                          ) : (
                            <FileCode2 className="h-4 w-4" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-medium text-slate-900">{c.label}</div>
                          {c.type === 'action' && (
                            <p className="mt-0.5 text-xs text-slate-500">{c.description}</p>
                          )}
                          {c.type === 'attachment' && (
                            <p className="mt-0.5 text-xs text-slate-500">Insert @{c.fileName} into the prompt</p>
                          )}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {paletteOpen && !selectedTool && (
          <div className="absolute inset-x-0 bottom-[calc(100%+0.6rem)] z-30 max-h-[26rem] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5 text-xs text-slate-500">
              <Search className="h-3.5 w-3.5" />
              Search all chat tools
            </div>
            <div className="max-h-[22rem] overflow-y-auto p-2">
              {filteredTools.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 px-3 py-5 text-center text-sm text-slate-500">
                  {toolsUnavailable
                    ? 'Slash tools are unavailable right now. Restart the backend to load the tool catalog.'
                    : `No tools match "${slashQuery}".`}
                </div>
              ) : (
                Object.entries(groupedTools).map(([group, groupTools]) => (
                  <div key={group} className="mb-3 last:mb-0">
                    <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">{group}</p>
                    <div className="space-y-1">
                      {groupTools.map((tool) => (
                        <button
                          key={tool.name}
                          type="button"
                          onClick={() => selectTool(tool)}
                          className="flex w-full items-start gap-3 rounded-xl border border-transparent px-3 py-2 text-left transition hover:border-slate-200 hover:bg-slate-50"
                        >
                          <div className="mt-0.5 rounded-lg border border-slate-200 bg-slate-50 p-2 text-slate-600">
                            <Wand2 className="h-4 w-4" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-medium text-slate-900">{tool.title}</span>
                              <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                                /{tool.slash_alias}
                              </span>
                              {tool.approval_required && (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-700">
                                  Approval
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs leading-relaxed text-slate-500">{tool.description}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        <div className="flex shrink-0 flex-col gap-2 self-end">
          {sessionId && (
            <Button
              type="button"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || uploading}
              className="h-11 rounded-lg border-slate-300 text-slate-600 hover:bg-slate-50"
              title="Upload files (images, XML, DITA)"
            >
              <Upload className="h-4 w-4" />
            </Button>
          )}
          {showStop && (
            <Button
              type="button"
              variant="outline"
              onClick={onStop}
              className="h-11 rounded-lg border-amber-300 text-amber-900 hover:bg-amber-50"
            >
              <Square className="mr-2 h-3.5 w-3.5 fill-current" />
              Stop
            </Button>
          )}
          <Button
            onClick={handleSendClick}
            disabled={
              disabled ||
              loading ||
              showStop ||
              (!selectedTool && !imageFile && !value.trim()) ||
              (selectedTool && !canSendTool) ||
              (!selectedTool && imageFile !== null && !canSendAuthoring)
            }
            className="h-11 rounded-lg bg-teal-700 px-5 font-medium text-white shadow-sm transition hover:bg-teal-800"
            title={selectedTool && missingRequired ? `Add required input: ${missingRequiredFields.map((field) => field.replace(/_/g, ' ')).join(', ')}` : undefined}
          >
            {loading && !showStop ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            <span className="ml-2">
              {selectedTool
                ? missingRequired
                  ? 'Add required input'
                  : 'Run tool'
                : imageFile
                  ? 'Generate DITA'
                : 'Send'}
            </span>
          </Button>
        </div>
      </div>

      {(helperText || showShortcutHint) && (
        <p className="text-xs text-slate-400">
          {helperText}
          {showShortcutHint && !selectedTool && !activeGuide && (
            <>
              {' '}
              <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Enter</kbd> to send -{' '}
              <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Shift</kbd>+
              <kbd className="rounded border border-slate-200 bg-slate-50 px-1">Enter</kbd> for a new line
            </>
          )}
        </p>
      )}

      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0] ?? null;
          const pendingRange = pendingAuthoringMentionRangeRef.current;
          pendingAuthoringMentionRangeRef.current = null;
          if (!file) {
            e.currentTarget.value = '';
            return;
          }
          setImageFile(file);
          setShowAuthoringOptions(true);
          if (pendingRange) {
            const { nextValue, caretAfter } = replaceAuthoringMentionInValue(valueRef.current, pendingRange, file.name);
            pendingCaretAfterMentionRef.current = caretAfter;
            onChange(nextValue);
          }
          e.currentTarget.value = '';
        }}
      />
      <input
        ref={ditaInputRef}
        type="file"
        accept=".dita,.xml,text/xml,application/xml"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0] ?? null;
          const pendingRange = pendingAuthoringMentionRangeRef.current;
          pendingAuthoringMentionRangeRef.current = null;
          if (!file) {
            e.currentTarget.value = '';
            return;
          }
          setReferenceDitaFile(file);
          setShowAuthoringOptions(true);
          if (pendingRange) {
            const { nextValue, caretAfter } = replaceAuthoringMentionInValue(valueRef.current, pendingRange, file.name);
            pendingCaretAfterMentionRef.current = caretAfter;
            onChange(nextValue);
          }
          e.currentTarget.value = '';
        }}
      />
    </div>
  );
}
