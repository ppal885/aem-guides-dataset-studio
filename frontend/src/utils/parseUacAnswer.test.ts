import { describe, expect, it } from 'vitest';
import {
  parseAutomationFit,
  parseMissingClarifications,
  parseMustTestScenarios,
  parseUacAnswerMarkdown,
  splitScenarioEvidence,
  splitUacSections,
} from './parseUacAnswer';

describe('splitUacSections', () => {
  it('splits numbered ### sections', () => {
    const md = `### 1. A\nx\n\n### 4. B\ny\n`;
    const s = splitUacSections(md);
    expect(s[1]).toBe('x');
    expect(s[4]).toBe('y');
  });
});

describe('splitScenarioEvidence', () => {
  it('splits current and similar labels', () => {
    const { current, similar } = splitScenarioEvidence(
      'current: summary field; similar: DXML-1 — repro snippet'
    );
    expect(current).toContain('summary');
    expect(similar).toContain('DXML-1');
  });
});

describe('parseMustTestScenarios', () => {
  it('parses fenced scenario blocks', () => {
    const body = `
\`\`\`
Scenario: Publish map
Why: Regression in PDF
Evidence: current: native_pdf; similar: GUIDES-2 — log
Test Layer: Publishing
\`\`\`
`;
    const rows = parseMustTestScenarios(body);
    expect(rows).toHaveLength(1);
    expect(rows[0].scenario).toBe('Publish map');
    expect(rows[0].testLayer).toBe('Publishing');
  });
});

describe('parseMissingClarifications', () => {
  it('collects bullets', () => {
    const items = parseMissingClarifications('- What version?\n- Which preset?');
    expect(items).toEqual(['What version?', 'Which preset?']);
  });
});

describe('parseAutomationFit', () => {
  it('parses bold labels', () => {
    const body = `- **Fit:** Partial\n- **Best Layer:** UI\n- **Reason:** Smoke test.\n- **Suggested test name:** foo_bar`;
    const a = parseAutomationFit(body);
    expect(a.fit).toMatch(/Partial/);
    expect(a.bestLayer).toMatch(/UI/);
  });
});

describe('parseUacAnswerMarkdown', () => {
  it('returns structured parts', () => {
    const md = `### 4. Must-Test Scenarios
\`\`\`
Scenario: S1
Why: W1
Evidence: only current text
Test Layer: Manual
\`\`\`

### 5. Missing Clarifications for UAC
- Q1

### 6. Automation Fit
- **Fit:** No
- **Best Layer:** Manual
- **Reason:** N/A
- **Suggested test name:** t1
`;
    const p = parseUacAnswerMarkdown(md);
    expect(p.scenarios).toHaveLength(1);
    expect(p.missingClarifications).toContain('Q1');
    expect(p.automation.fit).toMatch(/No/);
  });
});
