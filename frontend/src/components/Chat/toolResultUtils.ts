export const KNOWN_FIRST_PARTY_TOOLS = new Set([
  'generate_dita',
  'create_job',
  'create_job_from_jira',
  'search_jira_issues',
  'lookup_dita_spec',
  'review_dita_xml',
  'find_recipes',
  'get_job_status',
  'lookup_aem_guides',
  'search_tenant_knowledge',
  'lookup_output_preset',
  'list_jobs',
  'fix_dita_xml',
  'lookup_dita_attribute',
  'list_indexed_pdfs',
  'generate_native_pdf_config',
  'browse_dataset',
  'generate_xml_flowchart',
  'generate_image',
  'list_bulk_dataset_presets',
  'save_bulk_dataset_preset',
  'run_bulk_dataset_preset',
]);

export type ToolSource = {
  label?: string;
  title?: string;
  url?: string;
  uri?: string;
  snippet?: string;
};

export type ToolDisplayMeta = {
  title: string;
  kind: string;
  status: string;
  summary: string;
  warnings: string[];
  sources: ToolSource[];
};

function titleFromName(name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function normalizeStatus(result: Record<string, unknown>): string {
  const tone = String(result.status_tone || '').trim().toLowerCase();
  if (tone) return tone;
  const status = String(result.status || '').trim().toLowerCase();
  if (['success', 'warning', 'error'].includes(status)) return status;
  if (['failed', 'cancelled', 'canceled'].includes(status)) return 'warning';
  return result.error ? 'error' : 'success';
}

function normalizeWarnings(result: Record<string, unknown>): string[] {
  const warnings = result.warnings;
  if (Array.isArray(warnings)) {
    return warnings.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof warnings === 'string' && warnings.trim()) {
    return [warnings.trim()];
  }
  return [];
}

function normalizeSources(result: Record<string, unknown>): ToolSource[] {
  const sources = result.sources;
  if (!Array.isArray(sources)) return [];
  return sources
    .map((item) => {
      if (item && typeof item === 'object') {
        return item as ToolSource;
      }
      const text = String(item || '').trim();
      return text ? { label: text } : null;
    })
    .filter((item): item is ToolSource => Boolean(item && (item.label || item.title || item.url || item.uri)));
}

export function extractToolDisplayMeta(name: string, result: unknown): ToolDisplayMeta | null {
  if (!result || typeof result !== 'object') return null;
  const record = result as Record<string, unknown>;
  const summary = String(record.summary || '').trim();
  const warnings = normalizeWarnings(record);
  const sources = normalizeSources(record);
  if (!summary && warnings.length === 0 && sources.length === 0) {
    return null;
  }
  return {
    title: titleFromName(name),
    kind: String(record.kind || 'guidance'),
    status: normalizeStatus(record),
    summary,
    warnings,
    sources,
  };
}
