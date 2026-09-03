# Draft-vs-gold scoring (baseline LLM, no skill)

Mode: baseline | Sample: 20 tickets (seed 11) | model: gpt-5.2
Mean dimension recall (draft vs human gold): **53.1%**

## Most-missed dimensions (gold had it, blind draft dropped it)
- state_partition: missed 6/9 times (67% of the tickets where the human included it)
- multi_surface: missed 5/8 times (62% of the tickets where the human included it)
- negative_error: missed 5/10 times (50% of the tickets where the human included it)
- regression_parity: missed 3/8 times (38% of the tickets where the human included it)
- cross_tool_oracle: missed 2/3 times (67% of the tickets where the human included it)
- output_preset: missed 2/2 times (100% of the tickets where the human included it)
- localization: missed 1/3 times (33% of the tickets where the human included it)
- performance: missed 1/2 times (50% of the tickets where the human included it)
- attachment_or_bigcontent: missed 1/1 times (100% of the tickets where the human included it)

## Per ticket
### GUIDES-48587 (Authoring) - recall 0.0%
- missed: cross_tool_oracle, state_partition
### GUIDES-40399 (Publishing) - recall 50.0%
- missed: state_partition
### GUIDES-42652 (Asset Management) - recall 0.0%
- missed: multi_surface
### GUIDES-35125 (Review) - recall 0.0%
- missed: multi_surface
### GUIDES-28688 (Native PDF) - recall 100.0%
- missed: none
### GUIDES-37837 (Platform) - recall 50.0%
- missed: negative_error
### GUIDES-16709 (Translation) - recall 50.0%
- missed: negative_error, state_partition
### GUIDES-33247 (Editor) - recall 33.0%
- missed: negative_error, regression_parity
### GUIDES-14500 (Schematron) - recall 50.0%
- missed: negative_error
### GUIDES-44773 (Baseline) - recall 100.0%
- missed: none
### GUIDES-38783 (UUID Migration) - recall 25.0%
- missed: cross_tool_oracle, localization, multi_surface, output_preset, performance, state_partition
### GUIDES-53230 (Learning) - recall 33.0%
- missed: multi_surface, state_partition
### GUIDES-28918 (AI) - recall 0.0%
- missed: multi_surface, state_partition
### GUIDES-27774 (Reports) - recall 50.0%
- missed: regression_parity
### GUIDES-43481 (Database) - recall 100.0%
- missed: none
### GUIDES-19067 ((none)) - recall 50.0%
- missed: negative_error, regression_parity
### GUIDES-24537 (Miscellaneous) - recall 100.0%
- missed: none
### GUIDES-37935 (Citation Management) - recall 71.0%
- missed: attachment_or_bigcontent, output_preset
### GUIDES-33228 (Ditaval) - recall 100.0%
- missed: none
### GUIDES-31765 (External Data Sources) - recall 100.0%
- missed: none