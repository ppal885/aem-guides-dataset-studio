# Screenshot-guided DITA authoring — pipeline traces

The backend runs screenshot-guided topic generation through a **staged pipeline** (`run_screenshot_guided_pipeline` in `backend/app/services/dita_authoring_pipeline.py`). Each stage appends a serializable record to `AuthoringPipelineTrace`, exposed on successful runs in `ChatDitaAuthoringResult.debug` as:

- `pipeline_run_id` — UUID for correlation with structured logs
- `pipeline_version` — e.g. `screenshot_guided_v1`
- `pipeline_trace` — list of stage records (same shape as `AuthoringPipelineTrace.to_debug_list()`)
- `serialization_mode` — `programmatic` or `llm` from the serialize stage

## Structured logs

For every stage completion, the logger emits `authoring_pipeline_stage` with fields such as `pipeline_run_id`, `stage`, `stage_order`, `duration_ms`, `ok`, and scalar `detail_*` fields derived from stage metadata. When the pipeline finishes, `authoring_pipeline_complete` is logged with `stage_count` and `final_dita_type`.

## Example `pipeline_trace` (valid run, no repair)

Illustrative JSON (values will differ per request):

```json
[
  {
    "stage": "analyze_screenshot",
    "order": 1,
    "duration_ms": 1200.5,
    "ok": true,
    "detail": {
      "vision_provider": "openai",
      "screenshot_confidence": 0.87,
      "uncertainty_count": 1
    }
  },
  {
    "stage": "analyze_reference_topic",
    "order": 2,
    "duration_ms": 3.2,
    "ok": true,
    "detail": {
      "had_reference": true,
      "parse_reference_ok": true
    }
  },
  {
    "stage": "infer_topic_type",
    "order": 3,
    "duration_ms": 0.15,
    "ok": true,
    "detail": {
      "dita_type": "task",
      "user_override": false,
      "reference_guided_enabled": true
    }
  },
  {
    "stage": "build_semantic_plan",
    "order": 4,
    "duration_ms": 850.0,
    "ok": true,
    "detail": {
      "section_count": 4,
      "dita_type": "task"
    }
  },
  {
    "stage": "merge_screenshot_structured",
    "order": 5,
    "duration_ms": 0.08,
    "ok": true,
    "detail": {
      "merged_section_count": 5
    }
  },
  {
    "stage": "build_structured_draft",
    "order": 6,
    "duration_ms": 0.12,
    "ok": true,
    "detail": {
      "draft_sections": 5,
      "draft_tables": 0,
      "draft_notes": 1
    }
  },
  {
    "stage": "serialize_xml",
    "order": 7,
    "duration_ms": 45.0,
    "ok": true,
    "detail": {
      "serialization_mode": "programmatic",
      "xml_chars": 1840
    }
  },
  {
    "stage": "validate",
    "order": 8,
    "duration_ms": 120.0,
    "ok": true,
    "detail": {
      "valid": true,
      "validation_error_count": 0,
      "validation_warning_count": 1
    }
  }
]
```

## Example with optional repair

When validation fails and `strict_validation` is enabled, a ninth record is appended:

```json
{
  "stage": "repair_optional",
  "order": 9,
  "duration_ms": 400.0,
  "ok": true,
  "detail": {
    "repaired": true,
    "valid_after": true
  }
}
```

## Contracts between stages

Typed outputs are defined in `dita_authoring_pipeline.py` (Pydantic models): `ScreenshotAnalysisResult` → `ReferenceAnalysisResult` → `TopicTypeResult` → `SemanticPlanResult` → `MergedPlanResult` → `StructuredDraftResult` → `SerializationResult` → `ValidationStageResult` → optional `RepairStageResult`. The chat service adapts LLM/validation hooks via `_ScreenshotGuidedPipelineExecutor` and maps the final XML and validation state into `ChatDitaAuthoringResult`.
