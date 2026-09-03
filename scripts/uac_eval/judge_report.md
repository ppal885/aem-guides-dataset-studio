# Held-out, LLM-judged baseline vs skill

Test tickets (held out): 12 | train: 212 | model/judge: gpt-5.2 | seed 5
Priors rebuilt from TRAIN only; judge scores coverage & correctness vs human gold.

| metric | baseline | skill |
|---|---|---|
| mean coverage vs gold | 42.5% | 40.4% |
| mean hallucinations | 3.1 | 13.3 |
| mean holistic (1-5) | 2.4 | 2.3 |

## Per ticket (coverage% / holistic)
- GUIDES-48893 (Review): baseline 60%/3 -> skill 0%/1
- GUIDES-37733 (Publishing): baseline 33%/2 -> skill 67%/2
- GUIDES-53807 (Publishing): baseline 25%/2 -> skill 18%/2
- GUIDES-8979 (Authoring): baseline 20%/2 -> skill 0%/1
- GUIDES-46748 (Authoring): baseline 38%/2 -> skill 50%/3
- GUIDES-40399 (Publishing): baseline 60%/3 -> skill 60%/3
- GUIDES-28102 (Publishing): baseline 40%/2 -> skill 40%/2
- GUIDES-33731 (Schematron): baseline 33%/2 -> skill 33%/2
- GUIDES-29815 (Publishing): baseline 55%/3 -> skill 55%/3
- GUIDES-28443 (Asset Management): baseline 35%/2 -> skill 45%/3
- GUIDES-37220 (Authoring): baseline 57%/3 -> skill 71%/3
- GUIDES-38412 (Schematron): baseline 54%/3 -> skill 46%/3