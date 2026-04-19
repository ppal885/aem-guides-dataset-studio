import { useState, useEffect, useCallback, useRef } from 'react';
import { ValidationDisplay } from '@/components/ValidationDisplay';
import { SchedulePicker } from '@/components/SchedulePicker';
import { useRecipeValidation } from '@/hooks/useRecipeValidation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { TaskTopicsConfig } from '@/components/TaskTopicsConfig';
import { ConceptTopicsConfig } from '@/components/ConceptTopicsConfig';
import { ReferenceTopicsConfig } from '@/components/ReferenceTopicsConfig';
import { SyntaxDiagramReferenceConfig } from '@/components/SyntaxDiagramReferenceConfig';
import { GlossaryPackConfig } from '@/components/GlossaryPackConfig';
import { BookmapStructureConfig } from '@/components/BookmapStructureConfig';
import { MediaRichConfig } from '@/components/MediaRichConfig';
import { WorkflowConfig } from '@/components/WorkflowConfig';
import { KeyscopeDemoConfig } from '@/components/KeyscopeDemoConfig';
import { KeywordMetadataConfig } from '@/components/KeywordMetadataConfig';
import { IncrementalTopicrefMapsConfig } from '@/components/IncrementalTopicrefMapsConfig';
import { InsuranceIncrementalConfig } from '@/components/InsuranceIncrementalConfig';
import { RelationshipTableConfig } from '@/components/RelationshipTableConfig';
import { ConrefPackConfig } from '@/components/ConrefPackConfig';
import { ConditionalContentConfig } from '@/components/ConditionalContentConfig';
import { LocalizationConfig } from '@/components/LocalizationConfig';
import { PerformanceScaleConfig } from '@/components/PerformanceScaleConfig';
import { LegacyPatternsConfig } from '@/components/LegacyPatternsConfig';
import { MapParseStressConfig } from '@/components/MapParseStressConfig';
import { HeavyConditionalTopicConfig } from '@/components/HeavyConditionalTopicConfig';
import { NestedKeydefChainConfig } from '@/components/NestedKeydefChainConfig';
import { CustomerReusePackConfig } from '@/components/CustomerReusePackConfig';
import { AdvancedRelationshipsConfig } from '@/components/AdvancedRelationshipsConfig';
import { Sparkles, Zap, Download, Loader2 } from 'lucide-react';
import { RecipeTypeSelect } from '@/components/RecipeTypeSelect';
import { cn } from '@/lib/utils';

