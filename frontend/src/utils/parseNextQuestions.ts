/**
 * Extract follow-up questions from assistant markdown when the model ends with
 * `## Next questions` (see CHAT_SUGGEST_FOLLOWUPS in backend chat_service).
 */
const NEXT_Q_HEADER = /(?:^|\n)##\s*Next questions?\s*(?:\n|$)/i;

export function parseNextQuestionsFromMarkdown(content: string | null | undefined): string[] {
  const text = (content || '').trim();
  if (!text) return [];

  const m = text.match(NEXT_Q_HEADER);
  if (!m || m.index === undefined) return [];

  const afterHeader = text.slice(m.index + m[0].length);
  const nextSection = afterHeader.search(/\n(?=##\s)/);
  const block = nextSection >= 0 ? afterHeader.slice(0, nextSection) : afterHeader;

  const out: string[] = [];
  for (const rawLine of block.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;
    const bullet = line.match(/^[-*•]\s+(.+)$/);
    const numbered = line.match(/^\d+[\.)]\s+(.+)$/);
    const captured = (bullet?.[1] ?? numbered?.[1])?.trim();
    if (!captured || captured.length < 2) continue;
    const cleaned = captured
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/`+/g, '')
      .trim();
    if (cleaned.length < 2) continue;
    out.push(cleaned.length > 400 ? `${cleaned.slice(0, 397)}…` : cleaned);
    if (out.length >= 8) break;
  }
  return out;
}
