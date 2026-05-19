import { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { ChatDitaGenerationOptions } from '@/api/chat';
import {
  effectiveGenerationOptionsForTurn,
  mergeAuthoringGenerationOptions,
} from '@/lib/authoringGenerationDefaults';

export interface AuthoringRegenerateOptionsProps {
  /** Persisted options from the authoring user message (may be partial). */
  baselineFromTurn?: ChatDitaGenerationOptions | null;
  hasReferenceDita: boolean;
  semanticSectionNames: string[];
  onRegenerate: (options: ChatDitaGenerationOptions) => void;
  disabled?: boolean;
}

/**
 * Collapsible controls for screenshot DITA regeneration; emits full merged ChatDitaGenerationOptions.
 */
export function AuthoringRegenerateOptions({
  baselineFromTurn,
  hasReferenceDita,
  semanticSectionNames,
  onRegenerate,
  disabled = false,
}: AuthoringRegenerateOptionsProps) {
  const baseline = useMemo(
    () => effectiveGenerationOptionsForTurn(baselineFromTurn ?? null),
    [baselineFromTurn]
  );

  const [draft, setDraft] = useState<ChatDitaGenerationOptions>(baseline);
  const [closerToReference, setCloserToReference] = useState(false);

  useEffect(() => {
    setDraft(baseline);
    setCloserToReference(false);
  }, [baseline]);

  const effectiveForSubmit = useMemo(() => {
    if (closerToReference && hasReferenceDita) {
      return mergeAuthoringGenerationOptions(draft, {
        style_strictness: 'high',
        authoring_pattern: 'auto',
        preserve_reference_doctype: true,
      });
    }
    return { ...draft };
  }, [closerToReference, draft, hasReferenceDita]);

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
      <details className="min-w-[12rem] flex-1 rounded-lg border border-slate-200 bg-white/90 px-2 py-1.5 shadow-sm open:pb-2">
        <summary className="cursor-pointer select-none text-[11px] font-semibold uppercase tracking-wide text-slate-600">
          Regenerate options
        </summary>
        <div className="mt-2 grid max-w-md gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-[11px] text-slate-700">
            <span className="font-medium">Topic type</span>
            <select
              value={draft.dita_type || 'task'}
              disabled={disabled}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  dita_type: e.target.value as ChatDitaGenerationOptions['dita_type'],
                }))
              }
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900"
            >
              <option value="task">task</option>
              <option value="concept">concept</option>
              <option value="reference">reference</option>
              <option value="topic">topic</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-slate-700">
            <span className="font-medium">Style strictness</span>
            <select
              value={draft.style_strictness || 'medium'}
              disabled={disabled || (closerToReference && hasReferenceDita)}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  style_strictness: e.target.value as ChatDitaGenerationOptions['style_strictness'],
                }))
              }
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <div className="flex items-center justify-between gap-2 sm:col-span-2">
            <Label htmlFor="regen-prolog" className="text-[11px] font-normal text-slate-700">
              Preserve prolog
            </Label>
            <Switch
              id="regen-prolog"
              checked={Boolean(draft.preserve_prolog)}
              disabled={disabled}
              onCheckedChange={(v) => setDraft((d) => ({ ...d, preserve_prolog: v }))}
            />
          </div>
          <div className="flex items-center justify-between gap-2 sm:col-span-2">
            <Label htmlFor="regen-placeholders" className="text-[11px] font-normal text-slate-700">
              Allow xref placeholders
            </Label>
            <Switch
              id="regen-placeholders"
              checked={Boolean(draft.xref_placeholders)}
              disabled={disabled}
              onCheckedChange={(v) => setDraft((d) => ({ ...d, xref_placeholders: v }))}
            />
          </div>
          <div className="flex items-center justify-between gap-2 sm:col-span-2">
            <div className="min-w-0">
              <Label htmlFor="regen-refstyle" className="text-[11px] font-normal text-slate-700">
                Closer to reference style
              </Label>
              <p className="text-[10px] text-slate-500">
                Sets strictness high, pattern auto, preserve reference DOCTYPE when a reference file was used.
              </p>
            </div>
            <Switch
              id="regen-refstyle"
              checked={closerToReference}
              disabled={disabled || !hasReferenceDita}
              onCheckedChange={setCloserToReference}
            />
          </div>
          {!hasReferenceDita && (
            <p className="text-[10px] text-slate-500 sm:col-span-2">Reference style boost requires a reference DITA attachment on the original turn.</p>
          )}
          <label className="flex flex-col gap-1 text-[11px] text-slate-700 sm:col-span-2">
            <span className="font-medium">Regenerate section (future)</span>
            <select
              disabled
              className="cursor-not-allowed rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-500"
              value=""
              aria-disabled="true"
            >
              <option value="">Full topic only (section-scoped API not available)</option>
              {semanticSectionNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 shrink-0"
        disabled={disabled}
        onClick={() => onRegenerate(effectiveForSubmit)}
      >
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Regenerate
      </Button>
    </div>
  );
}
