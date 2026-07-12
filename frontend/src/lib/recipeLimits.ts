/** Server-reported limits with safe client fallbacks for scale recipes. */
export interface RecipeLimits {
  topicrefs_per_map_max?: number;
  total_topicrefs_max?: number;
  topics_max?: number;
  curated_topics_max?: number;
  large_scale_topics_max?: number;
  maps_max?: number;
}

export const DEFAULT_CURATED_TOPIC_MAX = 200_000;
export const DEFAULT_LARGE_SCALE_TOPIC_MAX = 1_000_000;
export const DEFAULT_TOPICS_MAX = 200_000;

export function normalizeRecipeLimits(raw: RecipeLimits | null | undefined): RecipeLimits {
  const topicsMax = Math.max(raw?.topics_max ?? 0, DEFAULT_TOPICS_MAX);
  return {
    ...raw,
    topics_max: topicsMax,
    curated_topics_max: Math.max(raw?.curated_topics_max ?? 0, DEFAULT_CURATED_TOPIC_MAX),
    large_scale_topics_max: Math.max(raw?.large_scale_topics_max ?? 0, DEFAULT_LARGE_SCALE_TOPIC_MAX),
    topicrefs_per_map_max: raw?.topicrefs_per_map_max ?? 25_000,
    total_topicrefs_max: raw?.total_topicrefs_max ?? 100_000,
    maps_max: raw?.maps_max ?? 100,
  };
}

export function topicCountCapForRecipe(
  recipeType: string | undefined,
  limits?: RecipeLimits
): number {
  const normalized = normalizeRecipeLimits(limits);
  if (recipeType === 'curated_realtime_corpus') {
    return normalized.curated_topics_max ?? DEFAULT_CURATED_TOPIC_MAX;
  }
  if (recipeType === 'large_scale') {
    return normalized.large_scale_topics_max ?? DEFAULT_LARGE_SCALE_TOPIC_MAX;
  }
  return normalized.topics_max ?? DEFAULT_TOPICS_MAX;
}
