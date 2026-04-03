"""Shared dataset job orchestration for routes and chat tools."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.db.session import SessionLocal
from app.jobs import crud
from app.jobs.schemas import DatasetConfig
from app.storage import get_storage
from app.tasks.generate_dataset import run_generate_dataset

logger = get_structured_logger(__name__)

DEFAULT_CONCURRENT_JOB_LIMIT = 20
_MISSING = object()


class ConcurrentJobLimitError(RuntimeError):
    """Raised when a user exceeds the allowed concurrent running jobs."""


def validate_dataset_job_config(config_dict: dict) -> DatasetConfig:
    """Validate a dataset config and return the parsed model."""
    return DatasetConfig.model_validate(config_dict)


def normalize_dataset_job_config(config_dict: dict) -> dict[str, Any]:
    """Return a JSON-safe, validated dataset config."""
    dataset_config = validate_dataset_job_config(config_dict)
    return dataset_config.model_dump(mode="json")


def build_dataset_job_urls(job_id: str) -> dict[str, str]:
    """Return the canonical status/download URLs for a dataset job."""
    safe_job_id = str(job_id).strip()
    return {
        "status_url": f"/api/v1/jobs/{safe_job_id}",
        "download_url": f"/api/v1/datasets/{safe_job_id}/download",
    }


def enforce_concurrent_job_limit(
    user_id: str,
    *,
    limit: int = DEFAULT_CONCURRENT_JOB_LIMIT,
) -> None:
    """Raise when a user already has too many running jobs."""
    session = SessionLocal()
    try:
        running_jobs, _ = crud.get_user_jobs(
            session,
            user_id=user_id,
            status="running",
            limit=None,
        )
        running_count = len(running_jobs)
        if running_count >= limit:
            raise ConcurrentJobLimitError(
                f"Too many concurrent jobs running ({running_count}/{limit}). "
                "Please wait for some jobs to complete before creating new ones."
            )
    finally:
        session.close()


def create_dataset_job_record(
    config_dict: dict,
    *,
    user_id: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Create and persist a validated dataset job record."""
    normalized_config = normalize_dataset_job_config(config_dict)
    job_name = str(name or normalized_config.get("name") or "Dataset Generation").strip() or "Dataset Generation"

    session = SessionLocal()
    try:
        job = crud.create_job(
            session,
            config=normalized_config,
            name=job_name,
            user_id=user_id,
        )
        session.commit()
        session.refresh(job)
        return {
            "id": str(job.id),
            "name": str(job.name),
            "status": str(job.status),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "config": normalized_config,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_dataset_job_summary(job_id: str) -> dict[str, Any] | None:
    """Fetch the latest summary payload for a dataset job."""
    session = SessionLocal()
    try:
        job = crud.get_job(session, job_id)
        if not job:
            return None
        return {
            "id": str(job.id),
            "name": str(job.name),
            "status": str(job.status),
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
    finally:
        session.close()


def _estimate_total_topics(dataset_config: DatasetConfig) -> int:
    return sum(
        getattr(recipe, "topic_count", 0)
        for recipe in dataset_config.recipes
        if hasattr(recipe, "topic_count")
    )


def _update_job_record(
    job_id: str,
    *,
    status: str | object = _MISSING,
    error_message: str | None | object = _MISSING,
    result: dict[str, Any] | None | object = _MISSING,
    progress_percent: int | None | object = _MISSING,
    files_generated: int | None | object = _MISSING,
    total_files_estimated: int | None | object = _MISSING,
    current_stage: str | None | object = _MISSING,
) -> dict[str, Any]:
    session = SessionLocal()
    try:
        job = crud.get_job(session, job_id)
        if not job:
            raise LookupError(f"Dataset job not found: {job_id}")

        if status is not _MISSING:
            job.status = str(status)
            if status == "running" and not job.started_at:
                job.started_at = datetime.utcnow()
            if status in {"completed", "failed"}:
                job.completed_at = datetime.utcnow()
        if error_message is not _MISSING:
            job.error_message = error_message
        if result is not _MISSING:
            job.result = result
        if progress_percent is not _MISSING:
            job.progress_percent = None if progress_percent is None else max(0, min(100, int(progress_percent)))
        if files_generated is not _MISSING:
            job.files_generated = files_generated
        if total_files_estimated is not _MISSING:
            job.total_files_estimated = total_files_estimated
        if current_stage is not _MISSING:
            job.current_stage = current_stage

        session.commit()
        session.refresh(job)
        return {
            "id": str(job.id),
            "name": str(job.name),
            "status": str(job.status),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "error_message": job.error_message,
            "progress_percent": job.progress_percent,
            "files_generated": job.files_generated,
            "total_files_estimated": job.total_files_estimated,
            "current_stage": job.current_stage,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _format_dataset_generation_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    lowered = message.lower()
    if isinstance(exc, TimeoutError) or any(keyword in lowered for keyword in ("timeout", "timed out", "request timeout")):
        return (
            f"Generation timed out: {message[:500]}. "
            "Large datasets may take longer than the current request window."
        )
    if isinstance(exc, MemoryError):
        return (
            f"Generation ran out of memory: {message[:500]}. "
            "Try a smaller dataset or enable a lighter recipe configuration."
        )
    return message[:1000]


def run_dataset_job(job_id: str, config_dict: dict) -> dict[str, Any]:
    """Generate dataset files, persist them, and update job state."""
    dataset_config = validate_dataset_job_config(config_dict)
    total_topic_count = _estimate_total_topics(dataset_config)
    total_files_estimated = total_topic_count if total_topic_count > 0 else 100
    use_streaming = total_topic_count > 10000
    storage = get_storage()

    try:
        _update_job_record(
            job_id,
            status="running",
            error_message=None,
            result=None,
            progress_percent=0,
            files_generated=0,
            total_files_estimated=total_files_estimated,
            current_stage="Starting generation",
        )

        sample_files: list[str] = []

        def progress_callback(progress_percent: int, files_generated: int, current_stage: str) -> None:
            _update_job_record(
                job_id,
                progress_percent=progress_percent,
                files_generated=files_generated,
                total_files_estimated=total_files_estimated,
                current_stage=current_stage,
            )

        if use_streaming:
            file_count = [0]

            def stream_batch(batch_files: dict[str, bytes]) -> None:
                storage.save_dataset_batch(job_id, batch_files)
                file_count[0] += len(batch_files)
                if len(sample_files) < 5:
                    sample_files.extend(list(batch_files.keys())[: 5 - len(sample_files)])
                if total_files_estimated > 0:
                    progress_percent = min(95, int((file_count[0] / total_files_estimated) * 95))
                    progress_callback(
                        progress_percent,
                        file_count[0],
                        f"Generating topics ({file_count[0]}/{total_files_estimated})",
                    )

            progress_callback(0, 0, "Starting generation")
            trailing_files = run_generate_dataset(
                config_dict,
                job_id,
                stream_callback=stream_batch,
                progress_callback=progress_callback,
            )
            if trailing_files:
                storage.save_dataset_batch(job_id, trailing_files)
                file_count[0] += len(trailing_files)
                if len(sample_files) < 5:
                    sample_files.extend(list(trailing_files.keys())[: 5 - len(sample_files)])
            total_files = file_count[0]
            result_file_list = sample_files[:5]
        else:
            progress_callback(0, 0, "Starting generation")
            files = run_generate_dataset(config_dict, job_id, progress_callback=progress_callback)
            if files:
                storage.save_dataset(job_id, files)
                sample_files = list(files.keys())[:5]
            total_files = len(files)
            result_file_list = list(files.keys())[:10]

        progress_callback(100, total_files, "Generation complete")

        if not storage.exists(job_id):
            raise RuntimeError("Dataset files were not saved to storage")

        result = {
            "files_generated": total_files,
            "file_list": result_file_list,
        }
        _update_job_record(
            job_id,
            status="completed",
            error_message=None,
            result=result,
            progress_percent=100,
            files_generated=total_files,
            total_files_estimated=total_files_estimated,
            current_stage="Generation complete",
        )
        return result
    except Exception as exc:
        error_message = _format_dataset_generation_error(exc)
        logger.error_structured(
            "Dataset generation failed",
            extra_fields={
                "job_id": job_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        _update_job_record(
            job_id,
            status="failed",
            error_message=error_message,
        )
        return {"error_message": error_message}


def start_dataset_job_in_background(job_id: str, config_dict: dict) -> asyncio.Task[Any]:
    """Run dataset generation in a background task on the current event loop."""

    async def _runner() -> dict[str, Any]:
        return await asyncio.to_thread(run_dataset_job, job_id, config_dict)

    task = asyncio.create_task(_runner(), name=f"dataset-job-{job_id}")

    def _log_failure(done_task: asyncio.Task[Any]) -> None:
        try:
            done_task.result()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error_structured(
                "Background dataset generation task crashed",
                extra_fields={"job_id": job_id, "error": str(exc)},
                exc_info=True,
            )

    task.add_done_callback(_log_failure)
    return task
