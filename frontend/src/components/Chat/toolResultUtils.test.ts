import { describe, expect, it } from 'vitest';
import { extractToolDisplayMeta, KNOWN_FIRST_PARTY_TOOLS } from './toolResultUtils';

describe('extractToolDisplayMeta', () => {
  it('returns normalized meta for a guidance tool', () => {
    const meta = extractToolDisplayMeta('lookup_dita_spec', {
      kind: 'guidance',
      status: 'warning',
      summary: 'Retrieved DITA specification guidance for `task`.',
      warnings: ['Only conservative base-grammar evidence was available.'],
      sources: [{ label: 'task', snippet: 'Task topics use taskbody.' }],
    });

    expect(meta).not.toBeNull();
    expect(meta?.title).toBe('Lookup Dita Spec');
    expect(meta?.status).toBe('warning');
    expect(meta?.warnings).toHaveLength(1);
    expect(meta?.sources[0].label).toBe('task');
  });

  it('maps non-normalized job statuses to warning tone when needed', () => {
    const meta = extractToolDisplayMeta('create_job', {
      kind: 'job',
      status: 'failed',
      summary: 'Dataset job `job-1` failed.',
      warnings: [],
      sources: [],
    });

    expect(meta?.status).toBe('warning');
  });

  it('returns null for objects without normalized display fields', () => {
    expect(extractToolDisplayMeta('lookup_dita_spec', { count: 1 })).toBeNull();
  });
});

describe('KNOWN_FIRST_PARTY_TOOLS', () => {
  it('includes all tool names that can appear from chat agent or grounding (beyond LLM tool_use list)', () => {
    expect(KNOWN_FIRST_PARTY_TOOLS.has('generate_dita')).toBe(true);
    expect(KNOWN_FIRST_PARTY_TOOLS.has('generate_xml_flowchart')).toBe(true);
    expect(KNOWN_FIRST_PARTY_TOOLS.has('create_job')).toBe(true);
    expect(KNOWN_FIRST_PARTY_TOOLS.has('lookup_dita_spec')).toBe(true);
  });
});