export function Builder() {
  const [currentRecipe, setCurrentRecipe] = useState<any>(null);
  const [limits, setLimits] = useState<any>(null);
  const [scheduledAt, setScheduledAt] = useState<Date | null>(null);
  const [timezone, setTimezone] = useState('UTC');
  const [loading, setLoading] = useState(false);
  const [downloadingJobId, setDownloadingJobId] = useState<string | null>(null);
  const [createdJobs, setCreatedJobs] = useState<Array<{id: string, name: string, createdAt?: string, recipeType?: string}>>([]);
  const isMountedRef = useRef(true);

  const validation = useRecipeValidation(currentRecipe, limits);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    fetch('/api/v1/limits')
      .then(res => res.json())
      .then(data => {
        if (isMountedRef.current) {
          setLimits(data);
        }
      })
      .catch(err => {
        if (isMountedRef.current) {
          console.error('Failed to load limits:', err);
          setLimits({
            topicrefs_per_map_max: 5000,
            total_topicrefs_max: 100000,
            topics_max: 10000,
            maps_max: 100,
          });
        }
      });
  }, []);


  const handleScheduleChange = useCallback((scheduledAt: Date | null, timezone: string) => {
    setScheduledAt(scheduledAt);
    setTimezone(timezone);
  }, []);

  const handleDownload = useCallback(async (jobId: string, jobName: string) => {
    if (downloadingJobId === jobId) {
      return;
    }

    setDownloadingJobId(jobId);
    
    try {
      console.log(`Downloading job ${jobId}...`);
      
      // Use setTimeout to allow UI to update before starting download
      await new Promise(resolve => setTimeout(resolve, 50));
      
      const response = await fetch(`/api/v1/datasets/${jobId}/download`);
      
      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        console.error('Download failed:', response.status, errorText);
        alert(`Failed to download: ${errorText}`);
        return;
      }
      
      // Use blob() which handles streaming internally and is non-blocking
      // The browser will handle the download in the background
      const blob = await response.blob();
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${jobName || jobId}.zip`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      
      // Cleanup after a short delay to ensure download starts
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }, 100);
      
      console.log(`Download completed for job ${jobId}`);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download dataset. Please try again.');
    } finally {
      // Delay clearing the loading state slightly to show feedback
      setTimeout(() => {
        setDownloadingJobId(null);
      }, 500);
    }
  }, [downloadingJobId]);

  const handleCreateJob = useCallback(async () => {
    if (!validation.isValid) {
      alert('Please fix validation errors before creating job');
      return;
    }

    if (!currentRecipe) {
      alert('Please select or configure a recipe');
      return;
    }

    setLoading(true);

    const jobData = {
      config: {
        name: 'My Dataset',
        seed: 'test-seed',
        root_folder: '/content/dam/dataset-studio',
        windows_safe_filenames: true,
        doctype_topic: '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        doctype_map: '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
        recipes: [currentRecipe],
      },
    };

    try {
      let response;
      if (scheduledAt) {
        response = await fetch('/api/v1/jobs/schedule', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...jobData,
            scheduled_at: scheduledAt.toISOString(),
            timezone,
          }),
        });
      } else {
        response = await fetch('/api/v1/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(jobData),
        });
      }

      if (response.ok) {
        const job = await response.json();
        const jobId = job.id;
        const createdAt = job.created_at || new Date().toISOString();
        const recipeType = currentRecipe?.type || 'unknown';
        
        // Generate unique name based on recipe type and timestamp
        const words = recipeType.split('_');
        const recipeTypeName = words
          .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
        const timestamp = new Date(createdAt);
        const timeStr = timestamp.toLocaleString('en-US', {
          month: 'short',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: true
        });
        const uniqueName = `${recipeTypeName} - ${timeStr}`;
        
        // Add to created jobs list
        setCreatedJobs(prev => [...prev, { 
          id: jobId, 
          name: uniqueName,
          createdAt: createdAt,
          recipeType: recipeType
        }]);
        
        alert(`Job created successfully! ID: ${jobId}\n\nYou can download the dataset once generation completes.`);
        setCurrentRecipe(null);
        setScheduledAt(null);
      } else {
        let errorMessage = 'Unknown error';
        try {
          const errorText = await response.text();
          if (errorText) {
            try {
              const error = JSON.parse(errorText);
              errorMessage = error.detail || error.message || JSON.stringify(error);
            } catch {
              errorMessage = errorText;
            }
          } else {
            errorMessage = `HTTP ${response.status}: ${response.statusText}`;
          }
        } catch (e) {
          errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        }
        console.error('Failed to create job:', errorMessage);
        alert(`Failed to create job: ${errorMessage}`);
      }
    } catch (error) {
      console.error('Failed to create job:', error);
      alert(`Failed to create job: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  }, [currentRecipe, scheduledAt, timezone, validation.isValid]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="border-l-4 border-teal-500 pl-4">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Dataset Builder</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Create and configure AEM Guides dataset generation jobs — same workflow as Job History and Dataset Explorer.
        </p>
      </div>

      <div className="space-y-6 pb-2">
        {/* Recipe Configuration */}
        <Card className="border border-slate-200 shadow-[0_4px_24px_-4px_rgba(15,23,42,0.08)] ring-1 ring-slate-900/[0.04] transition-shadow duration-200 hover:shadow-md">
              <CardHeader className="border-b border-slate-200 pb-3">
                <CardTitle className="text-xl font-semibold text-slate-900 mb-1.5">
                  Recipe Configuration
                </CardTitle>
                <CardDescription className="text-sm text-slate-600 leading-relaxed">
                  Customize your dataset generation recipe. Select a recipe type below to configure how your content will be structured and generated.
                </CardDescription>
              </CardHeader>
            <CardContent className="pt-5 space-y-5">
              <div className="space-y-2">
                <label className="block text-sm font-semibold text-slate-900">
                  Recipe Type
                </label>
                <p className="text-xs text-slate-500 mb-3">
                  Configuration template for dataset generation
                </p>
                <RecipeTypeSelect
                  value={currentRecipe?.type || ''}
                  onChange={(type) => {
                    if (type) {
                      if (type === 'incremental_topicref_maps') {
                        setCurrentRecipe({
                          type,
                          pool_size: 10000,
                          map_topicref_counts: [10, 100, 1000, 5000, 10000],
                          pretty_print: true,
                          deep_folders: false,
                        });
                      } else if (type === 'insurance_incremental') {
                        setCurrentRecipe({
                          type,
                          max_topics: 10000,
                          map_sizes: [10, 100, 1000, 5000, 10000],
                          include_local_dtd_stubs: true,
                          output_root_folder_name: 'aem_guides_insurance_incremental',
                        });
                      } else if (type === 'heavy_topics_tables_codeblocks') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          tables_per_topic: 5,
                          codeblocks_per_topic: 5,
                          table_cols: 4,
                          table_rows: 10,
                          code_lines_per_codeblock: 20,
                          include_map: true,
                          map_topicref_count: 50,
                          pretty_print: true,
                          windows_safe_paths: true,
                        });
                      } else if (type === 'task_topics') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          steps_per_task: 5,
                          include_prereq: true,
                          include_result: true,
                          include_choicetable: false,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'concept_topics') {
                        setCurrentRecipe({
                          type: 'concept_topics',
                          topic_count: 50,
                          sections_per_concept: 3,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'reference_topics') {
                        setCurrentRecipe({
                          type: 'reference_topics',
                          topic_count: 50,
                          properties_per_ref: 5,
                          include_choicetable: false,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'glossary_pack') {
                        setCurrentRecipe({
                          type: 'glossary_pack',
                          entry_count: 100,
                          include_acronyms: true,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'bookmap_structure') {
                        setCurrentRecipe({
                          type: 'bookmap_structure',
                          chapter_count: 10,
                          topics_per_chapter: 5,
                          include_frontmatter: true,
                          include_backmatter: true,
                          pretty_print: true,
                        });
                      } else if (type === 'media_rich_content') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          images_per_topic: 3,
                          generate_images: true,
                          image_width: 800,
                          image_height: 600,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'workflow_enabled_content') {
                        setCurrentRecipe({
                          type,
                          base_recipe: {
                            type: 'task_topics',
                            topic_count: 10,
                            steps_per_task: 5,
                            include_prereq: true,
                            include_result: true,
                            include_map: true,
                            pretty_print: true,
                          },
                          include_review: true,
                          include_translation: true,
                          include_approval: true,
                          reviewers: ['reviewer1', 'reviewer2'],
                          target_languages: ['es', 'fr'],
                        });
                      } else if (type === 'keyscope_demo') {
                        setCurrentRecipe({
                          type,
                          id_prefix: 't',
                          include_qualified_keyrefs: true,
                          pretty_print: true,
                        });
                      } else if (type === 'maps_topicgroup_basic' || type === 'maps_topicgroup_nested' || type === 'maps_topicref_basic' || type === 'maps_nested_topicrefs' || type === 'maps_mapref_basic' || type === 'maps_topichead_basic' || type === 'maps_reltable_basic' || type === 'maps_topicset_basic' || type === 'maps_navref_basic') {
                        setCurrentRecipe({
                          type,
                          id_prefix: 't',
                          pretty_print: true,
                        });
                      } else if (type === 'keyword_metadata') {
                        setCurrentRecipe({
                          type,
                          id_prefix: 't',
                          num_keywords: 10,
                          num_categories: 5,
                          num_topics: 8,
                          pretty_print: true,
                        });
                      } else if (type === 'relationship_table') {
                        setCurrentRecipe({
                          type,
                          topic_count: 100,
                          relationship_types: ['next', 'previous', 'related'],
                          relationship_density: 0.3,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'conref_pack') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          reusable_elements_per_topic: 3,
                          conref_density: 0.3,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'dita_conref_title_dataset_recipe') {
                        setCurrentRecipe({
                          type,
                          topic_count: 10,
                          pretty_print: true,
                          id_prefix: 't',
                        });
                      } else if (type === 'dita_conref_keyref_dataset_recipe') {
                        setCurrentRecipe({
                          type,
                          topic_count: 15,
                          id_prefix: 't',
                          pretty_print: true,
                        });
                      } else if (type === 'dita_subject_scheme_dataset_recipe') {
                        setCurrentRecipe({
                          type,
                          valid_count: 10,
                          invalid_count: 10,
                          id_prefix: 't',
                          pretty_print: true,
                        });
                      } else if (type === 'dita_glossary_abbrev_dataset_recipe') {
                        setCurrentRecipe({
                          type,
                          entry_count: 15,
                          usage_topic_count: 10,
                          id_prefix: 't',
                          pretty_print: true,
                        });
                      } else if (type === 'conditional_content') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          audiences: ['admin', 'user', 'developer'],
                          platforms: ['windows', 'mac', 'linux'],
                          products: ['product-a', 'product-b'],
                          generate_ditaval: true,
                          ditaval_profiles: ['admin-windows', 'user-all'],
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'localized_content') {
                        setCurrentRecipe({
                          type,
                          base_recipe: {
                            type: 'task_topics',
                            topic_count: 10,
                            steps_per_task: 5,
                            include_prereq: true,
                            include_result: true,
                            include_map: true,
                            pretty_print: true,
                          },
                          source_language: 'en',
                          target_languages: ['es', 'fr', 'de'],
                          include_translation_metadata: true,
                        });
                      } else if (type === 'output_optimized') {
                        setCurrentRecipe({
                          type,
                          base_recipe: {
                            type: 'task_topics',
                            topic_count: 10,
                            steps_per_task: 5,
                            include_prereq: true,
                            include_result: true,
                            include_map: true,
                            pretty_print: true,
                          },
                          output_format: 'aemsite',
                          optimization_options: {},
                        });
                      } else if (type === 'large_scale') {
                        setCurrentRecipe({
                          type,
                          topic_count: 100000,
                          batch_size: 1000,
                          pretty_print: false,
                        });
                      } else if (type === 'deep_hierarchy') {
                        setCurrentRecipe({
                          type,
                          depth: 10,
                          children_per_level: 5,
                          include_maps: true,
                          pretty_print: true,
                        });
                      } else if (type === 'wide_branching') {
                        setCurrentRecipe({
                          type,
                          root_topics: 2,
                          children_per_root: 1000,
                          include_maps: true,
                          pretty_print: true,
                        });
                      } else if (type === 'hub_spoke_inbound') {
                        setCurrentRecipe({
                          type,
                          topic_count: 100,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'keydef_heavy') {
                        setCurrentRecipe({
                          type,
                          topic_count: 100,
                          keydef_count: 50,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'map_cyclic') {
                        setCurrentRecipe({
                          type,
                          id_prefix: 't',
                          pretty_print: true,
                        });
                      } else if (type === 'map_parse_stress') {
                        setCurrentRecipe({
                          type,
                          map_count: 10,
                          topicrefs_per_map: 1000,
                          pretty_print: true,
                        });
                      } else if (type === 'keyref_nested_keydef_chain_map_to_map_to_topic') {
                        setCurrentRecipe({
                          type,
                          root_map_name: 'map_a.ditamap',
                          intermediate_map_name: 'map_b.ditamap',
                          keyword_topic_name: 'topic_c_keywords.dita',
                          consumer_topic_name: 'topic_d_consumer.dita',
                          root_map_title: 'Outer Context Map',
                          intermediate_map_title: 'Static Key Map',
                          keyword_topic_title: 'Keyword Source Topic',
                          consumer_topic_title: 'Consumer Topic',
                          root_to_intermediate_key: 'staticKeyMap',
                          direct_intermediate_key_name: 'productName',
                          nested_keyword_file_key_name: 'keywordFile',
                          nested_keyword_id: 'versionString',
                          consumer_keyrefs: ['productName', 'versionString'],
                          include_direct_key_in_root_map: true,
                          include_direct_key_in_intermediate_map: true,
                          include_nested_keyword_topic: true,
                          include_workaround_notes: true,
                          generation_mode: 'minimal_repro',
                          add_negative_variant: false,
                          add_workaround_variant: false,
                          id_prefix: 't',
                          pretty_print: true,
                        });
                      } else if (type === 'heavy_conditional_topic_6000_lines') {
                        setCurrentRecipe({
                          type,
                          topic_id: 'heavy_conditional_topic_001',
                          title: 'Enterprise Conditional Processing Heavy Topic',
                          target_lines: 6000,
                          section_count: 120,
                          subsections_per_section: 4,
                          paragraphs_per_subsection: 6,
                          include_tables: true,
                          include_codeblocks: true,
                          include_notes: true,
                          include_examples: true,
                          include_xrefs: false,
                          include_images: false,
                          include_ditaval: true,
                          condition_density: 'high',
                          audience_values: ['beginner', 'advanced', 'admin', 'developer', 'author', 'reviewer'],
                          platform_values: ['windows', 'linux', 'mac', 'cloud', 'web'],
                          otherprops_values: ['cloud', 'onprem', 'hybrid', 'internal', 'external', 'beta', 'prod', 'staging'],
                          tables_per_n_sections: 2,
                          codeblocks_per_n_sections: 2,
                          notes_per_n_sections: 3,
                          examples_per_n_sections: 3,
                          pretty_print: true,
                        });
                      } else if (type === 'advanced_relationships') {
                        setCurrentRecipe({
                          type,
                          topic_count: 100,
                          relationship_patterns: ['hierarchical', 'cross_map', 'conditional'],
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'customer_reuse_pack') {
                        setCurrentRecipe({
                          type,
                          remove_map_count: 10,
                          shared_topics: 500,
                          topic_references_per_map: 100,
                          key_definitions: 200,
                          key_groups: 5,
                          external_references: 10,
                        });
                      } else if (type === 'choicetable_tasks') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          steps_per_task: 5,
                          choices_per_topic: 4,
                          include_map: true,
                          pretty_print: true,
                        });
                      } else if (type === 'choicetable_references') {
                        setCurrentRecipe({
                          type,
                          topic_count: 50,
                          choices_per_topic: 5,
                          include_map: true,
                          pretty_print: true,
                        });
                      // Enterprise scenarios
                      } else if (type === 'parent_child_maps_keys_conref_conkeyref_selfrefs') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'compact_parent_child_key_resolution') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'conrefend_cyclic_duplicate_id') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'large_root_map_1000_topics_100kb') {
                        setCurrentRecipe({ type, topic_count: 1000, pretty_print: true });
                      // Specialized additions
                      } else if (type === 'properties_table_reference') {
                        setCurrentRecipe({ type, topic_count: 30, properties_per_ref: 5, include_map: true, pretty_print: true });
                      } else if (type === 'syntax_diagram_reference') {
                        setCurrentRecipe({ type, topic_count: 30, include_map: true, pretty_print: true });
                      } else if (type === 'bookmap_elements_reference') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'table_semantics_reference') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'topic_ph_keyword_related_links') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      // Advanced additions
                      } else if (type === 'topic_svg_mathml_foreign') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'inline_formatting_nested') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'nested_topic_inline') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'self_conrefend_range') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      } else if (type === 'self_xref_conref_positive') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      // Performance addition
                      } else if (type === 'bulk_dita_map_topics') {
                        setCurrentRecipe({ type, topic_count: 20000, include_local_dtd_stubs: true, pretty_print: true });
                      } else if (type === 'flat_hierarchical_dita') {
                        setCurrentRecipe({ type, topic_count: 5000, topics_per_section: 50, include_xrefs: false, pretty_print: true });
                      // Validation & Negative
                      } else if (type === 'validation_duplicate_id_negative' || type === 'validation_invalid_child_negative' || type === 'validation_missing_body_negative') {
                        setCurrentRecipe({ type, id_prefix: 't', pretty_print: true });
                      }
                    } else {
                      setCurrentRecipe(null);
                    }
                  }}
                />
              </div>

              {currentRecipe?.type === 'incremental_topicref_maps' && (
                <IncrementalTopicrefMapsConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'insurance_incremental' && (
                <InsuranceIncrementalConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'task_topics' && (
                <TaskTopicsConfig 
                  recipe={{...currentRecipe, type: 'task_topics'}} 
                  onChange={(updatedRecipe) => {
                    setCurrentRecipe({...updatedRecipe, type: 'task_topics'});
                  }} 
                />
              )}
              {currentRecipe?.type === 'concept_topics' && (
                <ConceptTopicsConfig 
                  recipe={{...currentRecipe, type: 'concept_topics'}} 
                  onChange={(updatedRecipe) => {
                    setCurrentRecipe({...updatedRecipe, type: 'concept_topics'});
                  }} 
                />
              )}
              {currentRecipe?.type === 'reference_topics' && (
                <ReferenceTopicsConfig 
                  recipe={{...currentRecipe, type: 'reference_topics'}} 
                  onChange={(updatedRecipe) => {
                    setCurrentRecipe({...updatedRecipe, type: 'reference_topics'});
                  }} 
                />
              )}
              {currentRecipe?.type === 'glossary_pack' && (
                <GlossaryPackConfig 
                  recipe={{...currentRecipe, type: 'glossary_pack'}} 
                  onChange={(updatedRecipe) => {
                    setCurrentRecipe({...updatedRecipe, type: 'glossary_pack'});
                  }} 
                />
              )}
              {currentRecipe?.type === 'bookmap_structure' && (
                <BookmapStructureConfig 
                  recipe={{...currentRecipe, type: 'bookmap_structure'}} 
                  onChange={(updatedRecipe) => {
                    setCurrentRecipe({...updatedRecipe, type: 'bookmap_structure'});
                  }} 
                />
              )}
              {currentRecipe?.type === 'media_rich_content' && (
                <MediaRichConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'workflow_enabled_content' && (
                <WorkflowConfig 
                  recipe={{...currentRecipe, type: 'workflow_enabled_content'}} 
                  onChange={(updatedRecipe) => {
                    setCurrentRecipe({...updatedRecipe, type: 'workflow_enabled_content'});
                  }} 
                />
              )}
              {currentRecipe?.type === 'keyscope_demo' && (
                <KeyscopeDemoConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'keyword_metadata' && (
                <KeywordMetadataConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'relationship_table' && (
                <RelationshipTableConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'conref_pack' && (
                <ConrefPackConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'conditional_content' && (
                <ConditionalContentConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'localized_content' && (
                <LocalizationConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'large_scale' && (
                <PerformanceScaleConfig recipe={currentRecipe} onChange={setCurrentRecipe} recipeType="large_scale" />
              )}
              {currentRecipe?.type === 'deep_hierarchy' && (
                <PerformanceScaleConfig recipe={currentRecipe} onChange={setCurrentRecipe} recipeType="deep_hierarchy" />
              )}
              {currentRecipe?.type === 'wide_branching' && (
                <PerformanceScaleConfig recipe={currentRecipe} onChange={setCurrentRecipe} recipeType="wide_branching" />
              )}
              {currentRecipe?.type === 'hub_spoke_inbound' && (
                <LegacyPatternsConfig recipe={currentRecipe} onChange={setCurrentRecipe} recipeType="hub_spoke_inbound" />
              )}
              {currentRecipe?.type === 'keydef_heavy' && (
                <LegacyPatternsConfig recipe={currentRecipe} onChange={setCurrentRecipe} recipeType="keydef_heavy" />
              )}
              {currentRecipe?.type === 'map_cyclic' && (
                <LegacyPatternsConfig recipe={currentRecipe} onChange={setCurrentRecipe} recipeType="map_cyclic" />
              )}
              {currentRecipe?.type === 'map_parse_stress' && (
                <MapParseStressConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'keyref_nested_keydef_chain_map_to_map_to_topic' && (
                <NestedKeydefChainConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'heavy_conditional_topic_6000_lines' && (
                <HeavyConditionalTopicConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'advanced_relationships' && (
                <AdvancedRelationshipsConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'customer_reuse_pack' && (
                <CustomerReusePackConfig recipe={currentRecipe} onChange={setCurrentRecipe} />
              )}
              {currentRecipe?.type === 'output_optimized' && (
                <div className="rounded-lg border border-teal-200/80 bg-teal-50/60 p-4">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 shrink-0 rounded-full bg-teal-600" />
                    <p className="text-sm text-slate-700">
                      Output Optimized recipe configured. Select base recipe and output format.
                    </p>
                  </div>
                </div>
              )}

              <ValidationDisplay 
                errors={validation.errors} 
                warnings={validation.warnings} 
              />

              {/* Schedule Picker */}
              {currentRecipe && (
                <div className="pt-5 border-t border-slate-200">
                  <SchedulePicker onScheduleChange={handleScheduleChange} />
                </div>
              )}

              {/* Create Job Button */}
              {currentRecipe && validation.isValid && (
                <div className="pt-3">
                  <Button
                    onClick={handleCreateJob}
                    disabled={loading}
                    className="w-full py-3.5 text-base font-semibold shadow-md shadow-teal-900/15 transition-all duration-200 hover:shadow-lg disabled:shadow-none"
                    size="lg"
                  >
                    {loading ? (
                      <span className="flex items-center justify-center gap-2">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        Creating...
                      </span>
                    ) : scheduledAt ? (
                      <span className="flex items-center justify-center gap-2">
                        <Zap className="w-4 h-4" /> Schedule Job
                      </span>
                    ) : (
                      <span className="flex items-center justify-center gap-2">
                        <Sparkles className="w-4 h-4" /> Create Dataset Now
                      </span>
                    )}
                  </Button>
                </div>
              )}

              {!currentRecipe && (
                <div className="pt-5 text-center py-6 border-t border-slate-200">
                  <p className="text-sm text-slate-500">
                    Select a recipe type above to get started
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Created Jobs - Below main card */}
          {createdJobs.length > 0 && (
            <Card className="border border-slate-200 shadow-[0_4px_24px_-4px_rgba(15,23,42,0.08)] ring-1 ring-slate-900/[0.04] transition-shadow duration-200 hover:shadow-md">
              <CardHeader className="border-b border-slate-200 pb-3">
                <CardTitle className="text-lg font-semibold text-slate-900">
                  Created Jobs ({createdJobs.length})
                </CardTitle>
                <CardDescription className="text-sm text-slate-600 mt-1">
                  Download your generated datasets
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {createdJobs.map((job) => {
                    const createdAt = job.createdAt ? new Date(job.createdAt) : null;
                    const formattedTime = createdAt 
                      ? createdAt.toLocaleString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                          hour12: true
                        })
                      : 'Unknown time';
                    const shortId = job.id.substring(0, 8);
                    
                    return (
                      <div
                        key={job.id}
                        className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50/90 p-3 transition-colors hover:border-teal-200/80 hover:bg-teal-50/40"
                      >
                        <div className="flex-1 min-w-0 pr-3">
                          <p className="text-sm font-semibold text-slate-900 truncate mb-1">
                            {job.name}
                          </p>
                          <div className="flex items-center gap-2 text-xs text-slate-500">
                            <span className="truncate">{formattedTime}</span>
                            <span className="text-slate-300">•</span>
                            <span className="font-mono truncate">{shortId}</span>
                          </div>
                        </div>
                        <Button
                          onClick={() => handleDownload(job.id, job.name)}
                          size="sm"
                          variant="outline"
                          disabled={downloadingJobId === job.id}
                          className="flex items-center gap-2 ml-3 flex-shrink-0"
                        >
                          {downloadingJobId === job.id ? (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Downloading...
                            </>
                          ) : (
                            <>
                              <Download className="h-4 w-4" />
                              Download
                            </>
                          )}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}
      </div>
    </div>
  );
}

export default Builder;
