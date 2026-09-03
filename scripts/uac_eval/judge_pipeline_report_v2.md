# Real-pipeline (evidence-grounded) vs baseline, LLM-judged, held-out

Test tickets: 8 | seed 5 | judge model: gpt-5.2 | pipeline: canonical runtime on http://10.42.46.78:4502

| metric | baseline | real pipeline |
|---|---|---|
| mean coverage vs gold | 39.5% | 91.8% |
| mean hallucinations | 3.5 | 10.8 |
| mean holistic (1-5) | 2.5 | 2.6 |

## Per ticket
- GUIDES-48893 (Review) [pipeline blocked, 31284 chars]: baseline 20%/3 -> pipeline 100%/3
- GUIDES-37733 (Publishing) [pipeline blocked, 38400 chars]: baseline 67%/3 -> pipeline 100%/3
- GUIDES-53807 (Publishing) [pipeline blocked, 34077 chars]: baseline 38%/2 -> pipeline 85%/3
- GUIDES-8979 (Authoring) [pipeline blocked, 39677 chars]: baseline 20%/2 -> pipeline 100%/3
- GUIDES-46748 (Authoring) [pipeline blocked, 27923 chars]: baseline 38%/2 -> pipeline 86%/2
- GUIDES-40399 (Publishing) [pipeline blocked, 25316 chars]: baseline 60%/3 -> pipeline 100%/2
- GUIDES-28102 (Publishing) [pipeline blocked, 20679 chars]: baseline 40%/2 -> pipeline 80%/2
- GUIDES-33731 (Schematron) [pipeline blocked, 31858 chars]: baseline 33%/3 -> pipeline 83%/3