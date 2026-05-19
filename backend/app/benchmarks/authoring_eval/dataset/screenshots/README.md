# Optional screenshot fixtures

Add PNG files here and reference them from `manifest.yaml` with `screenshot_path: screenshots/your.png`.

If `screenshot_path` is omitted, the harness uses a minimal 1×1 PNG and drives structure from the `vision` block in the manifest (offline-friendly).

For **live** evaluation with real vision models, keep using the manifest `vision` block only as expected-output hints for scoring—not as the model output unless you disable the stub in a dedicated job.
