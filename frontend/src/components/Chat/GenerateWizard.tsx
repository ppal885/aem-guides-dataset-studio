import { useState, useEffect, useRef } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Wand2, X, ChevronRight, ChevronLeft, Sparkles, Download, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { apiUrl, fetchJson } from '@/utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

interface WizardState {
  topicType: string;
  structure: string;
  domain: string;
  scale: string;
}

type GenStatus = 'idle' | 'generating' | 'done' | 'error';

interface GenResult {
  download_url?: string;
  jira_id?: string;
  run_id?: string;
  artifact_counts?: { topic_files?: number; map_files?: number; total_files?: number };
}

// ── Config ─────────────────────────────────────────────────────────────────

const TOPIC_TYPES = [
  { id: 'reference', label: 'Reference', icon: '📋', desc: 'API fields, config params, resource specs', example: 'aws_s3_bucket fields, kubectl flags' },
  { id: 'task',      label: 'Task',      icon: '✅', desc: 'Step-by-step procedures and workflows',   example: 'Install kubectl, Create S3 bucket' },
  { id: 'concept',   label: 'Concept',   icon: '💡', desc: 'Architecture, principles, overviews',     example: 'IAM model, Kafka consumer groups' },
  { id: 'mixed',     label: 'Mixed',     icon: '🗂️', desc: 'Reference + Task + Concept combined',    example: 'Full docs set for a technology' },
];

const STRUCTURES = [
  { id: 'freeform',        label: 'Freeform (LLM)',   icon: '🤖', desc: 'Best quality — real content, no placeholders', badge: 'Recommended', recipe: 'freeform' },
  { id: 'deep_hierarchy',  label: 'Deep Hierarchy',   icon: '🌳', desc: 'Nested tree — categories & subcategories',     badge: null, recipe: 'deep_hierarchy' },
  { id: 'flat',            label: 'Flat / Large Scale',icon: '📄', desc: 'Many topics at same level, great for APIs',   badge: null, recipe: null },
  { id: 'wide',            label: 'Wide Branching',   icon: '🌿', desc: 'Multiple root topics each with children',      badge: null, recipe: 'wide_branching' },
];

const DOMAIN_SUGGESTIONS = [
  'Kubernetes', 'Terraform AWS', 'Adobe Experience Manager',
  'GitHub Actions', 'Docker', 'PostgreSQL', 'React 18',
  'Ansible', 'Apache Kafka', 'Azure DevOps',
];

const SCALES = [
  { id: 'small',  label: 'Small',       range: '~20 topics',      hint: 'Quick, focused',            topicCount: 20  },
  { id: 'medium', label: 'Medium',      range: '50–100 topics',   hint: 'Full module',               topicCount: 75  },
  { id: 'large',  label: 'Large',       range: '200–300 topics',  hint: 'Complete docs set',         topicCount: 250 },
  { id: 'xlarge', label: 'Extra Large', range: '400–500 topics',  hint: 'Enterprise / training data',topicCount: 450 },
];

// ── Prompt & Recipe builder ────────────────────────────────────────────────

function getRecipeType(topicType: string, structure: string): string {
  if (structure === 'freeform') return 'freeform';
  if (structure === 'deep_hierarchy') return 'deep_hierarchy';
  if (structure === 'wide') return 'wide_branching';
  // flat
  const flatMap: Record<string, string> = {
    reference: 'reference_topics',
    task:      'task_topics',
    concept:   'concept_topics',
    mixed:     'flat_hierarchical_dita',
  };
  return flatMap[topicType] ?? 'flat_hierarchical_dita';
}

function buildPromptText(state: WizardState): string {
  const { topicType, structure, domain, scale } = state;
  const count = SCALES.find(s => s.id === scale)?.topicCount ?? 20;
  const recipe = getRecipeType(topicType, structure);

  if (recipe === 'freeform') {
    return `Generate a freeform ${topicType} DITA dataset about ${domain}. Produce approximately ${count} topics with real domain content.`;
  }
  if (structure === 'deep_hierarchy') {
    return `${domain} — deep hierarchy DITA dataset, topic_count ${count}, type emphasis: ${topicType}`;
  }
  if (structure === 'wide') {
    return `${domain} — wide branching DITA dataset, topic_count ${count}, type emphasis: ${topicType}`;
  }
  return `${domain} — ${recipe} DITA dataset, topic_count ${count}`;
}

