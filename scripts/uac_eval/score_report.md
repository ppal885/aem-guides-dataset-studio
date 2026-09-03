# Blind-draft-vs-gold scoring (baseline LLM, no skill)

Sample: 12 tickets | model: gpt-5.2
Mean dimension recall (draft vs human gold): **75.4%**

## Most-missed dimensions (gold had it, blind draft dropped it)
- multi_surface: missed 3/7 times (43% of the tickets where the human included it)
- state_partition: missed 2/5 times (40% of the tickets where the human included it)
- permissions_role: missed 1/1 times (100% of the tickets where the human included it)
- cross_tool_oracle: missed 1/1 times (100% of the tickets where the human included it)
- negative_error: missed 1/5 times (20% of the tickets where the human included it)

## Per ticket
### GUIDES-33012 (Publishing) - recall 100.0%
- missed: none
### GUIDES-28748 (Authoring) - recall 50.0%
- missed: permissions_role
### GUIDES-28443 (Asset Management) - recall 80.0%
- missed: state_partition
### GUIDES-48893 (Review) - recall 100.0%
- missed: none
### GUIDES-19958 (Native PDF) - recall 100.0%
- missed: none
### GUIDES-28574 (Platform) - recall 67.0%
- missed: cross_tool_oracle
### GUIDES-49386 (Translation) - recall 100.0%
- missed: none
### GUIDES-33464 (Editor) - recall 50.0%
- missed: multi_surface
### GUIDES-48105 (Schematron) - recall 50.0%
- missed: multi_surface
### GUIDES-14786 (Baseline) - recall 75.0%
- missed: negative_error
### GUIDES-33794 (UUID Migration) - recall 100.0%
- missed: none
### GUIDES-53230 (Learning) - recall 33.0%
- missed: multi_surface, state_partition