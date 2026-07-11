import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Code2,
  Database,
  GitBranch,
  Maximize2,
  MessageSquare,
  ShieldCheck,
  X,
} from 'lucide-react'
import { DocsVideoDemo, DocsVideoSidebarItems } from '../components/Docs/DocsVideoDemo'

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
  const [activePreview, setActivePreview] = useState(0)
  const [activeVideoStep, setActiveVideoStep] = useState(0)
  const activeSlide = previewSlides[activePreview]
  const showPreviousSlide = () => setActivePreview((current) => (current === 0 ? previewSlides.length - 1 : current - 1))
  const showNextSlide = () => setActivePreview((current) => (current + 1) % previewSlides.length)

  return (
    <div className="min-h-[calc(100vh-56px)] bg-background text-foreground">
      <div className="mx-auto grid max-w-[1400px] grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_220px]">
        <aside className="hidden border-r border-border px-5 py-8 lg:block">
          <div className="sticky top-[72px] space-y-7">
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Walkthrough</p>
              <DocsVideoSidebarItems activeStep={activeVideoStep} onSelect={setActiveVideoStep} />
            </div>
            {sidebarSections.map((section) => (
              <div key={section.title}>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{section.title}</p>
                <nav className="space-y-0.5">
                  {section.items.map((item, index) => (
                    <a
                      key={item}
                      href={index === 0 && section.title === 'Get Started' ? '#welcome' : '#features'}
                      className={`block rounded-md px-2.5 py-1.5 text-[13px] transition ${
                        item === 'Welcome'
                          ? 'bg-muted font-medium text-foreground'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      {item}
                    </a>
                  ))}
                </nav>
              </div>
            ))}
          </div>
        </aside>

        <main className="min-w-0 px-6 py-8 sm:px-10 lg:px-12">
          <DocsVideoDemo activeStep={activeVideoStep} onStepChange={setActiveVideoStep} />

          <section id="welcome" className="mx-auto mt-14 max-w-3xl border-t border-border pt-10">
            <p className="text-[13px] font-medium text-muted-foreground">Overview</p>
            <h2 className="mt-2 text-[1.35rem] font-semibold tracking-[-0.02em] text-foreground">
              What this assistant does
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-muted-foreground">
              A senior DITA, AEM Guides, DITA-OT, XML reuse, publishing, and Jira troubleshooting assistant for
              documentation teams. Use it to get source-grounded explanations, full XML examples, expected results,
              and deterministic debugging checks.
            </p>

            <div className="mt-5 flex flex-wrap gap-2">
              {quickLinks.map((item) => {
                const Icon = item.icon
                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] font-medium text-foreground transition hover:border-border hover:text-foreground"
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          </section>

          <section id="example" className="mx-auto mt-10 max-w-3xl">
            <p className="mb-3 text-[13px] font-medium text-muted-foreground">Example answer</p>
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
              className="group relative cursor-zoom-in overflow-hidden rounded-lg border border-border bg-stone-950 outline-none transition hover:border-border focus-visible:ring-2 focus-visible:ring-teal-500/30"
            >
              <div className="pointer-events-none absolute right-3 top-3 z-10 flex items-center gap-1.5 rounded-md bg-black/50 px-2 py-1 text-[11px] font-medium text-white opacity-0 backdrop-blur transition group-hover:opacity-100">
                <Maximize2 className="h-3 w-3" />
                Expand
              </div>
              <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
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
                    className="rounded-full bg-card/10 p-1.5 text-stone-300 transition hover:bg-card/20 hover:text-white"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="rounded-md bg-card/10 px-2 py-0.5 text-[11px] font-medium text-teal-100">
                    {activeSlide.badge}
                  </span>
                  <button
                    type="button"
                    aria-label="Next senior answer"
                    onClick={(event) => {
                      event.stopPropagation()
                      showNextSlide()
                    }}
                    className="rounded-full bg-card/10 p-1.5 text-stone-300 transition hover:bg-card/20 hover:text-white"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
                <div className="border-b border-white/10 p-4 lg:border-b-0 lg:border-r">
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">Prompt</p>
                  <div className="rounded-md bg-card/5 p-3 text-[14px] font-medium leading-6 text-white">
                    {activeSlide.prompt}
                  </div>
                  <div className="mt-3 space-y-2 text-[13px] text-stone-300">
                    {activeSlide.checks.map((item) => (
                      <div key={item} className="flex gap-2">
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 text-teal-300" />
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="p-4">
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">Answer shape</p>
                  <div className="space-y-3 text-[13px] leading-6 text-stone-200">
                    <p>
                      <span className="font-medium text-white">Short answer:</span> {activeSlide.answer}
                    </p>
                    <pre className="overflow-x-auto rounded-md bg-black/35 p-3 text-[11px] leading-5 text-teal-100">
{activeSlide.xml}
                    </pre>
                    <p>
                      <span className="font-medium text-white">Expected result:</span> {activeSlide.expected}
                    </p>
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center gap-1.5 border-t border-white/10 px-4 py-2">
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
                      index === activePreview ? 'w-8 bg-teal-300' : 'w-2 bg-card/25 hover:bg-card/45'
                    }`}
                  />
                ))}
              </div>
            </div>
          </section>

          <section id="features" className="mx-auto mt-14 max-w-3xl">
            <h2 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-foreground">What you can do with it</h2>
            <div className="mt-4 divide-y divide-border border-y border-border">
              {featureCards.map((card) => {
                const Icon = card.icon
                return (
                  <div key={card.title} className="grid gap-3 py-4 sm:grid-cols-[auto_1fr] sm:gap-4">
                    <div className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-muted text-foreground">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <h3 className="text-[15px] font-medium text-foreground">{card.title}</h3>
                      <p className="mt-1 text-[14px] leading-6 text-muted-foreground">{card.text}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>

          <section id="sources" className="mx-auto mt-14 max-w-3xl space-y-8">
            <div>
              <h2 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-foreground">Trusted sources</h2>
              <ul className="mt-4 divide-y divide-border border-y border-border">
                {['DITA 1.2 / 1.3 spec', 'DITA-OT docs and release notes', 'AEM Guides docs', 'Jira QA knowledge', 'Approved learned prompts'].map((source) => (
                  <li key={source} className="flex items-center gap-2.5 py-2.5 text-[14px] text-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-teal-600" />
                    {source}
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h2 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-foreground">Try prompts</h2>
              <div className="mt-4 divide-y divide-border border-y border-border">
                {prompts.map((prompt) => (
                  <Link
                    key={prompt}
                    to="/chat"
                    className="group flex items-center justify-between gap-3 py-2.5 text-[14px] text-foreground transition hover:text-teal-800"
                  >
                    {prompt}
                    <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-0 transition group-hover:opacity-100" />
                  </Link>
                ))}
              </div>
            </div>
          </section>
        </main>

        <aside className="hidden border-l border-border px-6 py-8 xl:block">
          <div className="sticky top-24">
            <p className="mb-3 text-[12px] font-medium text-muted-foreground">On this page</p>
            <nav className="space-y-2 border-b border-border pb-5">
              {[
                { label: 'Welcome', href: '#welcome' },
                { label: 'Q&A demo', href: '#qa-video' },
                { label: 'What this bot does', href: '#features' },
                { label: 'Sources and prompts', href: '#sources' },
              ].map((item) => (
                <a key={item.label} href={item.href} className="block text-[13px] text-muted-foreground transition hover:text-foreground">
                  {item.label}
                </a>
              ))}
            </nav>
            <div className="mt-5 space-y-2.5 text-[13px] text-muted-foreground">
              <Link to="/chat" className="block transition hover:text-teal-700">
                Ask AI Chat
              </Link>
              <Link to="/settings" className="block transition hover:text-teal-700">
                Check RAG status
              </Link>
              <span className="block">Slack-ready</span>
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
                <span className="ml-3 text-sm font-semibold text-stone-300">{activeSlide.badge}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  aria-label="Previous senior answer"
                  onClick={showPreviousSlide}
                  className="rounded-full bg-card/10 p-2 text-white transition hover:bg-card/20"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  aria-label="Next senior answer"
                  onClick={showNextSlide}
                  className="rounded-full bg-card/10 p-2 text-white transition hover:bg-card/20"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  aria-label="Close preview"
                  onClick={() => setIsPreviewOpen(false)}
                  className="rounded-full bg-card/10 p-2 text-white transition hover:bg-card/20"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>
            <div className="grid max-h-[calc(88vh-57px)] overflow-auto lg:grid-cols-[0.9fr_1.1fr]">
              <div className="border-b border-white/10 p-8 lg:border-b-0 lg:border-r">
                <p className="mb-4 text-sm font-semibold text-muted-foreground">Prompt</p>
                <div className="rounded-2xl bg-card/5 p-6 text-2xl font-semibold leading-10 text-white">
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
                <p className="mb-4 text-sm font-semibold text-muted-foreground">Answer shape</p>
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
                          index === activePreview ? 'w-8 bg-teal-300' : 'w-2 bg-card/25 hover:bg-card/45'
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
