import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  Bot,
  CheckCircle2,
  ChevronRight,
  Code2,
  Database,
  FileText,
  GitBranch,
  LifeBuoy,
  Maximize2,
  MessageSquare,
  ShieldCheck,
  Slack,
  Sparkles,
  X,
} from 'lucide-react'

const sidebarSections = [
  { title: 'Get Started', items: ['Welcome', 'Ask AI Chat', 'Knowledge Sources', 'Slack Setup'] },
  { title: 'DITA Expert', items: ['Key references', 'Content reuse', 'Maps and scopes', 'Tables and attributes', 'Troubleshooting'] },
  { title: 'DITA-OT', items: ['Preprocessing', 'PDF publishing', 'Markdown input', 'Parameters', 'Plug-ins'] },
  { title: 'Governance', items: ['Learned Q&A', 'Review Center', 'Jira issue analysis', 'Source health'] },
]

const quickLinks = [
  { label: 'Open AI Chat', to: '/chat', icon: Bot },
  { label: 'Review Sources', to: '/settings', icon: Database },
  { label: 'Builder', to: '/builder', icon: Code2 },
]

const featureCards = [
  {
    icon: MessageSquare,
    title: 'Senior-quality answers',
    text: 'Direct explanation first, then scope, XML examples, expected results, and common mistakes.',
  },
  {
    icon: ShieldCheck,
    title: 'Trusted retrieval',
    text: 'Uses approved learned Q&A and indexed DITA, DITA-OT, AEM Guides, and Jira sources.',
  },
  {
    icon: GitBranch,
    title: 'Troubleshooting depth',
    text: 'Handles keyref, conref, branch filtering, processing-role, copy-to, PDF, and publishing issues.',
  },
]

const prompts = [
  'What is keyscope in DITA? Show a map example.',
  'Why does a keyref work in one map but not another?',
  'How do I debug HTML output working but PDF failing?',
  'Compare toc="no" and processing-role="resource-only".',
]

