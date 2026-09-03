# Baseline vs Skill (n=20, seed 11, same sample)

- Baseline (description-only LLM): **53.1%** mean dimension recall
- Skill (LLM + priors + forcing rules): **96.8%**
- **Lift: 43.7 points**

## Per-dimension misses (baseline -> skill)
- negative_error: gold~10, misses 5 -> 0
- state_partition: gold~9, misses 6 -> 0
- regression_parity: gold~8, misses 3 -> 0
- multi_surface: gold~8, misses 5 -> 0
- cross_tool_oracle: gold~3, misses 2 -> 1
- localization: gold~3, misses 1 -> 1
- performance: gold~2, misses 1 -> 1
- output_preset: gold~2, misses 2 -> 1