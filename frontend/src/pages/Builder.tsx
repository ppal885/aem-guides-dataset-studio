import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';

import { BuilderRecipePanel } from '@/components/Builder/BuilderRecipePanel';
import { SchedulePicker } from '@/components/SchedulePicker';
import { ValidationDisplay } from '@/components/ValidationDisplay';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useRecipeValidation } from '@/hooks/useRecipeValidation';
import {
  normalizeRecipeLimits,
  topicCountCapForRecipe,
  type RecipeLimits,
} from '@/lib/recipeLimits';
import { apiUrl, fetchJson } from '@/utils/api';

type PrimitiveSchemaType = 'int' | 'float' | 'bool' | 'str' | 'list' | 'dict';

interface RecipeCatalogEntry {
  id: string;
  title: string;
  description: string;
  category: string;
  category_label: string;
  tags: string[];
  featured_tracks: string[];
  featured_track_labels: string[];
  params_schema: Record<string, PrimitiveSchemaType>;
  default_params: Record<string, unknown>;
  editor_type: string;
  full_example_xml: string;
  expected_result: string;
}

interface RecipeCatalogFilter {
  id: string;
  label: string;
}

interface QuickWorkflow {
  id: string;
  title: string;
  description: string;
  category?: string;
  featured_track?: string;
  search_terms?: string[];
  recipe_id?: string;
  preset_params?: Record<string, unknown>;
}

interface RecipeCatalogResponse {
  entries: RecipeCatalogEntry[];
  categories: RecipeCatalogFilter[];
  featured_tracks: RecipeCatalogFilter[];
  quick_workflows: QuickWorkflow[];
}

interface Limits extends RecipeLimits {}

function prettifyRecipeName(title: string, createdAt: string): string {
  const timestamp = new Date(createdAt);
  const timeStr = Number.isNaN(timestamp.getTime())
    ? createdAt
    : timestamp.toLocaleString('en-US', {
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      });
  return `${title} - ${timeStr}`;
}

function schemaFieldType(value: unknown): PrimitiveSchemaType {
  const text = String(value || '').trim().toLowerCase();
  if (text === 'int' || text === 'float' || text === 'bool' || text === 'str' || text === 'list' || text === 'dict') {
    return text;
  }
  if (text.includes('dict') || text.includes('mapping') || text.includes('object') || text.includes('json')) return 'dict';
  if (text.includes('list') || text.includes('tuple') || text.includes('sequence')) return 'list';
  if (text.includes('bool')) return 'bool';
  if (text.includes('float') || text.includes('number') || text.includes('decimal')) return 'float';
  if (text.includes('int') || text.includes('integer')) return 'int';
  return 'str';
}

function schemaFieldTypeFromSchemaOrValue(schemaValue: unknown, currentValue: unknown): PrimitiveSchemaType {
  const schemaType = schemaFieldType(schemaValue);
  if (schemaType !== 'str' || String(schemaValue || '').trim()) return schemaType;
  if (Array.isArray(currentValue)) return 'list';
  if (currentValue && typeof currentValue === 'object') return 'dict';
  if (typeof currentValue === 'boolean') return 'bool';
  if (typeof currentValue === 'number') return Number.isInteger(currentValue) ? 'int' : 'float';
  return 'str';
}

