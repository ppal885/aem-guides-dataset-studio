import { afterEach, describe, expect, it } from 'vitest';
import {
  AUTHORING_GENERATION_DEFAULTS_STORAGE_KEY,
  DEFAULT_CHAT_AUTHORING_GENERATION_OPTIONS,
  mergeAuthoringGenerationOptions,
  readAuthoringGenerationDefaults,
  resolvedAuthoringDefaults,
  writeAuthoringGenerationDefaults,
} from './authoringGenerationDefaults';

describe('authoringGenerationDefaults', () => {
  afterEach(() => {
    localStorage.removeItem(AUTHORING_GENERATION_DEFAULTS_STORAGE_KEY);
  });

  it('mergeAuthoringGenerationOptions applies defined patch keys only', () => {
    const base = { ...DEFAULT_CHAT_AUTHORING_GENERATION_OPTIONS };
    const merged = mergeAuthoringGenerationOptions(base, { dita_type: 'concept', save_path: undefined });
    expect(merged.dita_type).toBe('concept');
    expect(merged.style_strictness).toBe(base.style_strictness);
  });

  it('read/write roundtrip via resolvedAuthoringDefaults', () => {
    writeAuthoringGenerationDefaults(
      mergeAuthoringGenerationOptions(DEFAULT_CHAT_AUTHORING_GENERATION_OPTIONS, {
        style_strictness: 'high',
        preserve_prolog: true,
      })
    );
    const r = readAuthoringGenerationDefaults();
    expect(r.style_strictness).toBe('high');
    expect(r.preserve_prolog).toBe(true);
    const resolved = resolvedAuthoringDefaults();
    expect(resolved.style_strictness).toBe('high');
    expect(resolved.preserve_prolog).toBe(true);
  });

  it('handles corrupt localStorage', () => {
    localStorage.setItem(AUTHORING_GENERATION_DEFAULTS_STORAGE_KEY, 'not-json');
    expect(readAuthoringGenerationDefaults()).toEqual({});
  });
});
