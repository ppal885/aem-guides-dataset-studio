import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Code2,
  Database,
  FileText,
  GitBranch,
  LifeBuoy,
  Maximize2,
  MessageSquare,
  PlayCircle,
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

const previewSlides = [
  {
    badge: 'Key scopes',
    prompt: 'What is @keyscope in DITA? Show an example.',
    checks: ['Uses learned Q&A first', 'Verifies against indexed DITA sources', 'Includes XML and expected result'],
    answer: '@keyscope creates a named key-resolution boundary in a DITA map branch.',
    xml: `<map>
  <topicref keyscope="productA">
    <keydef keys="install" href="install-a.dita"/>
    <topicref href="guide.dita"/>
  </topicref>
</map>`,
    expected: 'Key references inside the branch resolve in productA before falling back to broader map context.',
  },
  {
    badge: 'PDF troubleshooting',
    prompt: 'How do I debug a topic that publishes in HTML but fails in PDF?',
    checks: ['Separates DITA-OT from AEM behavior', 'Lists deterministic checks', 'Points to logs and temp files'],
    answer: 'Start by comparing the HTML and PDF preprocessing paths, then inspect PDF-specific plug-ins, filters, and generated intermediate files.',
    xml: `<topic id="pdf-debug">
  <title>PDF debug topic</title>
  <body>
    <p outputclass="pdf-only">Check formatter support.</p>
  </body>
</topic>`,
    expected: 'The answer should guide the user through logs, DITAVAL differences, image/table constraints, and PDF transform configuration.',
  },
  {
    badge: 'Resource-only',
    prompt: 'Compare toc="no" and processing-role="resource-only".',
    checks: ['Explains navigation vs generation', 'Avoids false equivalence', 'Includes map example'],
    answer: 'toc="no" removes a topic from navigation, while processing-role="resource-only" marks it as a non-output resource for keys or reuse.',
    xml: `<map>
  <keydef keys="legal" href="reuse/legal.dita" processing-role="resource-only"/>
  <topicref href="hidden-in-toc.dita" toc="no"/>
</map>`,
    expected: 'The resource-only topic remains available for reuse/key resolution; the toc="no" topic may still generate output.',
  },
]

