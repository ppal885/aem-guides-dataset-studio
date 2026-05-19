"""
Evaluation harness for screenshot + reference DITA authoring.

See docs/benchmarks-authoring-eval.md for metrics, baselines, and workflow.
"""

from app.benchmarks.authoring_eval.models import BenchmarkCase, BenchmarkManifest, CaseEvalReport, SuiteReport
from app.benchmarks.authoring_eval.runner import evaluate_manifest, evaluate_single_case

__all__ = [
    "BenchmarkCase",
    "BenchmarkManifest",
    "CaseEvalReport",
    "SuiteReport",
    "evaluate_manifest",
    "evaluate_single_case",
]
