import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, Filter, Loader2, Search, Sparkles, Zap } from 'lucide-react';

import { SchedulePicker } from '@/components/SchedulePicker';
import { ValidationDisplay } from '@/components/ValidationDisplay';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useRecipeValidation } from '@/hooks/useRecipeValidation';
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
}

interface RecipeCatalogResponse {
  entries: RecipeCatalogEntry[];
  categories: RecipeCatalogFilter[];
  featured_tracks: RecipeCatalogFilter[];
  quick_workflows: QuickWorkflow[];
}

interface Limits {
  topicrefs_per_map_max?: number;
  total_topicrefs_max?: number;
  topics_max?: number;
  maps_max?: number;
}

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
  onCommit,
}: {
  label: string;
  value: unknown;
  onCommit: (nextValue: unknown) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value ?? (Array.isArray(value) ? [] : {}), null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(JSON.stringify(value ?? (Array.isArray(value) ? [] : {}), null, 2));
    setError(null);
  }, [value]);

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
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20"
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
      setLimits(limitsData);
      if (!selectedRecipeId && catalogData.entries.length > 0) {
        const first = catalogData.entries[0];
        setSelectedRecipeId(first.id);
        setRecipeParams({ ...first.default_params });
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

  const currentRecipe = useMemo(
    () => (selectedRecipe ? { type: selectedRecipe.id, ...recipeParams } : null),
    [recipeParams, selectedRecipe]
  );

  const validation = useRecipeValidation(currentRecipe, limits || undefined);

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

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-8">
      <div className="border-l-4 border-teal-500 pl-4">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Dataset Builder</h1>
        <p className="mt-2 max-w-3xl text-slate-600">
          Discover the full backend recipe catalog, filter by senior workflow tracks, inspect full XML examples, and create dataset jobs without frontend-specific recipe branching.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <Card>
          <CardContent className="flex items-center gap-3 py-10 text-slate-600">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading dynamic recipe catalog...
          </CardContent>
        </Card>
      ) : null}

      {!loading && catalog ? (
        <>
          <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="text-xl text-slate-900">Dynamic catalog</CardTitle>
                <CardDescription>
                  Search by recipe id, title, description, or tags. Filter by category or featured senior track.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
                    <Input
                      value={search}
                      onChange={event => setSearch(event.target.value)}
                      placeholder="Search by recipe id, title, tag, or description"
                      className="pl-9"
                    />
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSearch('');
                      setCategory('all');
                      setFeaturedTrack('all');
                      setActiveWorkflowId('');
                    }}
                  >
                    Reset filters
                  </Button>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <Filter className="h-4 w-4 text-slate-500" />
                    Category filters
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant={category === 'all' ? 'default' : 'outline'} size="sm" onClick={() => setCategory('all')}>
                      All categories
                    </Button>
                    {catalog.categories.map(item => (
                      <Button key={item.id} variant={category === item.id ? 'default' : 'outline'} size="sm" onClick={() => setCategory(item.id)}>
                        {item.label}
                      </Button>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <Sparkles className="h-4 w-4 text-slate-500" />
                    Featured senior tracks
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant={featuredTrack === 'all' ? 'default' : 'outline'} size="sm" onClick={() => setFeaturedTrack('all')}>
                      All tracks
                    </Button>
                    {catalog.featured_tracks.map(item => (
                      <Button key={item.id} variant={featuredTrack === item.id ? 'default' : 'outline'} size="sm" onClick={() => setFeaturedTrack(item.id)}>
                        {item.label}
                      </Button>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <Zap className="h-4 w-4 text-slate-500" />
                    Dataset quick cards
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    {catalog.quick_workflows.map(workflow => (
                      <button
                        key={workflow.id}
                        type="button"
                        onClick={() => {
                          setActiveWorkflowId(current => (current === workflow.id ? '' : workflow.id));
                          setCategory(workflow.category || 'all');
                          setFeaturedTrack(workflow.featured_track || 'all');
                        }}
                        className={`rounded-lg border p-4 text-left transition ${
                          activeWorkflowId === workflow.id
                            ? 'border-teal-500 bg-teal-50 shadow-sm'
                            : 'border-slate-200 bg-white hover:border-slate-300'
                        }`}
                      >
                        <div className="text-sm font-semibold text-slate-900">{workflow.title}</div>
                        <p className="mt-2 text-xs leading-5 text-slate-600">{workflow.description}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="text-sm font-semibold text-slate-900">
                    Catalog results ({filteredRecipes.length})
                  </div>
                  <div className="grid max-h-[520px] gap-3 overflow-y-auto pr-1">
                    {filteredRecipes.map(entry => (
                      <button
                        key={entry.id}
                        type="button"
                        onClick={() => handleRecipeSelect(entry.id)}
                        className={`rounded-lg border p-4 text-left transition ${
                          selectedRecipeId === entry.id
                            ? 'border-teal-500 bg-teal-50 shadow-sm'
                            : 'border-slate-200 bg-white hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-slate-900">{entry.title}</div>
                            <div className="mt-1 text-xs text-slate-500">{entry.id}</div>
                          </div>
                          <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-700">
                            {entry.category_label}
                          </span>
                        </div>
                        <p className="mt-3 text-sm leading-6 text-slate-600">{entry.description}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {entry.featured_track_labels.slice(0, 3).map(label => (
                            <span key={label} className="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-teal-700 ring-1 ring-teal-200">
                              {label}
                            </span>
                          ))}
                          {entry.tags.slice(0, 4).map(tag => (
                            <span key={tag} className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600">
                              {tag}
                            </span>
                          ))}
                        </div>
                      </button>
                    ))}
                    {filteredRecipes.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600">
                        No recipes match the current filters.
                      </div>
                    ) : null}
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-6">
              <Card className="border-slate-200">
                <CardHeader>
                  <CardTitle className="text-xl text-slate-900">Selected recipe</CardTitle>
                  <CardDescription>
                    Configure the selected recipe using backend schema defaults. New recipes appear automatically when catalog metadata is valid.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  {selectedRecipe ? (
                    <>
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h2 className="text-lg font-semibold text-slate-900">{selectedRecipe.title}</h2>
                            <p className="mt-1 text-sm text-slate-600">{selectedRecipe.description}</p>
                            <p className="mt-2 text-xs text-slate-500">{selectedRecipe.id}</p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {selectedRecipe.featured_track_labels.map(label => (
                              <span key={label} className="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-teal-700 ring-1 ring-teal-200">
                                {label}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        {formKeys.length > 0 ? (
                          formKeys.map(key => {
                            const type = schemaFieldType(selectedRecipe.params_schema[key]);
                            const value = recipeParams[key];
                            if (type === 'bool') {
                              return (
                                <div key={key} className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3">
                                  <div>
                                    <Label className="text-sm font-semibold text-slate-900">{fieldLabel(key)}</Label>
                                    <p className="text-xs text-slate-500">{fieldHelpText(type)}</p>
                                  </div>
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
                                  onCommit={nextValue => updateRecipeParam(key, nextValue)}
                                />
                              );
                            }
                            return (
                              <div key={key} className="space-y-2">
                                <Label className="text-sm font-semibold text-slate-900">{fieldLabel(key)}</Label>
                                <Input
                                  type={type === 'int' || type === 'float' ? 'number' : 'text'}
                                  step={type === 'float' ? '0.01' : undefined}
                                  value={value === undefined || value === null ? '' : String(value)}
                                  onChange={event => updateRecipeParam(key, coercePrimitiveValue(type, event.target.value))}
                                />
                                <p className="text-xs text-slate-500">{fieldHelpText(type)}</p>
                              </div>
                            );
                          })
                        ) : (
                          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                            This recipe uses catalog-driven defaults and does not expose additional parameters yet.
                          </div>
                        )}
                      </div>

                      <ValidationDisplay errors={validation.errors} warnings={validation.warnings} />

                      <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div>
                          <h3 className="text-sm font-semibold text-slate-900">Full example</h3>
                          <p className="mt-1 text-xs text-slate-500">Curated XML when available, otherwise a safe backend fallback.</p>
                        </div>
                        <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 text-xs leading-6 text-slate-100">
                          <code>{selectedRecipe.full_example_xml}</code>
                        </pre>
                        <div className="rounded-lg border border-teal-100 bg-teal-50 px-4 py-3 text-sm text-teal-900">
                          <span className="font-semibold">Expected result:</span> {selectedRecipe.expected_result}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600">
                      Select a recipe from the catalog to configure it.
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-slate-200">
                <CardHeader>
                  <CardTitle className="text-xl text-slate-900">Create job</CardTitle>
                  <CardDescription>
                    Keep the same select → configure → validate → create flow, now powered by catalog-driven defaults.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <SchedulePicker onScheduleChange={handleScheduleChange} />
                  <Button onClick={handleCreateJob} disabled={creating || !selectedRecipe || !validation.isValid} className="w-full">
                    {creating ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating job...
                      </>
                    ) : (
                      'Create dataset job'
                    )}
                  </Button>
                </CardContent>
              </Card>

              <Card className="border-slate-200">
                <CardHeader>
                  <CardTitle className="text-xl text-slate-900">Created jobs</CardTitle>
                  <CardDescription>Download recent dataset outputs from this Builder session.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {createdJobs.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                      No jobs created in this session yet.
                    </div>
                  ) : (
                    createdJobs.map(job => (
                      <div key={job.id} className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">{job.name}</div>
                          <div className="text-xs text-slate-500">{job.id}</div>
                        </div>
                        <Button variant="outline" onClick={() => handleDownload(job.id, job.name)} disabled={downloadingJobId === job.id}>
                          {downloadingJobId === job.id ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              Downloading
                            </>
                          ) : (
                            <>
                              <Download className="mr-2 h-4 w-4" />
                              Download
                            </>
                          )}
                        </Button>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
