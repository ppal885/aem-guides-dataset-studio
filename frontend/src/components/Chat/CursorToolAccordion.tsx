import { useState } from 'react';
import { ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { extractToolDisplayMeta } from './toolResultUtils';

const META_TOOLS = new Set([
  '_agent_plan',
  '_approval_state',
  '_agent_execution',
  '_grounding',
  '_attachments',
  '_generation_options',
]);

const TOOL_VERBS: Record<string, string> = {
  lookup_dita_spec: 'Searched DITA spec',
  lookup_aem_guides: 'Searched AEM Guides docs',
  lookup_dita_attribute: 'Looked up attribute',
  search_jira_issues: 'Searched Jira',
  find_recipes: 'Found recipes',
  generate_dita: 'Generated DITA',
  create_job: 'Created dataset job',
  get_job_status: 'Checked job status',
  list_jobs: 'Listed jobs',
  review_dita_xml: 'Reviewed DITA XML',
  fix_dita_xml: 'Fixed DITA XML',
  browse_dataset: 'Browsed dataset',
  lookup_output_preset: 'Looked up output preset',
  generate_native_pdf_config: 'Generated PDF config',
};

function friendlyToolLabel(name: string): string {
  if (TOOL_VERBS[name]) return TOOL_VERBS[name];
  return name
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

interface CursorToolAccordionProps {
  name: string;
  result: unknown;
  children: React.ReactNode;
  defaultOpen?: boolean;
  loading?: boolean;
}

export function CursorToolAccordion({
  name,
  result,
  children,
  defaultOpen,
  loading,
}: CursorToolAccordionProps) {
  const isMeta = META_TOOLS.has(name);
  const meta = extractToolDisplayMeta(name, result);
  const label = meta?.title || friendlyToolLabel(name);
  const statusBadge = meta?.status && meta.status !== 'success' ? meta.status : null;
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div className="my-0.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="cursor-tool-row"
      >
        <ChevronRight
          className={cn('h-3 w-3 shrink-0 transition-transform opacity-60', open && 'rotate-90')}
          aria-hidden
        />
        {loading ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin opacity-70" aria-hidden />
        ) : null}
        <span className="min-w-0 flex-1 truncate">
          {loading ? `Running ${label}…` : label}
        </span>
        {statusBadge && (
          <span className="shrink-0 text-[10px] capitalize opacity-70">{statusBadge}</span>
        )}
      </button>
      {open && (
        <div className="cursor-tool-content mb-2 ml-5 border-l border-border/50 pl-3">
          {children}
        </div>
      )}
    </div>
  );
}
