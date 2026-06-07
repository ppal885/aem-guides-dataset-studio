import type { ChatDitaGenerationOptions } from '@/api/chat';

export const AUTHORING_GENERATION_DEFAULTS_STORAGE_KEY = 'chatAuthoringGenerationDefaults';

/** Baseline options before user localStorage overrides (aligned with ChatInput defaults). */
export const DEFAULT_CHAT_AUTHORING_GENERATION_OPTIONS: ChatDitaGenerationOptions = {
  dita_type: 'task',
  save_path: '',
  file_name: '',
  strict_validation: true,
  style_strictness: 'medium',
  preserve_prolog: false,
  xref_placeholders: false,
  auto_ids: true,
  output_mode: 'xml_validation',
  authoring_pattern: 'auto',
  preserve_reference_doctype: false,
  screenshot_deliverable: 'single_topic',
};

export function mergeAuthoringGenerationOptions(
  base: ChatDitaGenerationOptions,
  patch?: Partial<ChatDitaGenerationOptions> | null
): ChatDitaGenerationOptions {
  if (!patch) return { ...base };
  const out: ChatDitaGenerationOptions = { ...base };
  (Object.keys(patch) as (keyof ChatDitaGenerationOptions)[]).forEach((k) => {
    const v = patch[k];
    if (v !== undefined) {
      (out as Record<string, unknown>)[k] = v;
    }
  });
  return out;
}

export function readAuthoringGenerationDefaults(): Partial<ChatDitaGenerationOptions> {
  try {
    const raw = localStorage.getItem(AUTHORING_GENERATION_DEFAULTS_STORAGE_KEY);
    if (!raw?.trim()) return {};
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
    return data as Partial<ChatDitaGenerationOptions>;
  } catch {
    return {};
  }
}

export function writeAuthoringGenerationDefaults(options: ChatDitaGenerationOptions): void {
  try {
    localStorage.setItem(AUTHORING_GENERATION_DEFAULTS_STORAGE_KEY, JSON.stringify(options));
  } catch {
    /* quota / private mode */
  }
}

/** Defaults from storage merged into app defaults — for new turns and regen baseline fill. */
export function resolvedAuthoringDefaults(): ChatDitaGenerationOptions {
  return mergeAuthoringGenerationOptions(DEFAULT_CHAT_AUTHORING_GENERATION_OPTIONS, readAuthoringGenerationDefaults());
}

/** Options used on this turn: persisted turn settings win over saved defaults for missing keys. */
export function effectiveGenerationOptionsForTurn(
  persistedTurnOptions?: ChatDitaGenerationOptions | null
): ChatDitaGenerationOptions {
  return mergeAuthoringGenerationOptions(resolvedAuthoringDefaults(), persistedTurnOptions ?? {});
}
