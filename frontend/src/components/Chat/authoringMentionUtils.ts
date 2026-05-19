/**
 * Parse an in-progress @mention in the authoring prompt (screenshot / reference DITA).
 * Avoids treating email local parts as mentions: @ must be at line start or after whitespace.
 */
export function getActiveAuthoringMention(
  text: string,
  caret: number
): { start: number; query: string } | null {
  if (caret < 0 || caret > text.length) return null;
  const before = text.slice(0, caret);
  const at = before.lastIndexOf('@');
  if (at === -1) return null;
  const afterAt = before.slice(at + 1);
  if (/\s/.test(afterAt)) return null;
  if (at > 0) {
    const prev = before[at - 1];
    if (prev !== undefined && !/\s/.test(prev)) return null;
  }
  return { start: at, query: afterAt };
}

export type AuthoringMentionCandidate =
  | { type: 'action'; id: string; label: string; description: string; kind: 'pick-image' | 'pick-dita' }
  | { type: 'attachment'; id: string; label: string; fileName: string; kind: 'image' | 'dita' };

export function buildAuthoringMentionCandidates(
  imageFile: File | null,
  referenceDitaFile: File | null
): AuthoringMentionCandidate[] {
  const list: AuthoringMentionCandidate[] = [
    {
      type: 'action',
      id: 'pick-image',
      label: 'Attach screenshot…',
      description: 'Choose an image from your device',
      kind: 'pick-image',
    },
    {
      type: 'action',
      id: 'pick-dita',
      label: 'Attach reference DITA…',
      description: 'Choose a .dita or .xml topic',
      kind: 'pick-dita',
    },
  ];
  if (imageFile) {
    list.push({
      type: 'attachment',
      id: 'current-image',
      label: imageFile.name,
      fileName: imageFile.name,
      kind: 'image',
    });
  }
  if (referenceDitaFile) {
    list.push({
      type: 'attachment',
      id: 'current-dita',
      label: referenceDitaFile.name,
      fileName: referenceDitaFile.name,
      kind: 'dita',
    });
  }
  return list;
}

export function filterAuthoringMentionCandidates(
  candidates: AuthoringMentionCandidate[],
  query: string
): AuthoringMentionCandidate[] {
  const q = query.trim().toLowerCase();
  if (!q) return candidates;
  return candidates.filter((c) => {
    const hay = `${c.label} ${c.type === 'action' ? c.description : ''}`.toLowerCase();
    return hay.includes(q);
  });
}

/** Safe token for inline @mention (single line, no control chars). */
export function mentionTokenForFileName(name: string): string {
  const source = (name || 'file').trim() || 'file';
  let cleaned = '';
  for (const ch of source) {
    if (ch === '\r' || ch === '\n' || ch === '\0') continue;
    cleaned += ch;
  }
  cleaned = cleaned.trim() || 'file';
  return `@${cleaned}`;
}

/** Replace `@query` at [start, end) with `@fileName ` and return new caret index after the inserted space. */
export function replaceAuthoringMentionInValue(
  value: string,
  range: { start: number; end: number },
  fileName: string
): { nextValue: string; caretAfter: number } {
  const insertion = `${mentionTokenForFileName(fileName)} `;
  const nextValue = value.slice(0, range.start) + insertion + value.slice(range.end);
  const caretAfter = range.start + insertion.length;
  return { nextValue, caretAfter };
}
