import { describe, expect, it } from 'vitest';
import { parseNextQuestionsFromMarkdown } from './parseNextQuestions';

describe('parseNextQuestionsFromMarkdown', () => {
  it('returns empty when no section', () => {
    expect(parseNextQuestionsFromMarkdown('Hello')).toEqual([]);
  });

  it('parses bullets under Next questions', () => {
    const md = `Here is help.\n\n## Next questions\n- First thing?\n- Second thing?\n`;
    expect(parseNextQuestionsFromMarkdown(md)).toEqual(['First thing?', 'Second thing?']);
  });

  it('stops at next heading', () => {
    const md = `## Next questions\n- A?\n\n## Sources\n- ignore`;
    expect(parseNextQuestionsFromMarkdown(md)).toEqual(['A?']);
  });
});
