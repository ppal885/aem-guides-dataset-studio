# Draft-vs-gold scoring (LLM + skill guidance/priors)

Mode: skill | Sample: 20 tickets (seed 11) | model: gpt-5.2
Mean dimension recall (draft vs human gold): **96.8%**

## Most-missed dimensions (gold had it, blind draft dropped it)
- localization: missed 1/3 times (33% of the tickets where the human included it)
- performance: missed 1/2 times (50% of the tickets where the human included it)
- output_preset: missed 1/2 times (50% of the tickets where the human included it)
- cross_tool_oracle: missed 1/3 times (33% of the tickets where the human included it)
- attachment_or_bigcontent: missed 1/1 times (100% of the tickets where the human included it)

## Per ticket
### GUIDES-48587 (Authoring) - recall 100.0%
- missed: none
### GUIDES-40399 (Publishing) - recall 100.0%
- missed: none
### GUIDES-42652 (Asset Management) - recall 100.0%
- missed: none
### GUIDES-35125 (Review) - recall 100.0%
- missed: none
### GUIDES-28688 (Native PDF) - recall 100.0%
- missed: none
### GUIDES-37837 (Platform) - recall 100.0%
- missed: none
### GUIDES-16709 (Translation) - recall 100.0%
- missed: none
### GUIDES-33247 (Editor) - recall 100.0%
- missed: none
### GUIDES-14500 (Schematron) - recall 100.0%
- missed: none
### GUIDES-44773 (Baseline) - recall 100.0%
- missed: none
### GUIDES-38783 (UUID Migration) - recall 50.0%
- missed: cross_tool_oracle, localization, output_preset, performance
### GUIDES-53230 (Learning) - recall 100.0%
- missed: none
### GUIDES-28918 (AI) - recall 100.0%
- missed: none
### GUIDES-27774 (Reports) - recall 100.0%
- missed: none
### GUIDES-43481 (Database) - recall 100.0%
- missed: none
### GUIDES-19067 ((none)) - recall 100.0%
- missed: none
### GUIDES-24537 (Miscellaneous) - recall 100.0%
- missed: none
### GUIDES-37935 (Citation Management) - recall 86.0%
- missed: attachment_or_bigcontent
### GUIDES-33228 (Ditaval) - recall 100.0%
- missed: none
### GUIDES-31765 (External Data Sources) - recall 100.0%
- missed: none