export function LandingDocsPage() {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [isVideoOpen, setIsVideoOpen] = useState(false)
  const [activePreview, setActivePreview] = useState(0)
  const activeSlide = previewSlides[activePreview]
  const showPreviousSlide = () => setActivePreview((current) => (current === 0 ? previewSlides.length - 1 : current - 1))
  const showNextSlide = () => setActivePreview((current) => (current + 1) % previewSlides.length)

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
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-label="Previous senior answer"
                    onClick={(event) => {
                      event.stopPropagation()
                      showPreviousSlide()
                    }}
                    className="rounded-full bg-white/10 p-1.5 text-stone-300 transition hover:bg-white/20 hover:text-white"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="rounded-full bg-teal-400/10 px-3 py-1 text-xs font-semibold text-teal-200">
                    {activeSlide.badge}
                  </span>
                  <button
                    type="button"
                    aria-label="Next senior answer"
                    onClick={(event) => {
                      event.stopPropagation()
                      showNextSlide()
                    }}
                    className="rounded-full bg-white/10 p-1.5 text-stone-300 transition hover:bg-white/20 hover:text-white"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
                <div className="border-b border-white/10 p-6 lg:border-b-0 lg:border-r">
                  <p className="mb-4 text-sm font-semibold text-stone-400">Prompt</p>
                  <div className="rounded-2xl bg-white/5 p-5 text-lg font-semibold leading-8 text-white">
                    {activeSlide.prompt}
                  </div>
                  <div className="mt-5 space-y-3 text-sm text-stone-300">
                    {activeSlide.checks.map((item) => (
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
                      <span className="font-bold text-white">Short answer:</span> {activeSlide.answer}
                    </p>
                    <pre className="overflow-x-auto rounded-2xl bg-black/35 p-4 text-xs text-teal-100">
{activeSlide.xml}
                    </pre>
                    <p>
                      <span className="font-bold text-white">Expected result:</span> {activeSlide.expected}
                    </p>
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center gap-2 border-t border-white/10 px-5 py-3">
                {previewSlides.map((slide, index) => (
                  <button
                    key={slide.badge}
                    type="button"
                    aria-label={`Show ${slide.badge} preview`}
                    onClick={(event) => {
                      event.stopPropagation()
                      setActivePreview(index)
                    }}
                    className={`h-2 rounded-full transition ${
                      index === activePreview ? 'w-8 bg-teal-300' : 'w-2 bg-white/25 hover:bg-white/45'
                    }`}
                  />
                ))}
              </div>
            </div>
          </section>

          <section id="qa-video" className="mx-auto mt-16 max-w-5xl">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-stone-500">Product walkthrough</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-stone-950">
                  See senior Q&A in action
                </h2>
              </div>
              <Link to="/chat" className="hidden text-sm font-bold text-teal-700 transition hover:text-teal-900 sm:inline-flex">
                Try in chat <ArrowRight className="ml-1 h-4 w-4" />
              </Link>
            </div>

            <button
              type="button"
              onClick={() => setIsVideoOpen(true)}
              className="group grid w-full overflow-hidden rounded-[1.75rem] border border-stone-200 bg-white text-left shadow-xl shadow-stone-900/5 transition hover:-translate-y-0.5 hover:shadow-2xl hover:shadow-stone-900/10 lg:grid-cols-[1.05fr_0.95fr]"
            >
              <div className="relative min-h-[320px] overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(45,212,191,0.24),transparent_34%),linear-gradient(135deg,#111827,#020617)] p-6 text-white">
                <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.06)_1px,transparent_1px)] [background-size:28px_28px]" />
                <div className="relative flex h-full flex-col justify-between">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full bg-red-400" />
                      <span className="h-3 w-3 rounded-full bg-amber-300" />
                      <span className="h-3 w-3 rounded-full bg-emerald-400" />
                    </div>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-100">
                      2 min demo
                    </span>
                  </div>

                  <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-white/15 text-white shadow-2xl backdrop-blur transition group-hover:scale-105 group-hover:bg-teal-400/25">
                    <PlayCircle className="h-12 w-12" />
                  </div>

                  <div>
                    <p className="text-sm font-semibold text-teal-200">Question</p>
                    <p className="mt-2 max-w-xl text-2xl font-semibold leading-9">
                      “A keyref works in one map but not another. What should I check?”
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-7">
                <p className="text-sm font-semibold text-stone-500">What the video shows</p>
                <div className="mt-5 space-y-4">
                  {[
                    'How the bot detects map context and keyscope issues.',
                    'How it separates DITA specification behavior from processor behavior.',
                    'How the final answer includes checks, XML examples, and expected result.',
                  ].map((item) => (
                    <div key={item} className="flex gap-3 rounded-2xl bg-stone-50 p-4 text-sm font-semibold leading-6 text-stone-700">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-teal-600" />
                      {item}
                    </div>
                  ))}
                </div>
                <div className="mt-6 flex items-center gap-2 text-sm font-bold text-teal-700">
                  Watch Q&A demo
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </div>
              </div>
            </button>
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

          <section id="sources" className="mx-auto mt-16 grid max-w-5xl gap-6 lg:grid-cols-[0.95fr_1.05fr]">
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
            <p className="mb-4 text-sm font-semibold text-stone-500">On this page</p>
            <nav className="space-y-3 border-b border-stone-200 pb-6">
              {[
                { label: 'Welcome', href: '#welcome' },
                { label: 'Q&A demo', href: '#qa-video' },
                { label: 'What this bot does', href: '#features' },
                { label: 'Sources and prompts', href: '#sources' },
              ].map((item) => (
                <a key={item.label} href={item.href} className="block text-sm font-medium text-stone-500 transition hover:text-stone-950">
                  {item.label}
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

      {isVideoOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Questions and answers product video"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-6 backdrop-blur-sm"
          onClick={() => setIsVideoOpen(false)}
        >
          <div
            className="max-h-[88vh] w-full max-w-5xl overflow-hidden rounded-[1.75rem] border border-white/15 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4">
              <div>
                <p className="text-sm font-bold text-stone-950">Q&A product walkthrough</p>
                <p className="text-xs text-stone-500">Senior answer flow for DITA troubleshooting</p>
              </div>
              <button
                type="button"
                aria-label="Close video"
                onClick={() => setIsVideoOpen(false)}
                className="rounded-full bg-stone-100 p-2 text-stone-700 transition hover:bg-stone-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid max-h-[calc(88vh-65px)] overflow-auto lg:grid-cols-[1.1fr_0.9fr]">
              <div className="relative min-h-[460px] bg-[radial-gradient(circle_at_top_left,rgba(20,184,166,0.22),transparent_34%),linear-gradient(135deg,#0f172a,#020617)] p-8 text-white">
                <div className="absolute inset-0 opacity-25 [background-image:linear-gradient(rgba(255,255,255,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:32px_32px]" />
                <div className="relative flex h-full flex-col">
                  <div className="mb-8 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full bg-red-400" />
                      <span className="h-3 w-3 rounded-full bg-amber-300" />
                      <span className="h-3 w-3 rounded-full bg-emerald-400" />
                    </div>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-100">Demo preview</span>
                  </div>

                  <div className="space-y-4">
                    <div className="max-w-xl rounded-2xl bg-white/10 p-5 backdrop-blur">
                      <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-200">User question</p>
                      <p className="mt-3 text-2xl font-semibold leading-9">
                        A keyref works in one map but not another. What processing contexts should I check?
                      </p>
                    </div>
                    <div className="ml-auto max-w-xl rounded-2xl bg-teal-400/15 p-5 backdrop-blur">
                      <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-100">Senior answer</p>
                      <p className="mt-3 leading-7 text-stone-100">
                        Check the active root map, keyscope branch, filtered key definitions, and whether the topic
                        is being previewed outside its intended map context.
                      </p>
                    </div>
                  </div>

                  <div className="mt-auto">
                    <div className="mt-10 h-1.5 overflow-hidden rounded-full bg-white/15">
                      <div className="h-full w-2/3 rounded-full bg-teal-300" />
                    </div>
                    <div className="mt-4 flex items-center justify-between text-xs font-semibold text-stone-300">
                      <span>00:42</span>
                      <span>02:00</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-7">
                <p className="text-sm font-bold text-stone-950">Transcript highlights</p>
                <div className="mt-5 space-y-4">
                  {[
                    ['1', 'Detect whether the user is asking about direct URI resolution or key-based resolution.'],
                    ['2', 'Retrieve learned Q&A and DITA map/keyscope source chunks before generic context.'],
                    ['3', 'Answer with expected behavior, probable causes, deterministic checks, and XML example.'],
                  ].map(([step, text]) => (
                    <div key={step} className="flex gap-4 rounded-2xl border border-stone-200 bg-stone-50 p-4">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-100 text-sm font-black text-teal-800">
                        {step}
                      </div>
                      <p className="text-sm font-medium leading-6 text-stone-700">{text}</p>
                    </div>
                  ))}
                </div>
                <Link
                  to="/chat"
                  onClick={() => setIsVideoOpen(false)}
                  className="mt-6 inline-flex items-center gap-2 rounded-full bg-stone-950 px-5 py-3 text-sm font-bold text-white transition hover:bg-teal-700"
                >
                  Try this in chat
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

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
                <span className="ml-3 text-sm font-semibold text-stone-300">{activeSlide.badge}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  aria-label="Previous senior answer"
                  onClick={showPreviousSlide}
                  className="rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  aria-label="Next senior answer"
                  onClick={showNextSlide}
                  className="rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  aria-label="Close preview"
                  onClick={() => setIsPreviewOpen(false)}
                  className="rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>
            <div className="grid max-h-[calc(88vh-57px)] overflow-auto lg:grid-cols-[0.9fr_1.1fr]">
              <div className="border-b border-white/10 p-8 lg:border-b-0 lg:border-r">
                <p className="mb-4 text-sm font-semibold text-stone-400">Prompt</p>
                <div className="rounded-2xl bg-white/5 p-6 text-2xl font-semibold leading-10 text-white">
                  {activeSlide.prompt}
                </div>
                <div className="mt-6 space-y-4 text-base text-stone-300">
                  {activeSlide.checks.map((item) => (
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
                    <span className="font-bold text-white">Short answer:</span> {activeSlide.answer}
                  </p>
                  <pre className="overflow-x-auto rounded-2xl bg-black/35 p-5 text-sm text-teal-100">
{activeSlide.xml}
                  </pre>
                  <p>
                    <span className="font-bold text-white">Expected result:</span> {activeSlide.expected}
                  </p>
                  <div className="flex gap-2 pt-2">
                    {previewSlides.map((slide, index) => (
                      <button
                        key={slide.badge}
                        type="button"
                        aria-label={`Show ${slide.badge} preview`}
                        onClick={() => setActivePreview(index)}
                        className={`h-2 rounded-full transition ${
                          index === activePreview ? 'w-8 bg-teal-300' : 'w-2 bg-white/25 hover:bg-white/45'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