export function LandingDocsPage() {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)

  return (
    <div className="min-h-[calc(100vh-68px)] bg-[#fbfaf7] text-[#1f1f1d]">
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_280px]">
        <aside className="hidden border-r border-stone-200 bg-[#f5f3ef] px-6 py-8 lg:block">
          <div className="sticky top-24 space-y-8">
            {sidebarSections.map((section) => (
              <div key={section.title}>
                <p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-stone-400">{section.title}</p>
                <nav className="space-y-1">
                  {section.items.map((item, index) => (
                    <a
                      key={item}
                      href={index === 0 && section.title === 'Get Started' ? '#welcome' : '#features'}
                      className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium transition ${
                        item === 'Welcome'
                          ? 'bg-white text-teal-700 shadow-sm'
                          : 'text-stone-700 hover:bg-white hover:text-stone-950'
                      }`}
                    >
                      {item}
                      {(item === 'Knowledge Sources' || item === 'Preprocessing') && <ChevronRight className="h-4 w-4 text-stone-400" />}
                    </a>
                  ))}
                </nav>
              </div>
            ))}
          </div>
        </aside>

        <main className="min-w-0 px-6 py-10 sm:px-10 lg:px-16">
          <section id="welcome" className="mx-auto max-w-5xl">
            <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-stone-500">
              <BookOpen className="h-4 w-4" />
              Get Started
            </div>
            <h1 className="max-w-4xl text-5xl font-semibold tracking-[-0.05em] text-stone-950 sm:text-6xl">
              DITA Expert Bot documentation
            </h1>
            <p className="mt-6 max-w-3xl text-xl leading-9 text-stone-700">
              A senior DITA, AEM Guides, DITA-OT, XML reuse, publishing, and Jira troubleshooting assistant for
              documentation teams. Use it to get source-grounded explanations, full XML examples, expected results,
              and deterministic debugging checks.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              {quickLinks.map((item) => {
                const Icon = item.icon
                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    className="inline-flex items-center gap-2 rounded-2xl border border-stone-200 bg-white px-5 py-3 text-sm font-bold text-stone-800 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:text-teal-700 hover:shadow-md"
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                )
              })}
            </div>

            <div
              role="button"
              tabIndex={0}
              aria-label="Open senior answer preview"
              onClick={() => setIsPreviewOpen(true)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setIsPreviewOpen(true)
                }
              }}
              className="group relative mt-10 cursor-zoom-in overflow-hidden rounded-[1.75rem] border border-stone-200 bg-stone-950 shadow-2xl shadow-stone-900/10 outline-none transition hover:-translate-y-0.5 hover:shadow-2xl hover:shadow-stone-900/20 focus-visible:ring-4 focus-visible:ring-teal-500/20"
            >
              <div className="pointer-events-none absolute right-4 top-4 z-10 flex items-center gap-2 rounded-full bg-black/45 px-3 py-1.5 text-xs font-semibold text-white opacity-0 backdrop-blur transition group-hover:opacity-100">
                <Maximize2 className="h-3.5 w-3.5" />
                Click to expand
              </div>
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-red-400" />
                  <span className="h-3 w-3 rounded-full bg-amber-300" />
                  <span className="h-3 w-3 rounded-full bg-emerald-400" />
                </div>
                <span className="rounded-full bg-teal-400/10 px-3 py-1 text-xs font-semibold text-teal-200">
                  Senior answer preview
                </span>
              </div>
              <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
                <div className="border-b border-white/10 p-6 lg:border-b-0 lg:border-r">
                  <p className="mb-4 text-sm font-semibold text-stone-400">Prompt</p>
                  <div className="rounded-2xl bg-white/5 p-5 text-lg font-semibold leading-8 text-white">
                    What is <code className="text-teal-200">@keyscope</code> in DITA? Show an example.
                  </div>
                  <div className="mt-5 space-y-3 text-sm text-stone-300">
                    {['Uses learned Q&A first', 'Verifies against indexed DITA sources', 'Includes XML and expected result'].map((item) => (
                      <div key={item} className="flex gap-2">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 text-teal-300" />
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="p-6">
                  <p className="mb-4 text-sm font-semibold text-stone-400">Answer shape</p>
                  <div className="space-y-4 text-sm leading-7 text-stone-200">
                    <p>
                      <span className="font-bold text-white">Short answer:</span> <code>@keyscope</code> creates a named
                      key-resolution boundary in a DITA map branch.
                    </p>
                    <pre className="overflow-x-auto rounded-2xl bg-black/35 p-4 text-xs text-teal-100">
{`<map>
  <topicref keyscope="productA">
    <keydef keys="install" href="install-a.dita"/>
    <topicref href="guide.dita"/>
  </topicref>
</map>`}
                    </pre>
                    <p>
                      <span className="font-bold text-white">Expected result:</span> key references inside the branch
                      resolve in <code>productA</code> before falling back to broader map context.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section id="features" className="mx-auto mt-16 max-w-5xl">
            <h2 className="text-3xl font-semibold tracking-[-0.035em] text-stone-950">What you can do with it</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {featureCards.map((card) => {
                const Icon = card.icon
                return (
                  <div key={card.title} className="rounded-3xl border border-stone-200 bg-white p-6 shadow-sm">
                    <div className="mb-5 inline-flex rounded-2xl bg-teal-50 p-3 text-teal-700">
                      <Icon className="h-6 w-6" />
                    </div>
                    <h3 className="text-lg font-bold text-stone-950">{card.title}</h3>
                    <p className="mt-3 text-sm leading-6 text-stone-600">{card.text}</p>
                  </div>
                )
              })}
            </div>
          </section>

          <section className="mx-auto mt-16 grid max-w-5xl gap-6 lg:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-3xl border border-stone-200 bg-white p-7 shadow-sm">
              <div className="mb-4 flex items-center gap-3">
                <Database className="h-6 w-6 text-teal-700" />
                <h2 className="text-2xl font-semibold tracking-[-0.03em] text-stone-950">Trusted sources</h2>
              </div>
              <div className="space-y-3">
                {['DITA 1.2 / 1.3 spec', 'DITA-OT docs and release notes', 'AEM Guides docs', 'Jira QA knowledge', 'Approved learned prompts'].map((source) => (
                  <div key={source} className="flex items-center gap-3 rounded-2xl bg-stone-50 px-4 py-3 text-sm font-semibold text-stone-700">
                    <CheckCircle2 className="h-4 w-4 text-teal-600" />
                    {source}
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-3xl border border-stone-200 bg-white p-7 shadow-sm">
              <div className="mb-4 flex items-center gap-3">
                <FileText className="h-6 w-6 text-teal-700" />
                <h2 className="text-2xl font-semibold tracking-[-0.03em] text-stone-950">Try prompts</h2>
              </div>
              <div className="space-y-3">
                {prompts.map((prompt) => (
                  <Link
                    key={prompt}
                    to="/chat"
                    className="group flex items-center justify-between rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm font-semibold text-stone-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-800"
                  >
                    {prompt}
                    <ArrowRight className="h-4 w-4 opacity-0 transition group-hover:opacity-100" />
                  </Link>
                ))}
              </div>
            </div>
          </section>
        </main>

        <aside className="hidden border-l border-stone-200 px-8 py-10 xl:block">
          <div className="sticky top-24">
            <p className="mb-4 text-sm font-semibold text-stone-500">Start here</p>
            <nav className="space-y-3 border-b border-stone-200 pb-6">
              {['Start here', 'What this bot does', 'Trusted sources', 'Try example prompts', 'Team workflow'].map((item) => (
                <a key={item} href="#welcome" className="block text-sm font-medium text-stone-500 transition hover:text-stone-950">
                  {item}
                </a>
              ))}
            </nav>
            <div className="mt-6 space-y-4 text-sm text-stone-500">
              <Link to="/chat" className="flex items-center gap-2 transition hover:text-teal-700">
                <Sparkles className="h-4 w-4" />
                Ask AI Chat
              </Link>
              <Link to="/settings" className="flex items-center gap-2 transition hover:text-teal-700">
                <LifeBuoy className="h-4 w-4" />
                Check RAG status
              </Link>
              <div className="flex items-center gap-2">
                <Slack className="h-4 w-4" />
                Slack-ready
              </div>
            </div>
          </div>
        </aside>
      </div>

      {isPreviewOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Expanded senior answer preview"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-6 backdrop-blur-sm"
          onClick={() => setIsPreviewOpen(false)}
        >
          <div
            className="max-h-[88vh] w-full max-w-6xl overflow-hidden rounded-[1.75rem] border border-white/15 bg-stone-950 text-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-red-400" />
                <span className="h-3 w-3 rounded-full bg-amber-300" />
                <span className="h-3 w-3 rounded-full bg-emerald-400" />
                <span className="ml-3 text-sm font-semibold text-stone-300">Senior answer preview</span>
              </div>
              <button
                type="button"
                aria-label="Close preview"
                onClick={() => setIsPreviewOpen(false)}
                className="rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="grid max-h-[calc(88vh-57px)] overflow-auto lg:grid-cols-[0.9fr_1.1fr]">
              <div className="border-b border-white/10 p-8 lg:border-b-0 lg:border-r">
                <p className="mb-4 text-sm font-semibold text-stone-400">Prompt</p>
                <div className="rounded-2xl bg-white/5 p-6 text-2xl font-semibold leading-10 text-white">
                  What is <code className="text-teal-200">@keyscope</code> in DITA? Show an example.
                </div>
                <div className="mt-6 space-y-4 text-base text-stone-300">
                  {['Uses learned Q&A first', 'Verifies against indexed DITA sources', 'Includes XML and expected result'].map((item) => (
                    <div key={item} className="flex gap-3">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 text-teal-300" />
                      {item}
                    </div>
                  ))}
                </div>
              </div>
              <div className="p-8">
                <p className="mb-4 text-sm font-semibold text-stone-400">Answer shape</p>
                <div className="space-y-5 text-base leading-8 text-stone-200">
                  <p>
                    <span className="font-bold text-white">Short answer:</span> <code>@keyscope</code> creates a named
                    key-resolution boundary in a DITA map branch.
                  </p>
                  <pre className="overflow-x-auto rounded-2xl bg-black/35 p-5 text-sm text-teal-100">
{`<map>
  <topicref keyscope="productA">
    <keydef keys="install" href="install-a.dita"/>
    <topicref href="guide.dita"/>
  </topicref>
</map>`}
                  </pre>
                  <p>
                    <span className="font-bold text-white">Expected result:</span> key references inside the branch
                    resolve in <code>productA</code> before falling back to broader map context.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