// ── API calls ──────────────────────────────────────────────────────────────

async function startGeneration(state: WizardState): Promise<{ run_id: string; status: string }> {
  const recipe = getRecipeType(state.topicType, state.structure);
  const count = SCALES.find(s => s.id === state.scale)?.topicCount ?? 20;

  if (recipe === 'freeform') {
    // Freeform: call generate-from-text async
    const body = {
      text: buildPromptText(state),
      generate_mode: 'freeform',
    };
    const res = await fetchJson<{ run_id: string; status: string }>(
      apiUrl('/api/v1/ai/generate-from-text?async=true'),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    );
    return res;
  } else {
    // Recipe: call generate-from-text with intent pipeline to pick recipe
    const instruction = `Use recipe_type=${recipe}, topic_count=${count}, subject="${state.domain}"`;
    const body = {
      text: buildPromptText(state),
      instructions: instruction,
      generate_mode: 'recipe',
    };
    const res = await fetchJson<{ run_id: string; status: string }>(
      apiUrl('/api/v1/ai/generate-from-text?async=true'),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    );
    return res;
  }
}

async function pollStatus(runId: string): Promise<{ status: string; result?: GenResult; stage?: string; message?: string }> {
  return fetchJson(apiUrl(`/api/v1/ai/generate-status/${runId}`));
}

// ── Component ──────────────────────────────────────────────────────────────

interface Props {
  onInsert?: (prompt: string) => void; // kept for fallback
}

