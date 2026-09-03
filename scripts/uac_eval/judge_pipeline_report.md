# Real-pipeline (evidence-grounded) vs baseline, LLM-judged, held-out

Test tickets: 8 | seed 5 | judge model: gpt-5.2 | pipeline: canonical runtime on http://10.42.46.78:4502

| metric | baseline | real pipeline |
|---|---|---|
| mean coverage vs gold | 41.2% | 94.3% |
| mean hallucinations | 3.4 | 11.0 |
| mean holistic (1-5) | 2.2 | 3.0 |

## Per ticket
- GUIDES-48893 (Review) [pipeline blocked, 0 chars]: baseline 60%/3 -> pipeline None%/None
- GUIDES-37733 (Publishing) [pipeline blocked, 0 chars]: baseline 33%/2 -> pipeline None%/None
- GUIDES-53807 (Publishing) [pipeline blocked, 0 chars]: baseline 31%/2 -> pipeline None%/None
- GUIDES-8979 (Authoring) [pipeline blocked, 0 chars]: baseline 20%/2 -> pipeline None%/None
- GUIDES-46748 (Authoring) [pipeline blocked, 0 chars]: baseline 38%/2 -> pipeline None%/None
- GUIDES-40399 (Publishing) [pipeline blocked, 25316 chars]: baseline 75%/3 -> pipeline 100%/2
- GUIDES-28102 (Publishing) [pipeline blocked, 20679 chars]: baseline 40%/2 -> pipeline 100%/3
- GUIDES-33731 (Schematron) [pipeline blocked, 31858 chars]: baseline 33%/2 -> pipeline 83%/4