export function primeVoiceoverAudio(src: string): void {
  const audio = new Audio(src)
  audio.preload = 'auto'
  audio.load()
}
