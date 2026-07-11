import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Database,
  FileCode2,
  GitBranch,
  MessageSquare,
  SearchCheck,
  Settings,
  ShieldCheck,
  Slack,
  Sparkles,
} from 'lucide-react'

const knowledgeSources = [
  'DITA 1.2 / 1.3 specification',
  'DITA-OT processing and parameters',
  'AEM Guides documentation',
  'Jira issue understanding',
  'Approved learned Q&A corpus',
]

const capabilities = [
  {
    icon: MessageSquare,
    title: 'Senior DITA answers',
    description:
      'Explains DITA concepts with direct answers, scope notes, XML examples, expected results, and common mistakes.',
  },
  {
    icon: SearchCheck,
    title: 'Trusted RAG retrieval',
    description:
      'Prioritizes approved learned examples and indexed product sources before falling back to broader LLM reasoning.',
  },
  {
    icon: GitBranch,
    title: 'DITA-OT troubleshooting',
    description:
      'Helps debug preprocessing, keyref, conref, branch filtering, copy-to, markdown input, and PDF publishing issues.',
  },
  {
    icon: Slack,
    title: 'Team-ready workflow',
    description:
      'Designed for direct use by documentation teams in the web app or through Slack integration.',
  },
]

const examplePrompts = [
  'What is keyscope in DITA? Show a map example.',
  'How do I debug a topic that works in HTML but fails in PDF?',
  'Compare conref, conkeyref, keyref, and href.',
  'When should processing-role="resource-only" be used?',
]

export function LandingPage() {
  return (
    <div className="space-y-16 pb-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-teal-100 bg-white/85 shadow-2xl shadow-teal-950/10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(20,184,166,0.2),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(15,23,42,0.12),transparent_35%)]" />
        <div className="relative grid gap-10 px-8 py-12 lg:grid-cols-[1.08fr_0.92fr] lg:px-12 lg:py-16">
          <div className="flex flex-col justify-center">
            <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-4 py-2 text-sm font-semibold text-teal-800">
              <Sparkles className="h-4 w-4" />
              Senior DITA, AEM Guides, and DITA-OT expert assistant
            </div>
            <h1 className="max-w-4xl text-4xl font-black tracking-tight text-slate-950 sm:text-5xl lg:text-6xl">
              Source-grounded answers for documentation teams.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-600">
              Ask practical DITA, AEM Guides, DITA-OT, publishing, XML reuse, and Jira troubleshooting
              questions. The assistant responds like a senior technical documentation expert with examples,
              expected behavior, and deterministic debugging checks.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/chat"
                className="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-teal-900/20 transition hover:bg-teal-700"
              >
                Ask the expert
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                to="/settings"
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-bold text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-800"
              >
                Review knowledge sources
                <Settings className="h-4 w-4" />
              </Link>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-slate-950 p-5 text-white shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="rounded-xl bg-teal-500/20 p-2 text-teal-200">
                  <Bot className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-bold">DITA Expert Bot</p>
                  <p className="text-xs text-slate-400">Example answer shape</p>
                </div>
              </div>
              <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-200">
                RAG + Expert reasoning
              </span>
            </div>
            <div className="space-y-3 rounded-2xl bg-white/5 p-4 text-sm leading-6 text-slate-200">
              <p className="font-semibold text-white">What is keyscope in DITA? Show an example.</p>
              <p>
                <span className="font-semibold text-teal-200">Short answer:</span> <code>@keyscope</code>{' '}
                creates a named key-resolution scope in a map branch.
              </p>
              <pre className="overflow-x-auto rounded-xl bg-slate-900 p-3 text-xs text-teal-100">
{`<map>
  <topicref keyscope="productA">
    <keydef keys="install" href="install-a.dita"/>
    <topicref href="guide.dita"/>
  </topicref>
</map>`}
              </pre>
              <p>
                <span className="font-semibold text-teal-200">Expected result:</span> key references inside
                the <code>productA</code> branch resolve against that branch before broader map scope.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        {capabilities.map((item) => {
          const Icon = item.icon
          return (
            <div key={item.title} className="rounded-2xl border border-slate-200 bg-white/85 p-6 shadow-sm">
              <div className="mb-4 inline-flex rounded-xl bg-teal-50 p-3 text-teal-700">
                <Icon className="h-6 w-6" />
              </div>
              <h2 className="text-lg font-bold text-slate-950">{item.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
            </div>
          )
        })}
      </section>

      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-3xl border border-slate-200 bg-white/85 p-7 shadow-sm">
          <div className="mb-4 flex items-center gap-3">
            <Database className="h-6 w-6 text-teal-700" />
            <h2 className="text-2xl font-black text-slate-950">Trusted knowledge stack</h2>
          </div>
          <p className="text-sm leading-6 text-slate-600">
            The system is built to answer from reviewed sources first, then synthesize with LLM reasoning
            only when the evidence supports the answer.
          </p>
          <div className="mt-5 space-y-3">
            {knowledgeSources.map((source) => (
              <div key={source} className="flex items-center gap-3 rounded-xl bg-slate-50 px-4 py-3">
                <CheckCircle2 className="h-5 w-5 text-teal-600" />
                <span className="text-sm font-semibold text-slate-700">{source}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white/85 p-7 shadow-sm">
          <div className="mb-4 flex items-center gap-3">
            <FileCode2 className="h-6 w-6 text-teal-700" />
            <h2 className="text-2xl font-black text-slate-950">Try senior-level prompts</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {examplePrompts.map((prompt) => (
              <Link
                key={prompt}
                to="/chat"
                className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm font-semibold leading-6 text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-800"
              >
                {prompt}
              </Link>
            ))}
          </div>
          <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <ShieldCheck className="mb-2 h-5 w-5" />
            Strong answers should include direct explanation, XML when relevant, expected result, scope note,
            and common mistakes—not shallow definitions.
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-teal-100 bg-gradient-to-r from-teal-700 to-slate-900 p-8 text-white shadow-xl">
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-3xl font-black">Ready to use it like a team expert?</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-teal-50">
              Start with chat for expert answers, then use Settings to review indexes, learned Q&A,
              failed items, and source health.
            </p>
          </div>
          <Link
            to="/chat"
            className="inline-flex w-fit items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-bold text-teal-800 shadow-lg transition hover:bg-teal-50"
          >
            Open AI Chat
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  )
}
