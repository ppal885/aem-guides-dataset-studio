import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Maximize2, Pause, Play, Volume2, VolumeX } from 'lucide-react'
import { primeVoiceoverAudio } from '../../lib/docsVoiceover'

const demoPrompt =
  'A keyref works in one map but not another. What processing contexts should I check?'

export const videoSteps = [
  {
    label: 'Question intake',
    audioSrc: '/audio/docs-demo/step-1.mp3',
    voiceover:
      'When a documentation team asks why a keyref works in one map but not another, the bot first classifies the question.',
    tags: ['Key resolution', 'Map context', 'Not a generic XML error'],
  },
  {
    label: 'Source retrieval',
    audioSrc: '/audio/docs-demo/step-2.mp3',
    voiceover:
      'Next, the assistant retrieves evidence from approved sources before falling back to generic context.',
    sources: ['Learned Q&A', 'DITA 1.3 keyscope spec', 'DITA-OT preprocessing docs', 'AEM Guides map behavior'],
  },
  {
    label: 'Senior reasoning',
    audioSrc: '/audio/docs-demo/step-3.mp3',
    voiceover:
      'Then the bot applies senior reasoning across map context, keyscope, and filtered key definitions.',
    checks: [
      'Confirm the active root map for preview',
      'Check keyscope branch boundaries',
      'Verify filtered keydefs still resolve',
      'Compare HTML path vs PDF path',
    ],
  },
  {
    label: 'Final answer',
    audioSrc: '/audio/docs-demo/step-4.mp3',
    voiceover:
      'Finally, you receive a complete answer with scope, checks, a map example, and the expected result.',
    answer:
      'Start with the active map context, then inspect keyscope, filtered keydefs, and whether the topic is previewed outside its intended branch.',
    xml: `<map>
  <topicref keyscope="productA">
    <keydef keys="install" href="install-a.dita"/>
    <topicref href="guide.dita"/>
  </topicref>
</map>`,
    expected: 'Keys inside productA resolve in that branch before broader map scope.',
  },
] as const

const PLAYBACK_VOLUME = 0.82
const PLAYBACK_RATE = 0.96

function formatTimestamp(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(safeSeconds / 60)
  const seconds = safeSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

async function loadAudioDuration(src: string): Promise<number> {
  return new Promise((resolve) => {
    const audio = new Audio(src)
    const finish = (duration: number) => {
      audio.removeEventListener('loadedmetadata', onReady)
      audio.removeEventListener('error', onError)
      resolve(duration)
    }
    const onReady = () => finish(Number.isFinite(audio.duration) ? audio.duration : 0)
    const onError = () => finish(0)
    audio.addEventListener('loadedmetadata', onReady)
    audio.addEventListener('error', onError)
    audio.load()
  })
}

function VideoStepPanel({ stepIndex }: { stepIndex: number }) {
  const step = videoSteps[stepIndex]

  if (stepIndex === 0 && 'tags' in step) {
    return (
      <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-teal-200/80">Classification</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {step.tags.map((tag) => (
            <span key={tag} className="rounded-full border border-teal-400/25 bg-teal-400/10 px-2 py-0.5 text-[11px] text-teal-100">
              {tag}
            </span>
          ))}
        </div>
        <p className="mt-3 text-[12px] leading-5 text-stone-300">
          The bot separates keyref troubleshooting from generic XML validation or authoring mistakes.
        </p>
      </div>
    )
  }

  if (stepIndex === 1 && 'sources' in step) {
    return (
      <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-teal-200/80">Retrieved sources</p>
        <ul className="mt-2 space-y-1.5">
          {step.sources.map((source) => (
            <li key={source} className="flex items-center gap-2 text-[12px] text-stone-200">
              <span className="h-1.5 w-1.5 rounded-full bg-teal-300" />
              {source}
            </li>
          ))}
        </ul>
      </div>
    )
  }

  if (stepIndex === 2 && 'checks' in step) {
    return (
      <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-teal-200/80">Deterministic checks</p>
        <ol className="mt-2 space-y-1.5">
          {step.checks.map((check, index) => (
            <li key={check} className="flex gap-2 text-[12px] leading-5 text-stone-200">
              <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border border-white/15 text-[10px] text-stone-400">
                {index + 1}
              </span>
              {check}
            </li>
          ))}
        </ol>
      </div>
    )
  }

  if (stepIndex === 3 && 'answer' in step) {
    return (
      <div className="space-y-2">
        <div className="rounded-md border border-white/10 bg-teal-400/10 p-3">
          <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-teal-100/90">Senior answer</p>
          <p className="mt-2 text-[12px] leading-5 text-stone-100">{step.answer}</p>
        </div>
        <pre className="overflow-x-auto rounded-md border border-white/10 bg-black/40 p-2.5 text-[10px] leading-4 text-teal-100">
          {step.xml}
        </pre>
        <p className="text-[11px] leading-5 text-stone-300">
          <span className="font-medium text-white">Expected:</span> {step.expected}
        </p>
      </div>
    )
  }

  return null
}