export function GenerateWizard({ onInsert }: Props) {
  const [open, setOpen]     = useState(false);
  const [step, setStep]     = useState(0);
  const [state, setState]   = useState<WizardState>({ topicType: '', structure: '', domain: '', scale: 'small' });
  const [genStatus, setGenStatus] = useState<GenStatus>('idle');
  const [runId, setRunId]         = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState('');
  const [result, setResult]       = useState<GenResult | null>(null);
  const [error, setError]         = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const STEPS = ['Topic Type', 'Structure', 'Domain', 'Scale'];

  function reset() {
    setStep(0);
    setState({ topicType: '', structure: '', domain: '', scale: 'small' });
    setGenStatus('idle');
    setRunId(null);
    setStatusMsg('');
    setResult(null);
    setError('');
    if (pollRef.current) clearInterval(pollRef.current);
  }

  // Poll for completion
  useEffect(() => {
    if (!runId || genStatus !== 'generating') return;

    pollRef.current = setInterval(async () => {
      try {
        const data = await pollStatus(runId);
        if (data.message) setStatusMsg(data.message);
        if (data.stage)   setStatusMsg(`${data.stage}…`);

        if (data.status === 'completed' && data.result) {
          clearInterval(pollRef.current!);
          setResult(data.result);
          setGenStatus('done');
        } else if (data.status === 'failed' || data.status === 'error') {
          clearInterval(pollRef.current!);
          setError(data.message ?? 'Generation failed');
          setGenStatus('error');
        }
      } catch {
        // ignore transient poll errors
      }
    }, 2500);

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [runId, genStatus]);

  async function handleGenerate() {
    setGenStatus('generating');
    setStatusMsg('Starting generation…');
    try {
      const res = await startGeneration(state);
      setRunId(res.run_id);
      setStatusMsg('LLM is reasoning and generating DITA…');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start generation');
      setGenStatus('error');
    }
  }

  function canNext() {
    if (step === 0) return !!state.topicType;
    if (step === 1) return !!state.structure;
    if (step === 2) return !!state.domain.trim();
    return true;
  }

  const isGenerating = genStatus === 'generating';
  const isDone       = genStatus === 'done';
  const isError      = genStatus === 'error';
  const selectedScale = SCALES.find(s => s.id === state.scale);
  const recipe = state.topicType && state.structure ? getRecipeType(state.topicType, state.structure) : '';

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          title="Generate DITA wizard"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-teal-200 bg-teal-50 text-teal-700 transition hover:bg-teal-100"
        >
          <Wand2 className="h-4 w-4" />
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white shadow-2xl focus:outline-none">

          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-teal-600" />
              <span className="font-semibold text-slate-800">Generate DITA</span>
            </div>
            <Dialog.Close className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* ── Generating / Done / Error states ── */}
          {genStatus !== 'idle' && (
            <div className="px-6 py-8">
              {isGenerating && (
                <div className="flex flex-col items-center gap-4 text-center">
                  <Loader2 className="h-10 w-10 animate-spin text-teal-500" />
                  <p className="font-medium text-slate-700">Generating DITA for <span className="text-teal-700">{state.domain}</span></p>
                  <p className="text-sm text-slate-400">{statusMsg}</p>
                  <p className="text-xs text-slate-300">~1–2 min for small datasets</p>
                </div>
              )}
              {isDone && result && (
                <div className="flex flex-col items-center gap-4 text-center">
                  <CheckCircle2 className="h-10 w-10 text-teal-500" />
                  <p className="font-medium text-slate-700">DITA generated successfully!</p>
                  {result.artifact_counts && (
                    <p className="text-sm text-slate-500">
                      {result.artifact_counts.topic_files ?? 0} topics · {result.artifact_counts.map_files ?? 0} maps
                    </p>
                  )}
                  {result.download_url && (
                    <a
                      href={apiUrl(result.download_url)}
                      download
                      className="flex items-center gap-2 rounded-xl bg-teal-600 px-6 py-3 text-sm font-medium text-white transition hover:bg-teal-700"
                    >
                      <Download className="h-4 w-4" />
                      Download ZIP
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={reset}
                    className="text-sm text-slate-400 hover:text-slate-600"
                  >
                    Generate another
                  </button>
                </div>
              )}
              {isError && (
                <div className="flex flex-col items-center gap-4 text-center">
                  <AlertCircle className="h-10 w-10 text-red-400" />
                  <p className="font-medium text-slate-700">Generation failed</p>
                  <p className="text-sm text-red-500">{error}</p>
                  <button
                    type="button"
                    onClick={reset}
                    className="rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-600 hover:bg-slate-200"
                  >
                    Try again
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── Wizard steps ── */}
          {genStatus === 'idle' && (
            <>
              {/* Step indicator */}
              <div className="flex gap-1 px-6 pt-4">
                {STEPS.map((s, i) => (
                  <div key={s} className="flex flex-1 flex-col items-center gap-1">
                    <div className={`h-1.5 w-full rounded-full transition-colors ${i <= step ? 'bg-teal-500' : 'bg-slate-100'}`} />
                    <span className={`text-xs ${i === step ? 'font-medium text-teal-600' : 'text-slate-400'}`}>{s}</span>
                  </div>
                ))}
              </div>

              <div className="px-6 py-5">
                {/* Step 0: Topic Type */}
                {step === 0 && (
                  <div className="grid grid-cols-2 gap-3">
                    {TOPIC_TYPES.map((t) => (
                      <button key={t.id} type="button"
                        onClick={() => setState(s => ({ ...s, topicType: t.id }))}
                        className={`rounded-xl border-2 p-4 text-left transition ${state.topicType === t.id ? 'border-teal-500 bg-teal-50' : 'border-slate-100 hover:border-slate-200 hover:bg-slate-50'}`}
                      >
                        <div className="mb-1 text-2xl">{t.icon}</div>
                        <div className="font-semibold text-slate-800">{t.label}</div>
                        <div className="mt-0.5 text-xs text-slate-500">{t.desc}</div>
                        <div className="mt-1 text-xs text-slate-400 italic">{t.example}</div>
                      </button>
                    ))}
                  </div>
                )}

                {/* Step 1: Structure */}
                {step === 1 && (
                  <div className="grid grid-cols-2 gap-3">
                    {STRUCTURES.map((s) => (
                      <button key={s.id} type="button"
                        onClick={() => setState(st => ({ ...st, structure: s.id }))}
                        className={`relative rounded-xl border-2 p-4 text-left transition ${state.structure === s.id ? 'border-teal-500 bg-teal-50' : 'border-slate-100 hover:border-slate-200 hover:bg-slate-50'}`}
                      >
                        {s.badge && (
                          <span className="absolute right-3 top-3 rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-teal-700">{s.badge}</span>
                        )}
                        <div className="mb-1 text-2xl">{s.icon}</div>
                        <div className="font-semibold text-slate-800">{s.label}</div>
                        <div className="mt-0.5 text-xs text-slate-500">{s.desc}</div>
                      </button>
                    ))}
                  </div>
                )}

                {/* Step 2: Domain */}
                {step === 2 && (
                  <div className="space-y-4">
                    <input autoFocus type="text"
                      placeholder="e.g. Terraform AWS, Kubernetes, AEM Guides…"
                      value={state.domain}
                      onChange={(e) => setState(s => ({ ...s, domain: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                    />
                    <div>
                      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Quick select</p>
                      <div className="flex flex-wrap gap-2">
                        {DOMAIN_SUGGESTIONS.map((d) => (
                          <button key={d} type="button"
                            onClick={() => setState(s => ({ ...s, domain: d }))}
                            className={`rounded-full border px-3 py-1 text-xs transition ${state.domain === d ? 'border-teal-400 bg-teal-50 font-medium text-teal-700' : 'border-slate-200 text-slate-600 hover:border-teal-200 hover:bg-teal-50'}`}
                          >
                            {d}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Step 3: Scale */}
                {step === 3 && (
                  <div className="space-y-3">
                    {SCALES.map((s) => (
                      <button key={s.id} type="button"
                        onClick={() => setState(st => ({ ...st, scale: s.id }))}
                        className={`flex w-full items-center justify-between rounded-xl border-2 px-4 py-3 text-left transition ${state.scale === s.id ? 'border-teal-500 bg-teal-50' : 'border-slate-100 hover:border-slate-200 hover:bg-slate-50'}`}
                      >
                        <div>
                          <span className="font-semibold text-slate-800">{s.label}</span>
                          <span className="ml-2 text-sm text-slate-500">{s.range}</span>
                        </div>
                        <span className="text-xs text-slate-400">{s.hint}</span>
                      </button>
                    ))}

                    {/* Summary card */}
                    {state.domain && (
                      <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Summary</p>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
                          <span className="text-slate-400">Type</span><span className="font-medium capitalize">{state.topicType}</span>
                          <span className="text-slate-400">Structure</span><span className="font-medium">{STRUCTURES.find(s => s.id === state.structure)?.label}</span>
                          <span className="text-slate-400">Domain</span><span className="font-medium">{state.domain}</span>
                          <span className="text-slate-400">Topics</span><span className="font-medium">{selectedScale?.topicCount} (~{selectedScale?.range})</span>
                          <span className="text-slate-400">Recipe</span><span className="font-mono text-teal-700">{recipe}</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between border-t border-slate-100 px-6 py-4">
                <button type="button"
                  onClick={() => setStep(s => s - 1)}
                  disabled={step === 0}
                  className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 disabled:opacity-0"
                >
                  <ChevronLeft className="h-4 w-4" />
                  Back
                </button>

                {step < STEPS.length - 1 ? (
                  <button type="button"
                    onClick={() => setStep(s => s + 1)}
                    disabled={!canNext()}
                    className="flex items-center gap-1 rounded-lg bg-teal-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-40"
                  >
                    Next <ChevronRight className="h-4 w-4" />
                  </button>
                ) : (
                  <button type="button"
                    onClick={handleGenerate}
                    disabled={!canNext()}
                    className="flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-40"
                  >
                    <Wand2 className="h-4 w-4" />
                    Generate Now
                  </button>
                )}
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
