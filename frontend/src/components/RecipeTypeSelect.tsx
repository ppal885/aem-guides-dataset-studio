import { useState, useRef, useEffect, type ReactNode } from 'react';
import { ChevronDown, Check, Sparkles, Zap, BarChart3, FileText, Link2, Workflow, Code, Database, Search, Map } from 'lucide-react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

interface RecipeOption {
  value: string;
  label: string;
  group: string;
  icon?: ReactNode;
  description?: string;
}

const RECIPE_GROUPS: Record<string, { label: string; icon: ReactNode }> = {
  specialized: { label: 'Specialized Content', icon: <FileText className="w-4 h-4" /> },
  reuse: { label: 'Content Reuse', icon: <Link2 className="w-4 h-4" /> },
  advanced: { label: 'Advanced Features', icon: <Sparkles className="w-4 h-4" /> },
  performance: { label: 'Performance & Scale', icon: <BarChart3 className="w-4 h-4" /> },
  metadata: { label: 'Metadata & Keys', icon: <Database className="w-4 h-4" /> },
  workflow: { label: 'Workflow & Localization', icon: <Workflow className="w-4 h-4" /> },
  output: { label: 'Output Optimization', icon: <Zap className="w-4 h-4" /> },
  legacy: { label: 'Legacy Patterns', icon: <Code className="w-4 h-4" /> },
  maps: { label: 'Map Structure', icon: <Map className="w-4 h-4" /> },
};

const RECIPE_OPTIONS: RecipeOption[] = [
  { value: 'task_topics', label: 'Task Topics', group: 'specialized', description: 'Procedural steps and instructions' },
  { value: 'concept_topics', label: 'Concept Topics', group: 'specialized', description: 'Explanatory content' },
  { value: 'reference_topics', label: 'Reference Topics', group: 'specialized', description: 'Structured reference data' },
  { value: 'glossary_pack', label: 'Glossary Pack', group: 'specialized', description: 'Term definitions and acronyms' },
  { value: 'bookmap_structure', label: 'Bookmap Structure', group: 'specialized', description: 'Book with chapters and frontmatter' },
  { value: 'maps_topicgroup_basic', label: 'Topicgroup Basic', group: 'maps', description: 'Map with topicgroup for grouping topicrefs' },
  { value: 'maps_topicgroup_nested', label: 'Topicgroup Nested', group: 'maps', description: 'Nested topicgroup elements for hierarchical grouping' },
  { value: 'maps_topicref_basic', label: 'Topicref Basic', group: 'maps', description: 'Map with basic topicrefs' },
  { value: 'maps_nested_topicrefs', label: 'Nested Topicrefs (Map Hierarchy)', group: 'maps', description: 'Map with nested topicref hierarchy' },
  { value: 'maps_mapref_basic', label: 'Mapref (Submap Hierarchy)', group: 'maps', description: 'Map with mapref to submap' },
  { value: 'maps_topichead_basic', label: 'Topichead Basic', group: 'maps', description: 'Map with topichead section headings without href' },
  { value: 'maps_reltable_basic', label: 'Reltable Basic', group: 'maps', description: 'Map with reltable for next/prev/related relationships' },
  { value: 'maps_topicset_basic', label: 'Topicset Basic', group: 'maps', description: 'Map with topicset for navigation grouping (DITA 1.3)' },
  { value: 'maps_navref_basic', label: 'Navref Basic', group: 'maps', description: 'Map with navref referencing another map for navigation' },
  { value: 'conref_pack', label: 'Conref Pack', group: 'reuse', description: 'Content references for reuse' },
  { value: 'dita_conref_title_dataset_recipe', label: 'Conref in Title Dataset', group: 'reuse', description: 'Topics with conref in title referencing variable ph elements' },
  { value: 'dita_conref_keyref_dataset_recipe', label: 'Conref + Keyref Dataset', group: 'reuse', description: 'Topics with conref and keyref combinations (15 topics)' },
  { value: 'dita_subject_scheme_dataset_recipe', label: 'Subject Scheme Dataset', group: 'reuse', description: 'Subject scheme validation (10 valid + 10 invalid topics)' },
  { value: 'dita_glossary_abbrev_dataset_recipe', label: 'Glossary Abbrev Dataset', group: 'reuse', description: 'Glossary with term and abbreviated-form (15 entries, 10 usage topics)' },
  { value: 'customer_reuse_pack', label: 'Customer Reuse Pack', group: 'reuse', description: 'Shared topics with key definitions' },
  { value: 'relationship_table', label: 'Relationship Table', group: 'advanced', description: 'Topic relationship tables' },
  { value: 'advanced_relationships', label: 'Advanced Relationships', group: 'advanced', description: 'Complex relationship patterns' },
  { value: 'conditional_content', label: 'Conditional Content', group: 'advanced', description: 'Conditional processing attributes' },
  { value: 'media_rich_content', label: 'Media Rich Content', group: 'advanced', description: 'Topics with images and media' },
  { value: 'incremental_topicref_maps', label: 'Incremental Topicref Maps', group: 'performance', description: 'Maps with varying topicref counts' },
  { value: 'insurance_incremental', label: 'Insurance Incremental (10/100/1k/5k/10k topicrefs)', group: 'performance', description: 'Insurance domain with incremental maps' },
  { value: 'large_scale', label: 'Large Scale', group: 'performance', description: '100k+ topics for performance testing' },
  { value: 'deep_hierarchy', label: 'Deep Hierarchy', group: 'performance', description: 'Deeply nested topic structures' },
  { value: 'wide_branching', label: 'Wide Branching', group: 'performance', description: 'Many children per parent' },
  { value: 'map_parse_stress', label: 'Map Parse Stress', group: 'performance', description: 'Stress test map parsing' },
  { value: 'heavy_topics_tables_codeblocks', label: 'Heavy Topics Tables & Codeblocks', group: 'performance', description: 'Topics with heavy content' },
  { value: 'heavy_conditional_topic_6000_lines', label: 'Heavy Conditional Topic (6000+ lines)', group: 'performance', description: 'Single extremely large topic with audience/platform/otherprops profiling' },
  { value: 'keyscope_demo', label: 'Keyscope Demo', group: 'metadata', description: 'Scoped key resolution demo' },
  { value: 'keyword_metadata', label: 'Keyword Metadata', group: 'metadata', description: 'Topics with keyword metadata' },
  { value: 'keyref_nested_keydef_chain_map_to_map_to_topic', label: 'Nested Keydef Chain (Map A→B→Topic C)', group: 'metadata', description: 'Recursive key resolution: Map A keydef→Map B keydef→Topic C' },
  { value: 'workflow_enabled_content', label: 'Workflow Enabled', group: 'workflow', description: 'Review and translation workflows' },
  { value: 'localized_content', label: 'Localized Content', group: 'workflow', description: 'Multi-language content variants' },
  { value: 'output_optimized', label: 'Output Optimized', group: 'output', description: 'Format-optimized content (AEM Site, PDF, HTML5)' },
  { value: 'hub_spoke_inbound', label: 'Hub-Spoke Inbound', group: 'legacy', description: 'Hub-spoke reference pattern' },
  { value: 'keydef_heavy', label: 'Keydef Heavy', group: 'legacy', description: 'Maps with many key definitions' },
  { value: 'map_cyclic', label: 'Map Cyclic References', group: 'legacy', description: 'Mapref cycle: map_a -> map_b -> map_a' },
];