type DocsVideoDemoProps = {
  activeStep?: number
  onStepChange?: (step: number) => void
}

export function DocsVideoDemo({ activeStep, onStepChange }: DocsVideoDemoProps) {
  const [internalStep, setInternalStep] = useState(0)
  const [isVideoPlaying, setIsVideoPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [totalDurationSeconds, setTotalDurationSeconds] = useState(0)
  const stepOffsetsRef = useRef<number[]>(videoSteps.map(() => 0))
  const stepDurationsRef = useRef<number[]>(videoSteps.map(() => 0))
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const mutedTimerRef = useRef<number | null>(null)
  const mutedStartedAtRef = useRef<number>(0)

  const activeVideoStep = activeStep ?? internalStep
  const setActiveVideoStep = onStepChange ?? setInternalStep
  const activeVideo = videoSteps[activeVideoStep]
  const progressPercent =
    totalDurationSeconds > 0 ? Math.min(100, (elapsedSeconds / totalDurationSeconds) * 100) : 0

  useEffect(() => {
    videoSteps.forEach((step) => primeVoiceoverAudio(step.audioSrc))

    void (async () => {
      const durations = await Promise.all(videoSteps.map((step) => loadAudioDuration(step.audioSrc)))
      const offsets: number[] = []
      let total = 0

      durations.forEach((duration, index) => {
        offsets[index] = total
        total += duration
      })

      stepDurationsRef.current = durations
      stepOffsetsRef.current = offsets
      setTotalDurationSeconds(total)
    })()
  }, [])

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      if (mutedTimerRef.current !== null) {
        window.clearInterval(mutedTimerRef.current)
      }
    }
  }, [])

  const clearMutedTimer = () => {
    if (mutedTimerRef.current !== null) {
      window.clearInterval(mutedTimerRef.current)
      mutedTimerRef.current = null
    }
  }

  const updateElapsedFromAudio = useCallback((stepIndex: number, audio: HTMLAudioElement) => {
    setElapsedSeconds(stepOffsetsRef.current[stepIndex] + audio.currentTime)
  }, [])

  const pausePlayback = useCallback(() => {
    clearMutedTimer()
    audioRef.current?.pause()
    setIsVideoPlaying(false)
  }, [])

  const stopPlayback = useCallback(() => {
    clearMutedTimer()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
    }
    setIsVideoPlaying(false)
  }, [])

  const playMutedStep = useCallback(
    (stepIndex: number, autoAdvance: boolean) => {
      clearMutedTimer()
      setActiveVideoStep(stepIndex)
      setElapsedSeconds(stepOffsetsRef.current[stepIndex] ?? 0)

      mutedStartedAtRef.current = performance.now()

      mutedTimerRef.current = window.setInterval(() => {
        const stepOffset = stepOffsetsRef.current[stepIndex] ?? 0
        const elapsedInStep = (performance.now() - mutedStartedAtRef.current) / 1000
        const stepDuration = stepDurationsRef.current[stepIndex] || 4.5
        setElapsedSeconds(stepOffset + Math.min(elapsedInStep, stepDuration))

        if (elapsedInStep >= stepDuration) {
          clearMutedTimer()
          if (autoAdvance && stepIndex < videoSteps.length - 1) {
            playMutedStep(stepIndex + 1, true)
            return
          }
          setIsVideoPlaying(false)
        }
      }, 100)
    },
    [setActiveVideoStep],
  )

  const playStep = useCallback(
    (stepIndex: number, autoAdvance: boolean) => {
      const step = videoSteps[stepIndex]
      if (!step) {
        return
      }

      clearMutedTimer()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }

      setActiveVideoStep(stepIndex)

      if (isMuted) {
        setIsVideoPlaying(true)
        playMutedStep(stepIndex, autoAdvance)
        return
      }

      const audio = new Audio(step.audioSrc)
      audio.volume = PLAYBACK_VOLUME
      audio.playbackRate = PLAYBACK_RATE
      audioRef.current = audio

      const onTimeUpdate = () => updateElapsedFromAudio(stepIndex, audio)
      const finish = () => {
        audio.removeEventListener('timeupdate', onTimeUpdate)
        audio.removeEventListener('ended', finish)
        audio.removeEventListener('error', finish)
        audioRef.current = null

        const stepEnd = (stepOffsetsRef.current[stepIndex] ?? 0) + (stepDurationsRef.current[stepIndex] ?? 0)
        setElapsedSeconds(stepEnd)

        if (autoAdvance && stepIndex < videoSteps.length - 1) {
          playStep(stepIndex + 1, true)
          return
        }

        setIsVideoPlaying(false)
      }

      audio.addEventListener('timeupdate', onTimeUpdate)
      audio.addEventListener('ended', finish)
      audio.addEventListener('error', finish)

      void audio.play().then(() => {
        updateElapsedFromAudio(stepIndex, audio)
      }).catch(() => {
        finish()
      })
    },
    [isMuted, playMutedStep, setActiveVideoStep, updateElapsedFromAudio],
  )

  const togglePlayback = () => {
    if (isVideoPlaying) {
      pausePlayback()
      return
    }

    setIsVideoPlaying(true)

    if (audioRef.current && !isMuted) {
      void audioRef.current.play()
      return
    }

    playStep(activeVideoStep, true)
  }

  const jumpToStep = (index: number) => {
    stopPlayback()
    setActiveVideoStep(index)
    setElapsedSeconds(stepOffsetsRef.current[index] ?? 0)
  }

  const toggleMute = () => {
    setIsMuted((current) => {
      const nextMuted = !current
      if (nextMuted) {
        pausePlayback()
      }
      return nextMuted
    })
  }

  return (
    <section id="qa-video" className="mx-auto max-w-3xl">
      <div className="overflow-hidden rounded-lg border border-stone-200 bg-black">
        <div className="relative aspect-video bg-stone-900">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_0%,rgba(45,212,191,0.12),transparent_40%),linear-gradient(180deg,#111827_0%,#09090b_100%)]" />

          <div className="absolute inset-0 flex flex-col p-4 pb-12">
            <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-2">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-teal-500/20 text-teal-200">
                  <Bot className="h-3.5 w-3.5" />
                </div>
                <div>
                  <p className="text-[11px] font-medium text-white">DITA Expert Bot</p>
                  <p className="text-[10px] text-stone-400">Senior Q&amp;A walkthrough</p>
                </div>
              </div>
              <span className="rounded-md border border-white/10 px-2 py-0.5 text-[10px] font-medium text-stone-300">
                Step {activeVideoStep + 1} · {activeVideo.label}
              </span>
            </div>

            <div className="min-h-0 flex-1 space-y-2.5 overflow-hidden">
              <div className="rounded-md border border-white/10 bg-white/[0.06] p-3">
                <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-stone-400">Prompt</p>
                <p className="mt-1.5 text-[13px] leading-5 text-white">{demoPrompt}</p>
              </div>

              <VideoStepPanel stepIndex={activeVideoStep} />
            </div>

            {(isVideoPlaying || activeVideo.voiceover) && (
              <div className="absolute inset-x-4 bottom-12 rounded-md border border-white/10 bg-black/55 px-3 py-2 backdrop-blur-sm">
                <p className="line-clamp-2 text-[11px] leading-4 text-white/85">{activeVideo.voiceover}</p>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 border-t border-stone-800 bg-[#1a1a1a] px-3 py-2">
          <button
            type="button"
            onClick={togglePlayback}
            aria-label={isVideoPlaying ? 'Pause' : 'Play'}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center text-white/90 transition hover:text-white"
          >
            {isVideoPlaying ? <Pause className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current" />}
          </button>
          <span className="shrink-0 text-[12px] tabular-nums text-white/70">
            {formatTimestamp(elapsedSeconds)}
          </span>
          <div className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-white/15">
            <div className="h-full rounded-full bg-white/80" style={{ width: `${progressPercent}%` }} />
          </div>
          <span className="shrink-0 text-[12px] tabular-nums text-white/70">
            {formatTimestamp(totalDurationSeconds)}
          </span>
          <button
            type="button"
            aria-label={isMuted ? 'Unmute' : 'Mute'}
            onClick={toggleMute}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center text-white/70 transition hover:text-white"
          >
            {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            aria-label="Fullscreen"
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center text-white/70 transition hover:text-white"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <p className="mt-8 text-[13px] font-medium text-stone-500">Get Started</p>
      <h1 className="mt-2 text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] text-stone-950">
        DITA Expert Bot walkthrough
      </h1>
      <p className="mt-4 max-w-2xl text-[15px] leading-7 text-stone-600">
        This walkthrough shows how the bot handles a real DITA troubleshooting question — from question intake and
        source retrieval through senior reasoning to a complete, source-grounded answer with XML and expected results.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        {videoSteps.map((step, index) => (
          <button
            key={step.label}
            type="button"
            onClick={() => jumpToStep(index)}
            className={`rounded-md border px-2.5 py-1 text-[12px] transition ${
              index === activeVideoStep
                ? 'border-stone-900 bg-stone-900 text-white'
                : 'border-stone-200 text-stone-600 hover:border-stone-300 hover:text-stone-900'
            }`}
          >
            {step.label}
          </button>
        ))}
      </div>

      <p className="mt-8 text-[15px] leading-7 text-stone-600">
        Ready to try it?{' '}
        <Link to="/chat" className="font-medium text-stone-900 underline underline-offset-2">
          Open AI Chat
        </Link>
      </p>
    </section>
  )
}

export function DocsVideoSidebarItems({
  activeStep,
  onSelect,
}: {
  activeStep: number
  onSelect: (step: number) => void
}) {
  return (
    <div className="space-y-0.5">
      {videoSteps.map((step, index) => (
        <button
          key={step.label}
          type="button"
          onClick={() => onSelect(index)}
          className={`flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition ${
            index === activeStep ? 'bg-stone-100 text-stone-950' : 'text-stone-600 hover:bg-stone-50 hover:text-stone-950'
          }`}
        >
          <span
            className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded border text-[10px] font-medium ${
              index === activeStep
                ? 'border-stone-400 bg-stone-200 text-stone-800'
                : 'border-stone-200 bg-stone-50 text-stone-500'
            }`}
          >
            {index + 1}
          </span>
          <span className="truncate text-[13px]">{step.label}</span>
        </button>
      ))}
    </div>
  )
}
