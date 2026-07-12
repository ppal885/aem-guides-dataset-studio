import { describe, expect, it } from 'vitest';

import {
  DEFAULT_CURATED_TOPIC_MAX,
  normalizeRecipeLimits,
  topicCountCapForRecipe,
} from './recipeLimits';

describe('recipeLimits', () => {
  it('normalizes stale API limits to curated minimums', () => {
    const normalized = normalizeRecipeLimits({ topics_max: 25_000 });
    expect(normalized.topics_max).toBe(DEFAULT_CURATED_TOPIC_MAX);
    expect(normalized.curated_topics_max).toBe(DEFAULT_CURATED_TOPIC_MAX);
  });

  it('uses curated cap for curated_realtime_corpus', () => {
    expect(topicCountCapForRecipe('curated_realtime_corpus', { topics_max: 25_000 })).toBe(200_000);
  });

  it('allows 100k curated topic count to pass validation cap', () => {
    const cap = topicCountCapForRecipe('curated_realtime_corpus', { topics_max: 25_000 });
    expect(100_000 <= cap).toBe(true);
  });
});