function filterOptions(options: RecipeOption[], query: string): RecipeOption[] {
  if (!query.trim()) return options;
  const q = query.toLowerCase().trim();
  return options.filter(
    (opt) =>
      opt.label.toLowerCase().includes(q) ||
      (opt.description?.toLowerCase().includes(q)) ||
      opt.value.toLowerCase().includes(q) ||
      RECIPE_GROUPS[opt.group]?.label.toLowerCase().includes(q)
  );
}

interface RecipeTypeSelectProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export function RecipeTypeSelect({ value, onChange, className }: RecipeTypeSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [dropdownPlacement, setDropdownPlacement] = useState<'below' | 'above'>('below');
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selectedOption = RECIPE_OPTIONS.find((opt) => opt.value === value);
  const filteredOptions = filterOptions(RECIPE_OPTIONS, searchQuery);

  const groupedOptions = filteredOptions.reduce((acc, opt) => {
    if (!acc[opt.group]) acc[opt.group] = [];
    acc[opt.group].push(opt);
    return acc;
  }, {} as Record<string, RecipeOption[]>);

  const flatFilteredOptions = filteredOptions.map((opt, idx) => ({ ...opt, flatIndex: idx }));

  // Position dropdown viewport-aware
  useEffect(() => {
    if (!isOpen || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    setDropdownPlacement(spaceBelow < 320 && spaceAbove > spaceBelow ? 'above' : 'below');
  }, [isOpen]);

  // Focus search when opening
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setFocusedIndex(-1);
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    const handleScroll = (e: Event) => {
      if (dropdownRef.current?.contains(e.target as Node)) return;
      setIsOpen(false);
    };
    const handleResize = () => setIsOpen(false);
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      window.addEventListener('scroll', handleScroll, true);
      window.addEventListener('resize', handleResize);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', handleScroll, true);
      window.removeEventListener('resize', handleResize);
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && focusedIndex >= 0 && listRef.current) {
      const el = listRef.current.querySelector(`[data-index="${focusedIndex}"]`) as HTMLElement;
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [focusedIndex, isOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
      setFocusedIndex(-1);
      setSearchQuery('');
      return;
    }

    if (!isOpen && (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown')) {
      e.preventDefault();
      setIsOpen(true);
      return;
    }

    if (!isOpen) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIndex((prev) => (prev < flatFilteredOptions.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIndex((prev) => (prev > 0 ? prev - 1 : -1));
    } else if (e.key === 'Enter' && focusedIndex >= 0) {
      e.preventDefault();
      const option = flatFilteredOptions[focusedIndex];
      if (option) handleSelect(option.value);
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const char = e.key.toLowerCase();
      const idx = flatFilteredOptions.findIndex((opt) => opt.label.toLowerCase().startsWith(char));
      if (idx >= 0) {
        e.preventDefault();
        setFocusedIndex(idx);
      }
    }
  };

  const handleSelect = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
    setFocusedIndex(-1);
    setSearchQuery('');
  };

  const dropdownContent =
    isOpen &&
    triggerRef.current && (
      <div
        ref={dropdownRef}
        className="fixed z-[100] rounded-xl border border-slate-200/80 bg-white/95 shadow-xl backdrop-blur-sm animate-fadeIn"
        style={{
          left: triggerRef.current.getBoundingClientRect().left,
          width: triggerRef.current.getBoundingClientRect().width,
          ...(dropdownPlacement === 'below'
            ? { top: triggerRef.current.getBoundingClientRect().bottom + 6 }
            : { bottom: window.innerHeight - triggerRef.current.getBoundingClientRect().top + 6 }),
          maxHeight: 'min(420px, 70vh)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
      <div className="flex flex-col max-h-[min(420px,70vh)]">
        <div className="shrink-0 border-b border-slate-100 p-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setFocusedIndex(-1);
              }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setFocusedIndex((prev) => (prev < flatFilteredOptions.length - 1 ? prev + 1 : 0));
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setFocusedIndex((prev) => (prev > 0 ? prev - 1 : flatFilteredOptions.length - 1));
                } else if (e.key === 'Enter' && focusedIndex >= 0) {
                  e.preventDefault();
                  const opt = flatFilteredOptions[focusedIndex];
                  if (opt) handleSelect(opt.value);
                }
              }}
              placeholder="Search recipes..."
              className="w-full rounded-lg border-0 bg-slate-50 py-2.5 pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500/30 focus:bg-white transition-colors"
            />
          </div>
        </div>
        <div
          ref={listRef}
          className="overflow-y-auto overscroll-contain py-2"
          style={{ maxHeight: '360px', scrollbarWidth: 'thin' }}
        >
          {Object.keys(groupedOptions).length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-slate-500">
              No recipes match &quot;{searchQuery}&quot;
            </div>
          ) : (
            Object.entries(groupedOptions).map(([groupKey, options]) => (
              <div key={groupKey} className="py-1">
                <div className="px-3 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2 sticky top-0 bg-white/95 backdrop-blur-sm z-10">
                  {RECIPE_GROUPS[groupKey]?.icon}
                  {RECIPE_GROUPS[groupKey]?.label}
                </div>
                {options.map((option) => {
                  const flatIndex = flatFilteredOptions.findIndex((o) => o.value === option.value);
                  const isSelected = option.value === value;
                  const isFocused = flatIndex === focusedIndex;

                  return (
                    <button
                      key={option.value}
                      type="button"
                      data-index={flatIndex}
                      onClick={() => handleSelect(option.value)}
                      onMouseEnter={() => setFocusedIndex(flatIndex)}
                      className={cn(
                        'w-full px-3 py-2.5 text-left transition-colors duration-100 flex items-start gap-3 group rounded-lg mx-1',
                        isSelected && 'bg-blue-50 text-blue-800',
                        isFocused && !isSelected && 'bg-slate-50',
                        !isSelected && !isFocused && 'hover:bg-slate-50/80'
                      )}
                    >
                      <div className={cn('flex-shrink-0 mt-0.5', isSelected ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600')}>
                        {RECIPE_GROUPS[option.group]?.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">{option.label}</span>
                          {isSelected && <Check className="w-4 h-4 text-blue-600 flex-shrink-0" />}
                        </div>
                        {option.description && (
                          <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{option.description}</div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className={cn('relative w-full', className)}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label="Select recipe type"
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        className={cn(
          'w-full flex items-center justify-between rounded-xl border bg-white px-4 py-3 text-left transition-all duration-200',
          'hover:border-slate-300 hover:shadow-sm',
          'focus:outline-none focus:ring-2 focus:ring-blue-500/25 focus:border-blue-400',
          isOpen && 'border-blue-400 ring-2 ring-blue-500/20 shadow-md'
        )}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {selectedOption ? (
            <>
              <div className="flex-shrink-0 text-slate-500">{RECIPE_GROUPS[selectedOption.group]?.icon}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-900 truncate">{selectedOption.label}</div>
                {selectedOption.description && (
                  <div className="text-xs text-slate-500 truncate">{selectedOption.description}</div>
                )}
              </div>
            </>
          ) : (
            <span className="text-slate-400 text-sm">Select a recipe type...</span>
          )}
        </div>
        <ChevronDown
          className={cn(
            'w-5 h-5 text-slate-400 flex-shrink-0 transition-transform duration-200',
            isOpen && 'transform rotate-180'
          )}
        />
      </button>

      {dropdownContent && createPortal(dropdownContent, document.body)}
    </div>
  );
}
