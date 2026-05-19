import { describe, expect, it } from 'vitest';
import {
  buildAuthoringMentionCandidates,
  filterAuthoringMentionCandidates,
  getActiveAuthoringMention,
  replaceAuthoringMentionInValue,
} from './authoringMentionUtils';

describe('getActiveAuthoringMention', () => {
  it('returns null when @ is inside a word', () => {
    expect(getActiveAuthoringMention('a@b', 3)).toBeNull();
  });

  it('returns query after @ at line start', () => {
    expect(getActiveAuthoringMention('@shot', 5)).toEqual({ start: 0, query: 'shot' });
  });

  it('returns query after @ following whitespace', () => {
    expect(getActiveAuthoringMention('see @ref', 8)).toEqual({ start: 4, query: 'ref' });
  });

  it('returns null when mention contains space', () => {
    expect(getActiveAuthoringMention('see @a b', 8)).toBeNull();
  });
});

describe('replaceAuthoringMentionInValue', () => {
  it('replaces the active range with @filename and trailing space', () => {
    const { nextValue, caretAfter } = replaceAuthoringMentionInValue('doc @x', { start: 4, end: 6 }, 'ui.png');
    expect(nextValue).toBe('doc @ui.png ');
    expect(caretAfter).toBe(nextValue.length);
  });
});

describe('buildAuthoringMentionCandidates / filter', () => {
  it('includes pick actions and attached files', () => {
    const img = new File(['x'], 'cap.png', { type: 'image/png' });
    const dita = new File(['<task/>'], 'ref.dita', { type: 'application/xml' });
    const all = buildAuthoringMentionCandidates(img, dita);
    expect(all.some((c) => c.type === 'action' && c.kind === 'pick-image')).toBe(true);
    expect(all.some((c) => c.type === 'attachment' && c.fileName === 'cap.png')).toBe(true);
    expect(all.some((c) => c.type === 'attachment' && c.fileName === 'ref.dita')).toBe(true);
  });

  it('filters by query', () => {
    const all = buildAuthoringMentionCandidates(null, null);
    const filtered = filterAuthoringMentionCandidates(all, 'dita');
    expect(filtered.every((c) => `${c.label} ${'description' in c ? c.description : ''}`.toLowerCase().includes('dita'))).toBe(
      true
    );
  });
});
