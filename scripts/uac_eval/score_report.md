# Blind-draft-vs-gold scoring (baseline LLM, no skill)

Sample: 40 tickets | model: gpt-5.2
Mean dimension recall (draft vs human gold): **71.8%**

## Most-missed dimensions (gold had it, blind draft dropped it)
- state_partition: missed 10/19 times (53% of the tickets where the human included it)
- regression_parity: missed 6/14 times (43% of the tickets where the human included it)
- multi_surface: missed 5/13 times (38% of the tickets where the human included it)
- negative_error: missed 5/18 times (28% of the tickets where the human included it)
- cross_tool_oracle: missed 3/4 times (75% of the tickets where the human included it)
- css_styles: missed 2/3 times (67% of the tickets where the human included it)
- provenance_channels: missed 2/10 times (20% of the tickets where the human included it)
- performance: missed 2/5 times (40% of the tickets where the human included it)
- attachment_or_bigcontent: missed 1/1 times (100% of the tickets where the human included it)
- output_preset: missed 1/6 times (17% of the tickets where the human included it)
- permissions_role: missed 1/5 times (20% of the tickets where the human included it)

## Per ticket
### GUIDES-27507 (Authoring) - recall 100.0%
- missed: none
### GUIDES-25969 (Publishing) - recall 67.0%
- missed: state_partition
### GUIDES-28443 (Asset Management) - recall 80.0%
- missed: state_partition
### GUIDES-48893 (Review) - recall 100.0%
- missed: none
### GUIDES-19958 (Native PDF) - recall 67.0%
- missed: css_styles
### GUIDES-28574 (Platform) - recall 67.0%
- missed: cross_tool_oracle
### GUIDES-45396 (Translation) - recall 33.0%
- missed: regression_parity, state_partition
### GUIDES-33464 (Editor) - recall 50.0%
- missed: multi_surface
### GUIDES-48105 (Schematron) - recall 50.0%
- missed: multi_surface
### GUIDES-44773 (Baseline) - recall 100.0%
- missed: none
### GUIDES-33794 (UUID Migration) - recall 100.0%
- missed: none
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
### GUIDES-27362 (Authoring) - recall 100.0%
- missed: none
### GUIDES-34298 (Publishing) - recall 100.0%
- missed: none
### GUIDES-33605 (Asset Management) - recall 40.0%
- missed: negative_error, permissions_role, state_partition
### GUIDES-49153 (Review) - recall 75.0%
- missed: provenance_channels
### GUIDES-25680 (Native PDF) - recall 100.0%
- missed: none
### GUIDES-7207 (Platform) - recall 17.0%
- missed: cross_tool_oracle, multi_surface, performance, provenance_channels, state_partition
### GUIDES-51759 (Translation) - recall 100.0%
- missed: none
### GUIDES-48457 (Editor) - recall 0.0%
- missed: state_partition
### GUIDES-14505 (Schematron) - recall 60.0%
- missed: performance, regression_parity
### GUIDES-14786 (Baseline) - recall 75.0%
- missed: negative_error
### GUIDES-46526 (UUID Migration) - recall 100.0%
- missed: none
### GUIDES-52343 (Learning) - recall 100.0%
- missed: none
### GUIDES-29781 (Authoring) - recall 100.0%
- missed: none
### GUIDES-24789 (Publishing) - recall 100.0%
- missed: none
### GUIDES-8912 (Asset Management) - recall 20.0%
- missed: cross_tool_oracle, negative_error, regression_parity, state_partition
### GUIDES-38669 (Review) - recall 100.0%
- missed: none
### GUIDES-19703 (Native PDF) - recall 33.0%
- missed: css_styles, state_partition
### GUIDES-18372 (Platform) - recall 100.0%
- missed: none
### GUIDES-49386 (Translation) - recall 100.0%
- missed: none
### GUIDES-33247 (Editor) - recall 33.0%
- missed: negative_error, regression_parity