function fieldLabel(key: string): string {
  return key
    .split(/[_\-.]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function fieldHelpText(type: PrimitiveSchemaType): string {
  if (type === 'list') return 'JSON array';
  if (type === 'dict') return 'JSON object';
  if (type === 'bool') return 'On or off';
  if (type === 'int' || type === 'float') return 'Numeric value';
  return 'Text value';
}

function normalizeSearchText(entry: RecipeCatalogEntry): string {
  return [
    entry.id,
    entry.title,
    entry.description,
    ...entry.tags,
    ...entry.featured_track_labels,
  ]
    .join(' ')
    .toLowerCase();
}

function coercePrimitiveValue(type: PrimitiveSchemaType, raw: string): unknown {
  if (type === 'int') {
    const parsed = Number.parseInt(raw, 10);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  if (type === 'float') {
    const parsed = Number.parseFloat(raw);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return raw;
}

function JsonEditorField({
  label,
  value,
  emptyValue,
  onCommit,
}: {
  label: string;
  value: unknown;
  emptyValue: unknown;
  onCommit: (nextValue: unknown) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value ?? emptyValue, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(JSON.stringify(value ?? emptyValue, null, 2));
    setError(null);
  }, [emptyValue, value]);

  return (
    <div className="space-y-2">
      <Label className="text-sm font-semibold text-slate-900">{label}</Label>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => {
          try {
            const parsed = JSON.parse(text);
            setError(null);
            onCommit(parsed);
          } catch {
            setError('Enter valid JSON before leaving this field.');
          }
        }}
        rows={6}
        className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-sm text-foreground shadow-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
      />
      {error ? <p className="text-xs text-red-600">{error}</p> : <p className="text-xs text-slate-500">Valid JSON is applied when the field loses focus.</p>}
    </div>
  );
}

export function Builder() {
  const [catalog, setCatalog] = useState<RecipeCatalogResponse | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [selectedRecipeId, setSelectedRecipeId] = useState('');
  const [recipeParams, setRecipeParams] = useState<Record<string, unknown>>({});
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [featuredTrack, setFeaturedTrack] = useState('all');
  const [activeWorkflowId, setActiveWorkflowId] = useState('');
  const [scheduledAt, setScheduledAt] = useState<Date | null>(null);
  const [timezone, setTimezone] = useState('UTC');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [downloadingJobId, setDownloadingJobId] = useState<string | null>(null);
  const [createdJobs, setCreatedJobs] = useState<Array<{ id: string; name: string; createdAt?: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [recipeSample, setRecipeSample] = useState<{ full_example_xml: string; expected_result: string } | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadBuilderData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalogData, limitsData] = await Promise.all([
        fetchJson<RecipeCatalogResponse>(apiUrl('/api/v1/recipes/catalog')),
        fetchJson<Limits>(apiUrl('/api/v1/limits')),
      ]);
      if (!isMountedRef.current) return;
      setCatalog(catalogData);
      setLimits(normalizeRecipeLimits(limitsData));
      if (!selectedRecipeId && catalogData.entries.length > 0) {
        const preferred =
          catalogData.entries.find(entry => entry.id === 'curated_realtime_corpus') || catalogData.entries[0];
        setSelectedRecipeId(preferred.id);
        setRecipeParams({ ...preferred.default_params });
      }
    } catch (loadError) {
      if (!isMountedRef.current) return;
      setError(loadError instanceof Error ? loadError.message : 'Failed to load Builder catalog');
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [selectedRecipeId]);

  useEffect(() => {
    loadBuilderData();
  }, [loadBuilderData]);

  const selectedRecipe = useMemo(
    () => catalog?.entries.find(entry => entry.id === selectedRecipeId) || null,
    [catalog, selectedRecipeId]
  );

  useEffect(() => {
    if (selectedRecipe) {
      setRecipeParams({ ...selectedRecipe.default_params });
    }
  }, [selectedRecipe?.id]);

  useEffect(() => {
    if (!selectedRecipeId) {
      setRecipeSample(null);
      return;
    }

    let cancelled = false;
    setSampleLoading(true);

    fetchJson<{ full_example_xml: string; expected_result: string }>(
      apiUrl(`/api/v1/recipes/catalog/samples/${encodeURIComponent(selectedRecipeId)}`)
    )
      .then(sample => {
        if (!cancelled && isMountedRef.current) {
          setRecipeSample(sample);
        }
      })
      .catch(() => {
        if (!cancelled && isMountedRef.current) {
          setRecipeSample(null);
        }
      })
      .finally(() => {
        if (!cancelled && isMountedRef.current) {
          setSampleLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRecipeId]);

  const activeWorkflow = useMemo(
    () => catalog?.quick_workflows.find(item => item.id === activeWorkflowId) || null,
    [catalog?.quick_workflows, activeWorkflowId]
  );

  const filteredRecipes = useMemo(() => {
    const entries = catalog?.entries || [];
    const searchText = search.trim().toLowerCase();
    return entries.filter(entry => {
      if (category !== 'all' && entry.category !== category) return false;
      if (featuredTrack !== 'all' && !entry.featured_tracks.includes(featuredTrack)) return false;
      if (searchText && !normalizeSearchText(entry).includes(searchText)) return false;
      if (activeWorkflow?.search_terms?.length) {
        const haystack = normalizeSearchText(entry);
        const hasWorkflowMatch = activeWorkflow.search_terms.some(term => haystack.includes(term.toLowerCase()));
        if (!hasWorkflowMatch) return false;
      }
      return true;
    });
  }, [activeWorkflow?.search_terms, catalog?.entries, category, featuredTrack, search]);

  useEffect(() => {
    if (!catalog) return;
    if (filteredRecipes.length === 0) {
      setSelectedRecipeId('');
      return;
    }
    if (!filteredRecipes.some(entry => entry.id === selectedRecipeId)) {
      setSelectedRecipeId(filteredRecipes[0].id);
    }
  }, [catalog, filteredRecipes, selectedRecipeId]);

  const currentRecipe = useMemo(
    () => (selectedRecipe ? { type: selectedRecipe.id, ...recipeParams } : null),
    [recipeParams, selectedRecipe]
  );

  const validation = useRecipeValidation(currentRecipe, limits || undefined);

  const sampleExpectedResult = recipeSample?.expected_result ?? selectedRecipe?.expected_result ?? '';
  const sampleXml = recipeSample?.full_example_xml ?? selectedRecipe?.full_example_xml ?? '';

  const handleScheduleChange = useCallback((nextScheduledAt: Date | null, nextTimezone: string) => {
    setScheduledAt(nextScheduledAt);
    setTimezone(nextTimezone);
  }, []);

  const handleRecipeSelect = useCallback((recipeId: string) => {
    setSelectedRecipeId(recipeId);
    setActiveWorkflowId('');
  }, []);

  const updateRecipeParam = useCallback((key: string, value: unknown) => {
    setRecipeParams(previous => ({ ...previous, [key]: value }));
  }, []);

  const handleCreateJob = useCallback(async () => {
    if (!selectedRecipe) {
      setError('Select a recipe before creating a job.');
      return;
    }
    if (!validation.isValid) {
      setError('Fix validation errors before creating the dataset job.');
      return;
    }

    setCreating(true);
    setError(null);

    const recipePayload = { type: selectedRecipe.id, ...recipeParams };
    const jobData = {
      config: {
        name: selectedRecipe.title,
        seed: 'catalog-driven',
        root_folder: '/content/dam/dataset-studio',
        windows_safe_filenames: true,
        doctype_topic: '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        doctype_map: '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
        recipes: [recipePayload],
      },
    };

    try {
      const response = await fetchJson<{ id: string; created_at?: string }>(
        apiUrl(scheduledAt ? '/api/v1/jobs/schedule' : '/api/v1/jobs'),
        {
          method: 'POST',
          body: JSON.stringify(
            scheduledAt
              ? {
                  ...jobData,
                  scheduled_at: scheduledAt.toISOString(),
                  timezone,
                }
              : jobData
          ),
        }
      );
      const createdAt = response.created_at || new Date().toISOString();
      setCreatedJobs(previous => [
        ...previous,
        { id: response.id, name: prettifyRecipeName(selectedRecipe.title, createdAt), createdAt },
      ]);
      setScheduledAt(null);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Failed to create the dataset job');
    } finally {
      setCreating(false);
    }
  }, [recipeParams, scheduledAt, selectedRecipe, timezone, validation.isValid]);

  const handleDownload = useCallback(
    async (jobId: string, jobName: string) => {
      if (downloadingJobId === jobId) return;
      setDownloadingJobId(jobId);
      try {
        const response = await fetch(apiUrl(`/api/v1/datasets/${jobId}/download`));
        if (!response.ok) {
          throw new Error(await response.text().catch(() => 'Download failed'));
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${jobName}.zip`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } catch (downloadError) {
        setError(downloadError instanceof Error ? downloadError.message : 'Failed to download dataset');
      } finally {
        setDownloadingJobId(null);
      }
    },
    [downloadingJobId]
  );

  const formKeys = useMemo(() => {
    const keys = new Set<string>();
    Object.keys(selectedRecipe?.params_schema || {}).forEach(key => keys.add(key));
    Object.keys(selectedRecipe?.default_params || {}).forEach(key => keys.add(key));
    return Array.from(keys).sort();
  }, [selectedRecipe]);

  const applyQuickPreset = useCallback(
    (workflow: QuickWorkflow) => {
      setActiveWorkflowId(workflow.id);
      setSearch('');
      setCategory('all');
      setFeaturedTrack('all');
      if (workflow.recipe_id) {
        setSelectedRecipeId(workflow.recipe_id);
        const entry = catalog?.entries.find(item => item.id === workflow.recipe_id);
        if (entry) {
          setRecipeParams({ ...entry.default_params, ...(workflow.preset_params || {}) });
        }
      } else if (workflow.search_terms?.length) {
        setSearch(workflow.search_terms[0]);
      }
    },
    [catalog]
  );

  const handleQuickPresetById = useCallback(
    (workflowId: string) => {
      const workflow = catalog?.quick_workflows.find(item => item.id === workflowId);
      if (workflow) applyQuickPreset(workflow);
    },
    [applyQuickPreset, catalog?.quick_workflows]
  );

  return (
    <div className="builder-shell flex h-full min-h-0 flex-col">
      {error ? (
        <div className="shrink-0 border-b border-red-500/25 bg-red-500/5 px-4 py-2 text-[12px] text-red-600 dark:text-red-300">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-[13px] text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading recipes…
        </div>
      ) : null}

      {!loading && catalog ? (
        <div className="flex min-h-0 flex-1">
          <BuilderRecipePanel
            recipes={filteredRecipes.map(entry => ({ id: entry.id, title: entry.title }))}
            selectedRecipeId={selectedRecipeId}
            onSelect={recipeId => {
              handleRecipeSelect(recipeId);
              setActiveWorkflowId('');
            }}
            search={search}
            onSearchChange={setSearch}
            quickWorkflows={catalog.quick_workflows}
            activeWorkflowId={activeWorkflowId}
            onQuickPreset={handleQuickPresetById}
          />

          <main className="cursor-chat-workspace flex min-w-0 flex-1 flex-col overflow-y-auto">
            {selectedRecipe ? (
              <div className="mx-auto w-full max-w-2xl space-y-4 px-6 py-8">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Dataset Builder</p>
                  <h2 className="mt-2 text-[1.125rem] font-medium tracking-tight text-foreground">{selectedRecipe.title}</h2>
                  <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">{selectedRecipe.description}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">{selectedRecipe.id}</p>
                </div>

                <div className="space-y-3">
                  {formKeys.map(key => {
                    const type = schemaFieldTypeFromSchemaOrValue(selectedRecipe.params_schema[key], recipeParams[key]);
                    const value = recipeParams[key];
                    if (type === 'bool') {
                      return (
                        <div key={key} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                          <Label className="text-[12px]">{fieldLabel(key)}</Label>
                          <Switch checked={Boolean(value)} onCheckedChange={checked => updateRecipeParam(key, checked)} />
                        </div>
                      );
                    }
                    if (type === 'list' || type === 'dict') {
                      return (
                        <JsonEditorField
                          key={key}
                          label={fieldLabel(key)}
                          value={value ?? (type === 'list' ? [] : {})}
                          emptyValue={type === 'list' ? [] : {}}
                          onCommit={nextValue => updateRecipeParam(key, nextValue)}
                        />
                      );
                    }
                    if (key === 'topic_count' && selectedRecipe.id === 'curated_realtime_corpus') {
                      const cap = topicCountCapForRecipe(selectedRecipe.id, limits ?? undefined);
                      const numericValue = Number(value ?? 100_000);
                      const presets = [100_000, 200_000];
                      return (
                        <div key={key} className="space-y-1.5">
                          <div className="flex items-baseline justify-between gap-2">
                            <Label className="text-[12px]">{fieldLabel(key)}</Label>
                            <span className="text-[10px] text-muted-foreground">
                              1,000 – {cap.toLocaleString()}
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {presets.map(preset => (
                              <button
                                key={preset}
                                type="button"
                                onClick={() => updateRecipeParam(key, preset)}
                                className={`rounded-md border px-2 py-1 text-[11px] font-medium transition ${
                                  numericValue === preset
                                    ? 'border-foreground/30 bg-muted text-foreground'
                                    : 'border-border text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                                }`}
                              >
                                {preset === 100_000 ? '1 Lakh' : '2 Lakh'}
                              </button>
                            ))}
                          </div>
                          <Input
                            type="number"
                            min={1000}
                            max={cap}
                            step={1000}
                            className="h-8 text-[12px]"
                            value={value === undefined || value === null ? '' : String(value)}
                            onChange={event => updateRecipeParam(key, coercePrimitiveValue('int', event.target.value))}
                          />
                        </div>
                      );
                    }
                    return (
                      <div key={key} className="space-y-1">
                        <Label className="text-[12px]">{fieldLabel(key)}</Label>
                        <Input
                          type={type === 'int' || type === 'float' ? 'number' : 'text'}
                          step={type === 'float' ? '0.01' : undefined}
                          className="h-8 text-[12px]"
                          value={value === undefined || value === null ? '' : String(value)}
                          onChange={event => updateRecipeParam(key, coercePrimitiveValue(type, event.target.value))}
                        />
                      </div>
                    );
                  })}
                </div>

                <ValidationDisplay errors={validation.errors} warnings={validation.warnings} />

                <details className="rounded-md border border-border text-[12px]">
                  <summary className="cursor-pointer px-3 py-2 text-muted-foreground hover:text-foreground">
                    Sample output (from generator)
                  </summary>
                  {sampleLoading ? (
                    <p className="border-t border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
                      Loading generator sample…
                    </p>
                  ) : sampleExpectedResult ? (
                    <p className="border-t border-border/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
                      {sampleExpectedResult}
                    </p>
                  ) : null}
                  <pre className="overflow-x-auto border-t border-border bg-[#1e1e1e] p-3 text-[11px] leading-5 text-slate-100">
                    <code>{sampleXml}</code>
                  </pre>
                </details>

                <div className="space-y-3 border-t border-border pt-3">
                  <SchedulePicker onScheduleChange={handleScheduleChange} />
                  <Button
                    onClick={handleCreateJob}
                    disabled={creating || !validation.isValid}
                    className="w-full"
                    size="sm"
                  >
                    {creating ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating job…
                      </>
                    ) : (
                      'Create dataset job'
                    )}
                  </Button>
                </div>

                {createdJobs.length > 0 ? (
                  <div className="space-y-2 border-t border-border pt-3">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Session jobs</p>
                    {createdJobs.map(job => (
                      <div key={job.id} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                        <div className="min-w-0">
                          <div className="truncate text-[12px] font-medium">{job.name}</div>
                          <div className="truncate font-mono text-[10px] text-muted-foreground">{job.id}</div>
                        </div>
                        <Button variant="outline" size="sm" onClick={() => handleDownload(job.id, job.name)} disabled={downloadingJobId === job.id}>
                          {downloadingJobId === job.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center px-6 py-10 text-center">
                <p className="max-w-sm text-[12px] leading-relaxed text-muted-foreground">
                  Select a recipe from the panel on the left to configure parameters and create a dataset job.
                </p>
              </div>
            )}
          </main>
        </div>
      ) : null}
    </div>
  );
}
