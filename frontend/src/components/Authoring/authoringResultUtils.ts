import type { ChatDitaAuthoringResult, ChatDitaGenerationOptions, ChatDitaValidationResult } from '@/api/chat';

function isReviewIssueRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Human-readable line for backend review checklist items ({ label, passing }) or freeform { label, message }. */
export function formatReviewIssueLine(item: Record<string, unknown>): string {
  const label = typeof item.label === 'string' ? item.label.trim() : '';
  const message = typeof item.message === 'string' ? item.message.trim() : '';
  if (typeof item.passing === 'boolean') {
    const status = item.passing ? 'passed' : 'failed';
    if (label) return `${label} — ${status}`;
    return status;
  }
  if (label && message) return `${label}: ${message}`;
  if (label) return label;
  if (message) return message;
  try {
    return JSON.stringify(item);
  } catch {
    return String(item);
  }
}

export function splitAuthoringValidation(result: ChatDitaAuthoringResult): {
  validation: ChatDitaValidationResult;
  blockingIssues: string[];
  warnings: string[];
} {
  const validation = result.validation_result || { valid: false };
  const blockingIssues = [
    ...(validation.validator_errors || []),
    ...(validation.aem_guides_validation_errors || []),
    ...(validation.structural_issues || []),
  ];
  const warnings = [...(validation.validator_warnings || [])];
  const review = validation.review_issues || [];
  for (const item of review.slice(0, 12)) {
    if (isReviewIssueRecord(item)) {
      warnings.push(formatReviewIssueLine(item));
    } else {
      warnings.push(String(item));
    }
  }
  return { validation, blockingIssues, warnings };
}

export function generationOptionPills(options: ChatDitaGenerationOptions | null | undefined): string[] {
  if (!options) return [];
  return [
    options.dita_type ? `type: ${options.dita_type}` : '',
    options.style_strictness ? `style: ${options.style_strictness}` : '',
    options.output_mode ? `output: ${options.output_mode}` : '',
    options.authoring_pattern ? `pattern: ${options.authoring_pattern}` : '',
    options.file_name ? `file: ${options.file_name}` : '',
    options.save_path ? `save: ${options.save_path}` : '',
    options.strict_validation === false ? 'strict validation: off' : '',
    options.preserve_prolog ? 'prolog: on' : '',
    options.preserve_reference_doctype ? 'ref DOCTYPE: on' : '',
    options.xref_placeholders ? 'xref placeholders: on' : '',
    options.auto_ids === false ? 'auto ids: off' : '',
  ].filter(Boolean);
}

export function ditaFileNameFromTitle(title: string): string {
  const base = (title || 'generated-topic')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  return `${base || 'generated-topic'}.dita`;
}

export interface AuthoringGenerationSnapshot {
  title: string;
  valid: boolean;
  blockingCount: number;
  warningCount: number;
  xmlLen: number;
  optionPillsKey: string;
}

export function buildAuthoringGenerationSnapshot(
  result: ChatDitaAuthoringResult,
  optionPills: string[]
): AuthoringGenerationSnapshot {
  const { validation, blockingIssues, warnings } = splitAuthoringValidation(result);
  const xml = (result.xml_preview || '').trim();
  return {
    title: result.title || '',
    valid: Boolean(validation.valid),
    blockingCount: blockingIssues.length,
    warningCount: warnings.length,
    xmlLen: xml.length,
    optionPillsKey: optionPills.slice().sort().join('|'),
  };
}

function fmtBool(v: boolean): string {
  return v ? 'pass' : 'fail';
}

/** Compare two runs for a compact “what changed” summary (no XML diff). */
export function summarizeAuthoringGenerationDelta(
  prev: AuthoringGenerationSnapshot | null,
  next: AuthoringGenerationSnapshot
): { headline: string; bullets: string[] } {
  if (!prev) {
    return { headline: 'First generation in this view.', bullets: [] };
  }
  const bullets: string[] = [];
  if (prev.title !== next.title) {
    bullets.push(`Title: "${prev.title || '(none)'}" → "${next.title || '(none)'}"`);
  }
  if (prev.valid !== next.valid) {
    bullets.push(`Validation: ${fmtBool(prev.valid)} → ${fmtBool(next.valid)}`);
  }
  if (prev.blockingCount !== next.blockingCount) {
    bullets.push(`Blocking issues: ${prev.blockingCount} → ${next.blockingCount}`);
  }
  if (prev.warningCount !== next.warningCount) {
    bullets.push(`Warnings: ${prev.warningCount} → ${next.warningCount}`);
  }
  if (prev.xmlLen !== next.xmlLen) {
    const d = next.xmlLen - prev.xmlLen;
    bullets.push(`XML length: ${prev.xmlLen} → ${next.xmlLen} (${d >= 0 ? '+' : ''}${d})`);
  }
  if (prev.optionPillsKey !== next.optionPillsKey) {
    bullets.push('Generation options changed (see pills above).');
  }
  const headline =
    bullets.length === 0
      ? 'No material changes detected (title, validation counts, XML length, options).'
      : bullets.length <= 4
        ? bullets.join(' · ')
        : `${bullets.length} updates`;

  return { headline, bullets };
}
