import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PanelResizeHandle } from '@/components/Chat/PanelResizeHandle';
import { useHorizontalPanelResize } from '@/components/Chat/usePanelResize';

const MIN_WIDTH = 200;
const MAX_WIDTH = 480;
const DEFAULT_WIDTH = 260;
const STORAGE_KEY = 'builderRecipePanelWidth';

const searchInputClass =
  'w-full rounded-lg border border-border/70 bg-background/80 py-1.5 pl-8 pr-2 text-[12px] text-foreground placeholder:text-muted-foreground focus:border-ring/50 focus:outline-none focus:ring-1 focus:ring-ring/20';

export interface BuilderRecipeListEntry {
  id: string;
  title: string;
}

export interface BuilderQuickWorkflow {
  id: string;
  title: string;
}

interface BuilderRecipePanelProps {
  recipes: BuilderRecipeListEntry[];
  selectedRecipeId: string;
  onSelect: (recipeId: string) => void;
  search: string;
  onSearchChange: (value: string) => void;
  quickWorkflows?: BuilderQuickWorkflow[];
  activeWorkflowId?: string;
  onQuickPreset?: (workflowId: string) => void;
}

export function BuilderRecipePanel({
  recipes,
  selectedRecipeId,
  onSelect,
  search,
  onSearchChange,
  quickWorkflows = [],
  activeWorkflowId = '',
  onQuickPreset,
}: BuilderRecipePanelProps) {
  const { width, dragging, onMouseDown, resetWidth } = useHorizontalPanelResize({
    storageKey: STORAGE_KEY,
    defaultWidth: DEFAULT_WIDTH,
    minWidth: MIN_WIDTH,
    maxWidth: MAX_WIDTH,
  });

  return (
    <aside className="cursor-sidebar relative flex shrink-0 flex-col" style={{ width }} aria-label="Recipe library">
      <div className="flex items-center justify-between border-b border-border/60 px-3 py-2.5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Recipes</p>
      </div>

      <div className="flex flex-col gap-2 p-2.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={event => onSearchChange(event.target.value)}
            placeholder="Search recipes"
            className={searchInputClass}
            aria-label="Search recipes"
          />
        </div>

        {quickWorkflows.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {quickWorkflows.map(workflow => {
              const active = activeWorkflowId === workflow.id;
              return (
                <button
                  key={workflow.id}
                  type="button"
                  onClick={() => onQuickPreset?.(workflow.id)}
                  className={cn(
                    'cursor-list-item rounded-lg border px-2 py-1 text-[11px] font-medium',
                    active
                      ? 'border-border bg-muted text-foreground'
                      : 'border-border/70 bg-background/60 text-muted-foreground'
                  )}
                  data-selected={active ? '' : undefined}
                >
                  {workflow.title}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {recipes.length === 0 ? (
          <p className="px-2 py-6 text-center text-[11px] leading-relaxed text-muted-foreground">
            {search.trim() ? 'No matching recipes.' : 'No recipes available.'}
          </p>
        ) : (
          recipes.map(entry => {
            const selected = selectedRecipeId === entry.id;
            return (
              <button
                key={entry.id}
                type="button"
                onClick={() => onSelect(entry.id)}
                title={entry.title}
                aria-current={selected ? 'true' : undefined}
                data-selected={selected ? '' : undefined}
                className={cn(
                  'cursor-list-item mb-0.5 flex w-full flex-col rounded-lg px-2.5 py-2 text-left',
                  selected ? 'text-foreground' : 'text-muted-foreground'
                )}
              >
                <span className="truncate text-[12px] font-medium leading-5">{entry.title}</span>
                <span className="truncate font-mono text-[10px] text-muted-foreground">{entry.id}</span>
              </button>
            );
          })
        )}
      </div>

      <PanelResizeHandle
        side="right"
        dragging={dragging}
        onMouseDown={onMouseDown}
        onDoubleClick={resetWidth}
        className="right-edge"
        title="Resize recipe panel"
      />
    </aside>
  );
}
