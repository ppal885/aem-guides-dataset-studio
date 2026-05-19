/**
 * Parse UAC Copilot markdown (uac_answer) into structured sections for compact UI.
 * Template matches prompts/uac_prompt.py (sections 4–6).
 */

export type ParsedScenario = {
  scenario: string;
  why: string;
  evidenceRaw: string;
  currentEvidence: string;
  similarEvidence: string;
  testLayer: string;
};

export type ParsedAutomationFit = {
  fit: string;
  bestLayer: string;
  reason: string;
  suggestedTestName: string;
};

const SECTION_HEADING_RE = /^###\s*(\d+)\.\s+.+$/gm;

/** Split markdown into section number -> body (without the heading line). */
export function splitUacSections(markdown: string): Record<number, string> {
  const text = markdown || '';
  const matches = [...text.matchAll(SECTION_HEADING_RE)];
  const sections: Record<number, string> = {};
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const num = parseInt(m[1], 10);
    const start = (m.index ?? 0) + m[0].length;
    const end = i + 1 < matches.length ? (matches[i + 1].index ?? text.length) : text.length;
    sections[num] = text.slice(start, end).trim();
  }
  return sections;
}

/** Split Evidence line into current vs similar columns (heuristic). */
export function splitScenarioEvidence(evidence: string): { current: string; similar: string } {
  const raw = (evidence || '').trim();
  if (!raw) return { current: '—', similar: '—' };

  const similarLabel = /\bsimilar\s*:/i;
  const currentLabel = /\bcurrent\s*:/i;

  const si = raw.search(similarLabel);
  const ci = raw.search(currentLabel);

  if (ci >= 0 && si >= 0) {
    const firstIsCurrent = ci < si;
    if (firstIsCurrent) {
      const cur = raw.slice(ci).replace(currentLabel, '').split(similarLabel)[0].trim().replace(/[,;]\s*$/, '');
      const sim = raw.slice(si).replace(similarLabel, '').trim();
      return {
        current: cur || '—',
        similar: sim || '—',
      };
    }
    const sim = raw.slice(si).replace(similarLabel, '').split(currentLabel)[0].trim().replace(/[,;]\s*$/, '');
    const cur = raw.slice(ci).replace(currentLabel, '').trim();
    return {
      current: cur || '—',
      similar: sim || '—',
    };
  }

  if (ci >= 0) {
    return { current: raw.slice(ci).replace(currentLabel, '').trim() || '—', similar: '—' };
  }
  if (si >= 0) {
    return { current: '—', similar: raw.slice(si).replace(similarLabel, '').trim() || '—' };
  }

  const keyMatch = raw.match(/\b([A-Z][A-Z0-9]+-\d+)\b/);
  if (keyMatch && /similar|\(similar/i.test(raw)) {
    return { current: '—', similar: raw };
  }

  return { current: raw, similar: '—' };
}

/** Extract fenced ``` blocks from section 4 body. */
function extractFencedBlocks(sectionBody: string): string[] {
  const blocks: string[] = [];
  const re = /```[\s\S]*?```/g;
  let m: RegExpExecArray | null;
  let text = sectionBody;
  while ((m = re.exec(text)) !== null) {
    const block = m[0].replace(/^```\w*\n?/, '').replace(/\n?```$/, '').trim();
    if (block) blocks.push(block);
  }
  return blocks;
}

export function parseMustTestScenarios(section4Body: string): ParsedScenario[] {
  const body = section4Body || '';
  const blocks = extractFencedBlocks(body);
  const out: ParsedScenario[] = [];

  for (const block of blocks) {
    const lines = block.split('\n').map((l) => l.trim());
    let scenario = '';
    let why = '';
    let evidence = '';
    let testLayer = '';

    for (const line of lines) {
      if (/^Scenario:/i.test(line)) scenario = line.replace(/^Scenario:\s*/i, '').trim();
      else if (/^Why:/i.test(line)) why = line.replace(/^Why:\s*/i, '').trim();
      else if (/^Evidence:/i.test(line)) evidence = line.replace(/^Evidence:\s*/i, '').trim();
      else if (/^Test Layer:/i.test(line)) testLayer = line.replace(/^Test Layer:\s*/i, '').trim();
    }

    if (!scenario && !why && !evidence) continue;

    const { current, similar } = splitScenarioEvidence(evidence);
    out.push({
      scenario: scenario || '—',
      why,
      evidenceRaw: evidence,
      currentEvidence: current,
      similarEvidence: similar,
      testLayer: testLayer || '—',
    });
  }

  return out;
}

/** Bullets from section 5 (Missing Clarifications). */
export function parseMissingClarifications(section5Body: string): string[] {
  const lines = (section5Body || '').split('\n');
  const items: string[] = [];
  for (const line of lines) {
    const m = line.match(/^\s*[-*•]\s+(.+)/);
    if (m) items.push(m[1].trim());
  }
  return items;
}

/** Parse Automation Fit section (subsection 6). */
export function parseAutomationFit(section6Body: string): ParsedAutomationFit {
  const body = section6Body || '';
  const lower = body;

  const pick = (label: RegExp): string => {
    const m = lower.match(label);
    return (m?.[1] ?? '').trim();
  };

  const fit =
    pick(/\*\*Fit:\*\*\s*([^\n]+)/i) ||
    pick(/-\s*\*\*Fit:\*\*\s*([^\n]+)/i) ||
    pick(/Fit:\s*\*?\*?([^|\n]+)/i);

  const bestLayer =
    pick(/\*\*Best Layer:\*\*\s*([^\n]+)/i) ||
    pick(/-\s*\*\*Best Layer:\*\*\s*([^\n]+)/i) ||
    pick(/Best Layer:\s*\*?\*?([^|\n]+)/i);

  let reason =
    pick(/\*\*Reason:\*\*\s*([\s\S]*?)(?=\n-\s*\*\*|\n\*\*Suggested|\n###|$)/i) ||
    pick(/Reason:\s*([\s\S]*?)(?=\n-\s*\*\*|\n\*\*Suggested|\n###|$)/i);

  reason = reason.replace(/\n+/g, ' ').trim();

  const suggestedTestName =
    pick(/\*\*Suggested test name:\*\*\s*([^\n]+)/i) ||
    pick(/Suggested test name:\s*([^\n]+)/i);

  return {
    fit: fit || '—',
    bestLayer: bestLayer || '—',
    reason: reason || '—',
    suggestedTestName: suggestedTestName || '—',
  };
}

export function parseUacAnswerMarkdown(markdown: string): {
  scenarios: ParsedScenario[];
  missingClarifications: string[];
  automation: ParsedAutomationFit;
} {
  const sections = splitUacSections(markdown || '');
  return {
    scenarios: parseMustTestScenarios(sections[4] || ''),
    missingClarifications: parseMissingClarifications(sections[5] || ''),
    automation: parseAutomationFit(sections[6] || ''),
  };
}

/** Compact bullets from section 2 (Why This Jira Is Risky). */
export function parseRiskHighlights(section2Body: string, max = 5): string[] {
  const items: string[] = [];
  for (const line of (section2Body || '').split('\n')) {
    const m = line.match(/^\s*[-*•]\s+(.+)/);
    if (m) items.push(m[1].trim());
    if (items.length >= max) break;
  }
  return items;
}
