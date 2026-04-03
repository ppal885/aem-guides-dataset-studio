import { useState, useEffect } from 'react';

interface ValidationError {
  field: string;
  message: string;
  severity: 'error' | 'warning';
}

interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
}

interface Limits {
  topicrefs_per_map_max?: number;
  total_topicrefs_max?: number;
  topics_max?: number;
  maps_max?: number;
}

export function useRecipeValidation(recipe: any, limits?: Limits): ValidationResult {
  const [validation, setValidation] = useState<ValidationResult>({
    isValid: true,
    errors: [],
    warnings: [],
  });

  useEffect(() => {
    const errors: ValidationError[] = [];
    const warnings: ValidationError[] = [];

    if (!recipe) {
      setValidation({ isValid: false, errors, warnings });
      return;
    }

    // Incremental Topicref Maps validation
    if (recipe.type === 'incremental_topicref_maps') {
      const mapCounts = recipe.map_topicref_counts || [];
      if (mapCounts.length > 0) {
        const maxCount = Math.max(...mapCounts);
        
        if (maxCount > recipe.pool_size) {
          errors.push({
            field: 'map_topicref_counts',
            message: `Maximum topicref count (${maxCount}) exceeds pool size (${recipe.pool_size})`,
            severity: 'error',
          });
        }

        // For incremental_topicref_maps, allow large topicref counts (this recipe is designed for performance testing)
        // Only show as warning if significantly exceeds the general limit
        if (limits?.topicrefs_per_map_max && maxCount > limits.topicrefs_per_map_max * 2) {
          warnings.push({
            field: 'map_topicref_counts',
            message: `Topicref count (${maxCount}) significantly exceeds recommended maximum per map (${limits.topicrefs_per_map_max}). This may impact performance.`,
            severity: 'warning',
          });
        } else if (maxCount >= 10000) {
          warnings.push({
            field: 'map_topicref_counts',
            message: 'Large topicref counts (10k+) may significantly slow map parsing',
            severity: 'warning',
          });
        }

        const totalTopicrefs = mapCounts.reduce((sum: number, count: number) => sum + count, 0);
        if (limits?.total_topicrefs_max && totalTopicrefs > limits.total_topicrefs_max) {
          errors.push({
            field: 'map_topicref_counts',
            message: `Total topicrefs (${totalTopicrefs}) exceeds maximum (${limits.total_topicrefs_max})`,
            severity: 'error',
          });
        }
      }
    }

    // Insurance Incremental validation
    if (recipe.type === 'insurance_incremental') {
      const mapSizes = recipe.map_sizes || [];
      if (mapSizes.length > 0) {
        const maxSize = Math.max(...mapSizes);
        
        if (maxSize > recipe.max_topics) {
          errors.push({
            field: 'map_sizes',
            message: `Maximum map size (${maxSize}) exceeds max topics (${recipe.max_topics})`,
            severity: 'error',
          });
        }

        // Check if map sizes are in increasing order
        const sortedSizes = [...mapSizes].sort((a, b) => a - b);
        if (JSON.stringify(mapSizes) !== JSON.stringify(sortedSizes)) {
          errors.push({
            field: 'map_sizes',
            message: 'Map sizes must be in increasing order',
            severity: 'error',
          });
        }

        // Warning for large map sizes
        if (maxSize >= 10000) {
          warnings.push({
            field: 'map_sizes',
            message: 'Large map sizes (10k+) may significantly slow map parsing',
            severity: 'warning',
          });
        }

        // Validate max_topics range
        if (recipe.max_topics < 10 || recipe.max_topics > 50000) {
          errors.push({
            field: 'max_topics',
            message: 'Max topics must be between 10 and 50000',
            severity: 'error',
          });
        }
      } else {
        errors.push({
          field: 'map_sizes',
          message: 'At least one map size is required',
          severity: 'error',
        });
      }
    }

    // Heavy Topics validation
    if (recipe.type === 'heavy_topics_tables_codeblocks') {
      if (recipe.map_topicref_count > recipe.topic_count) {
        errors.push({
          field: 'map_topicref_count',
          message: `Map topicref count (${recipe.map_topicref_count}) exceeds topic count (${recipe.topic_count})`,
          severity: 'error',
        });
      }

      if (limits?.topicrefs_per_map_max && recipe.map_topicref_count > limits.topicrefs_per_map_max) {
        errors.push({
          field: 'map_topicref_count',
          message: `Map topicref count (${recipe.map_topicref_count}) exceeds maximum per map (${limits.topicrefs_per_map_max})`,
          severity: 'error',
        });
      }

      const totalBlocks = recipe.topic_count * (recipe.tables_per_topic + recipe.codeblocks_per_topic);
      if (totalBlocks > 10000) {
        warnings.push({
          field: 'tables_per_topic',
          message: `Large number of blocks (${totalBlocks}) may impact generation time`,
          severity: 'warning',
        });
      }
    }

    // Customer Reuse validation
    if (recipe.type === 'customer_reuse_pack') {
      if (limits?.topicrefs_per_map_max && recipe.topic_references_per_map > limits.topicrefs_per_map_max) {
        errors.push({
          field: 'topic_references_per_map',
          message: `Topic references per map (${recipe.topic_references_per_map}) exceeds maximum (${limits.topicrefs_per_map_max})`,
          severity: 'error',
        });
      }
    }

    setValidation({
      isValid: errors.length === 0,
      errors,
      warnings,
    });
  }, [recipe, limits]);

  return validation;
}
