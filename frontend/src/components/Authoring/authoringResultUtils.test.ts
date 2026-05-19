import { describe, expect, it } from 'vitest';
import {
  buildAuthoringGenerationSnapshot,
  formatReviewIssueLine,
  generationOptionPills,
  splitAuthoringValidation,
  summarizeAuthoringGenerationDelta,
} from './authoringResultUtils';
import type { ChatDitaAuthoringResult } from '@/api/chat';

describe('formatReviewIssueLine', () => {
  it('formats checklist items with passing flag without JSON dump', () => {
    expect(formatReviewIssueLine({ label: 'shortdesc present', passing: true })).toBe('shortdesc present — passed');
    expect(formatReviewIssueLine({ label: 'taskbody present', passing: false })).toBe('taskbody present — failed');
  });
});

describe('splitAuthoringValidation', () => {
  it('collects blocking issues and review-derived warnings', () => {
    const result: ChatDitaAuthoringResult = {
      status: 'invalid',
      title: 'T',
      dita_type: 'task',
      xml_preview: '<task/>',
      validation_result: {
        valid: false,
        validator_errors: ['e1'],
        structural_issues: ['s1'],
        review_issues: [{ label: 'Review', message: 'r1' }],
      },
    };
    const { blockingIssues, warnings } = splitAuthoringValidation(result);
    expect(blockingIssues).toContain('e1');
    expect(blockingIssues).toContain('s1');
    expect(warnings.some((w) => w.includes('r1'))).toBe(true);
  });

  it('renders review checklist items as human-readable lines', () => {
    const result: ChatDitaAuthoringResult = {
      status: 'valid',
      title: 'T',
      dita_type: 'task',
      xml_preview: '<task/>',
      validation_result: {
        valid: true,
        review_issues: [{ label: 'steps present', passing: true }],
      },
    };
    const { warnings } = splitAuthoringValidation(result);
    expect(warnings).toContain('steps present — passed');
    expect(warnings.some((w) => w.includes('"passing"'))).toBe(false);
  });
});

describe('summarizeAuthoringGenerationDelta', () => {
  it('reports title and validation changes', () => {
    const a = buildAuthoringGenerationSnapshot(
      {
        status: 'valid',
        title: 'A',
        dita_type: 'task',
        xml_preview: '<task/>',
        validation_result: { valid: true },
      } as ChatDitaAuthoringResult,
      ['type: task']
    );
    const b = buildAuthoringGenerationSnapshot(
      {
        status: 'invalid',
        title: 'B',
        dita_type: 'task',
        xml_preview: '<task><title>B</title></task>',
        validation_result: { valid: false, validator_errors: ['e1'] },
      } as ChatDitaAuthoringResult,
      ['type: concept']
    );
    const { bullets } = summarizeAuthoringGenerationDelta(a, b);
    expect(bullets.some((x) => x.includes('Title'))).toBe(true);
    expect(bullets.some((x) => x.includes('Validation'))).toBe(true);
    expect(bullets.some((x) => x.includes('options'))).toBe(true);
  });
});

describe('generationOptionPills', () => {
  it('returns non-empty pills for typical options', () => {
    const pills = generationOptionPills({
      dita_type: 'task',
      style_strictness: 'high',
      output_mode: 'xml_validation',
    });
    expect(pills.length).toBeGreaterThan(0);
    expect(pills.some((p) => p.includes('task'))).toBe(true);
  });
});
