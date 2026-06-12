"""Worker service — picks up scheduled jobs from Redis and executes them in Docker.

Lifecycle:
  1. Register in the workers table.
  2. Start heartbeat coroutine.
  3. BLPOP from Redis queue for run_ids.
  4. For each run_id:
     a. Fetch job, job_input, job_run, env_vars, gpu_allocations from DB.
     b. Check for cancellation.
     c. Set statuses to running.
     d. Prepare workspace (copy file or clone repo).
     e. Snapshot workspace (before).
     f. Execute via DockerRunner.
     g. Snapshot workspace (after).
     h. Collect artifacts (diff snapshots).
     i. Copy logs to NAS.
     j. Update DB with results.
     k. Release GPUs.
     l. Reset worker status to idle.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models import (
    GpuDevice,
    Job,
    JobArtifact,
    JobCommand,
    JobEnvVar,
    JobEvent,
    JobInput,
    JobRun,
    JobRunGpuAllocation,
    Worker,
)
from app.services.docker_runner import DockerRunner, RunConfig
from app.services.redis_queue import pop_job, set_heartbeat
from app.services.storage import (
    collect_artifacts,
    copy_logs_to_nas,
    logs_dir,
    nas_output_dir,
    prepare_workspace,
    snapshot_workspace,
    workspace_dir,
)

logger = logging.getLogger("worker")
settings = get_settings()

runner = DockerRunner()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker main loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def run_worker() -> None:
    """Main worker loop — register, heartbeat, and process jobs."""

    worker_id = await _register_worker()
    logger.info("Worker registered: %s (id=%s)", settings.worker_name, worker_id)

    # Start heartbeat in background
    heartbeat_task = asyncio.create_task(_heartbeat_loop(worker_id))

    try:
        await _job_loop(worker_id)
    except asyncio.CancelledError:
        logger.info("Worker shutting down")
    finally:
        heartbeat_task.cancel()
        # Mark worker as offline
        async with async_session_factory() as db:
            async with db.begin():
                result = await db.execute(
                    select(Worker).where(Worker.id == worker_id)
                )
                worker = result.scalars().first()
                if worker:
                    worker.status = "offline"


async def _register_worker() -> uuid.UUID:
    """Register or update this worker in the database."""
    hostname = platform.node()
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        async with db.begin():
            # Try to find existing worker by name
            result = await db.execute(
                select(Worker).where(Worker.worker_name == settings.worker_name)
            )
            worker = result.scalars().first()

            if worker:
                worker.hostname = hostname
                worker.status = "idle"
                worker.last_heartbeat_at = now
                worker.current_job_run_id = None
                await db.flush()
                return worker.id
            else:
                worker = Worker(
                    worker_name=settings.worker_name,
                    hostname=hostname,
                    status="idle",
                    last_heartbeat_at=now,
                    version="1.0.0",
                )
                db.add(worker)
                await db.flush()
                return worker.id


async def _heartbeat_loop(worker_id: uuid.UUID) -> None:
    """Send heartbeats to both Redis and PostgreSQL."""
    interval = settings.worker_heartbeat_interval

    while True:
        try:
            # Redis heartbeat (ephemeral)
            await set_heartbeat(worker_id, ttl=interval * 3)

            # PostgreSQL heartbeat (persistent)
            async with async_session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Worker).where(Worker.id == worker_id)
                    )
                    worker = result.scalars().first()
                    if worker:
                        worker.last_heartbeat_at = datetime.now(timezone.utc)

        except Exception:
            logger.exception("Heartbeat failed")

        await asyncio.sleep(interval)


async def _job_loop(worker_id: uuid.UUID) -> None:
    """Continuously pop jobs from Redis and execute them."""
    queue_name = settings.worker_queue
    logger.info("Listening on queue: %s", queue_name)

    while True:
        # Blocking pop with 5s timeout (allows periodic heartbeat checks)
        run_id_str = await pop_job(queue_name, timeout=5)

        if run_id_str is None:
            continue  # Timeout — loop back to check cancellation, etc.

        run_id = uuid.UUID(run_id_str)
        logger.info("Received run_id: %s", run_id)

        try:
            await _execute_run(worker_id, run_id)
        except Exception:
            logger.exception("Fatal error processing run %s", run_id)
            await _mark_run_failed(run_id, worker_id, "Internal worker error")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job execution
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _execute_run(worker_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """Full execution pipeline for a single job run."""

    async with async_session_factory() as db:
        async with db.begin():
            # ── Fetch all data ────────────────────────────

            run_result = await db.execute(
                select(JobRun).where(JobRun.id == run_id)
            )
            job_run = run_result.scalars().first()
            if not job_run:
                logger.error("JobRun %s not found", run_id)
                return

            job_result = await db.execute(
                select(Job).where(Job.id == job_run.job_id)
            )
            job = job_result.scalars().first()
            if not job:
                logger.error("Job not found for run %s", run_id)
                return

            # Check cancellation
            if job.status == "cancelled" or job_run.status == "cancelled":
                logger.info("Run %s was cancelled — skipping", run_id)
                return

            input_result = await db.execute(
                select(JobInput).where(JobInput.job_id == job.id)
            )
            job_input = input_result.scalars().first()
            if not job_input:
                logger.error("JobInput not found for job %s", job.id)
                await _mark_run_failed_in_session(
                    db, job, job_run, worker_id, "No job input found"
                )
                return

            # Fetch commands
            cmd_result = await db.execute(
                select(JobCommand)
                .where(JobCommand.job_id == job.id)
                .order_by(JobCommand.step_order.asc())
            )
            commands = cmd_result.scalars().all()

            # Fetch env vars
            env_result = await db.execute(
                select(JobEnvVar).where(JobEnvVar.job_id == job.id)
            )
            env_vars = env_result.scalars().all()

            # Fetch GPU allocations
            gpu_alloc_result = await db.execute(
                select(JobRunGpuAllocation).where(
                    JobRunGpuAllocation.job_run_id == run_id
                )
            )
            gpu_allocations = gpu_alloc_result.scalars().all()

            # Fetch GPU device details
            gpu_devices_info = []
            for alloc in gpu_allocations:
                gpu_dev_result = await db.execute(
                    select(GpuDevice).where(GpuDevice.id == alloc.gpu_device_id)
                )
                gpu_dev = gpu_dev_result.scalars().first()
                if gpu_dev:
                    gpu_devices_info.append(
                        {
                            "gpu_id": str(gpu_dev.id),
                            "gpu_index": gpu_dev.gpu_index,
                            "gpu_model": gpu_dev.gpu_model,
                        }
                    )

            # ── Set running status ────────────────────────

            now = datetime.now(timezone.utc)
            job.status = "running"
            job.started_at = now
            job_run.status = "running"
            job_run.worker_id = worker_id
            job_run.started_at = now

            # Update worker
            worker_result = await db.execute(
                select(Worker).where(Worker.id == worker_id)
            )
            worker = worker_result.scalars().first()
            if worker:
                worker.status = "busy"
                worker.current_job_run_id = run_id

            db.add(
                JobEvent(
                    job_id=job.id,
                    job_run_id=run_id,
                    event_type="run_started",
                    event_message="Worker picked up the job",
                )
            )
            await db.flush()

    # ── Prepare workspace (outside transaction) ───────

    try:
        _insert_event_sync = _make_event_inserter(job.id, run_id)

        job_cfg = job.job_config or {}
        setup_script_name = job_cfg.get("setup_script_name")
        setup_script_storage_path: Optional[str] = None
        if setup_script_name and job_input.uploaded_file_storage_path:
            # Setup script lives alongside the main script in the upload dir
            upload_dir = str(Path(job_input.uploaded_file_storage_path).parent)
            candidate = Path(upload_dir) / setup_script_name
            if candidate.exists():
                setup_script_storage_path = str(candidate)

        ws = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: prepare_workspace(
                run_id,
                job_input.source_type,
                uploaded_file_name=job_input.uploaded_file_name,
                uploaded_file_storage_path=job_input.uploaded_file_storage_path,
                requirements_file_path=job_input.requirements_file_path,
                setup_script_storage_path=setup_script_storage_path,
                setup_script_name=setup_script_name,
                repo_url=job_input.repo_url,
                repo_branch=job_input.repo_branch,
                repo_commit_hash=job_input.repo_commit_hash,
                repo_subdir=job_input.repo_subdir,
                entrypoint=job_input.uploaded_file_storage_path,
            ),
        )

        await _insert_event(
            job.id, run_id, "input_prepared", "Workspace prepared successfully"
        )

    except Exception as e:
        logger.exception("Failed to prepare workspace for run %s", run_id)
        await _mark_run_failed(run_id, worker_id, f"Workspace preparation failed: {e}")
        return

    # ── Snapshot before ───────────────────────────────

    before_snapshot = await asyncio.get_event_loop().run_in_executor(
        None, lambda: snapshot_workspace(ws)
    )

    # ── Build execution command ───────────────────────

    if commands:
        execution_command = commands[0].command_text
    else:
        # Fallback: build from job_input
        execution_command = _build_execution_command(job_input)

    # Build the full command chain: pip install → setup.sh → main script
    # Each step is only added when the file exists in the workspace.
    steps: list[str] = []

    # 1. pip install (if requirements.txt present)
    # Install to /outputs/.pip-user (disk-backed NAS bind mount, NOT tmpfs) so
    # large packages like PyTorch don't consume the container's RAM.
    # PYTHONPATH=/outputs/.pip-user/lib/python3.11/site-packages is injected by
    # docker_runner so Python can find packages at that location.
    pip_prefix = "export PYTHONUSERBASE=/outputs/.pip-user && pip install -q --no-cache-dir --user -r"
    if job_input.source_type == "github_repo" and job_input.requirements_file_path:
        if (ws / job_input.requirements_file_path).exists():
            steps.append(f"{pip_prefix} {job_input.requirements_file_path}")
    elif (ws / "requirements.txt").exists():
        steps.append(f"{pip_prefix} requirements.txt")

    # 2. Setup shell script (python_file mode only)
    if setup_script_name and (ws / setup_script_name).exists():
        steps.append(f"bash {setup_script_name}")

    # 3. Main execution command
    steps.append(execution_command)

    execution_command = " && ".join(steps)

    # Build env vars dict
    env_dict = {ev.var_name: ev.var_value or "" for ev in env_vars}

    # Determine network setting (job_cfg already set above for setup_script_name)
    network_enabled = job_cfg.get("network_enabled", True)

    # ── Execute in Docker ─────────────────────────────

    await _insert_event(job.id, run_id, "container_started", "Starting Docker container")

    run_config = RunConfig(
        run_id=run_id,
        workspace=ws,
        output_dir=nas_output_dir(run_id),
        logs_dir=logs_dir(run_id),
        execution_command=execution_command,
        container_image=job_run.container_image or settings.default_container_image,
        memory_mb=job.requested_memory_mb or 8192,
        cpu_cores=job.requested_cpu_cores or 2,
        env_vars=env_dict,
        gpu_devices=gpu_devices_info,
        network_enabled=network_enabled,
        max_runtime_seconds=job.max_runtime_seconds,
    )

    await _insert_event(
        job.id, run_id, "execution_started", f"Executing: {execution_command}"
    )

    result = await runner.run(run_config)

    await _insert_event(
        job.id,
        run_id,
        "execution_completed",
        f"Exit code: {result.exit_code}, duration: {result.duration_seconds}s",
        {"exit_code": result.exit_code, "timed_out": result.timed_out},
    )

    # ── Snapshot after & collect artifacts ─────────────

    after_snapshot = await asyncio.get_event_loop().run_in_executor(
        None, lambda: snapshot_workspace(ws)
    )

    artifacts = await asyncio.get_event_loop().run_in_executor(
        None, lambda: collect_artifacts(run_id, job.user_id, before_snapshot, after_snapshot, ws)
    )

    # Copy logs to NAS
    log_paths = await asyncio.get_event_loop().run_in_executor(
        None, lambda: copy_logs_to_nas(run_id)
    )

    await _insert_event(
        job.id,
        run_id,
        "artifact_collected",
        f"Collected {len(artifacts)} artifact(s)",
    )

    # ── Update DB with results ────────────────────────

    final_status = "completed" if result.exit_code == 0 else "failed"

    async with async_session_factory() as db:
        async with db.begin():
            now = datetime.now(timezone.utc)

            # Check if job was cancelled
            job_db_result = await db.execute(
                select(Job).where(Job.id == job.id)
            )
            job_db = job_db_result.scalars().first()
            if job_db and job_db.status == "cancelled":
                final_status = "cancelled"

            # Update job_run
            run_result_db = await db.execute(
                select(JobRun).where(JobRun.id == run_id)
            )
            job_run_db = run_result_db.scalars().first()
            if job_run_db:
                if job_run_db.status != "cancelled":
                    job_run_db.status = final_status
                job_run_db.finished_at = now
                job_run_db.exit_code = result.exit_code
                job_run_db.duration_seconds = result.duration_seconds
                job_run_db.container_id = result.container_id
                job_run_db.stdout_log_path = log_paths.get("stdout")
                job_run_db.stderr_log_path = log_paths.get("stderr")
                job_run_db.combined_log_path = log_paths.get("combined")
                job_run_db.nas_output_path = str(nas_output_dir(run_id))
                job_run_db.error_message = result.error_message

            # Update job
            if job_db:
                if job_db.status != "cancelled":
                    job_db.status = final_status
                    job_db.finished_at = now
                    if result.error_message and final_status == "failed":
                        job_db.failure_reason = result.error_message

            # Insert artifacts
            for art in artifacts:
                db.add(
                    JobArtifact(
                        job_run_id=run_id,
                        artifact_type=art["artifact_type"],
                        file_name=art["file_name"],
                        object_key=art["object_key"],
                        file_size_bytes=art["file_size_bytes"],
                        checksum_sha256=art["checksum_sha256"],
                    )
                )

            # Release GPUs
            alloc_result = await db.execute(
                select(JobRunGpuAllocation).where(
                    JobRunGpuAllocation.job_run_id == run_id,
                    JobRunGpuAllocation.released_at.is_(None),
                )
            )
            allocations = alloc_result.scalars().all()
            for alloc in allocations:
                alloc.released_at = now
                gpu_result = await db.execute(
                    select(GpuDevice).where(GpuDevice.id == alloc.gpu_device_id)
                )
                gpu = gpu_result.scalars().first()
                if gpu:
                    gpu.status = "available"
                    gpu.current_job_run_id = None

            # Events
            if allocations:
                db.add(
                    JobEvent(
                        job_id=job.id,
                        job_run_id=run_id,
                        event_type="gpu_released",
                        event_message=f"Released {len(allocations)} GPU(s)",
                    )
                )

            if final_status != "cancelled":
                event_type = "run_completed" if final_status == "completed" else "run_failed"
                db.add(
                    JobEvent(
                        job_id=job.id,
                        job_run_id=run_id,
                        event_type=event_type,
                        event_message=f"Run {final_status} (exit={result.exit_code})",
                    )
                )

            # Reset worker
            worker_result = await db.execute(
                select(Worker).where(Worker.id == worker_id)
            )
            worker = worker_result.scalars().first()
            if worker:
                worker.status = "idle"
                worker.current_job_run_id = None

    logger.info(
        "Run %s finished: status=%s exit=%d duration=%.1fs artifacts=%d",
        run_id,
        final_status,
        result.exit_code,
        result.duration_seconds,
        len(artifacts),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_execution_command(job_input: JobInput) -> str:
    """Build the execution command from the job input."""
    file_path = job_input.uploaded_file_storage_path or job_input.uploaded_file_name or ""

    if job_input.source_type == "python_file":
        # For python_file, execute the file directly
        return f"python {job_input.uploaded_file_name}"

    elif job_input.source_type == "github_repo":
        # For github_repo, use the entrypoint path
        if file_path.endswith(".sh"):
            return f"bash {file_path}"
        elif file_path.endswith(".py"):
            return f"python {file_path}"
        else:
            raise ValueError(f"Unsupported entrypoint extension: {file_path}")

    raise ValueError(f"Unknown source_type: {job_input.source_type}")


async def _insert_event(
    job_id: uuid.UUID,
    run_id: uuid.UUID,
    event_type: str,
    message: str,
    event_data: dict | None = None,
) -> None:
    """Insert a job event in a new short-lived session."""
    async with async_session_factory() as db:
        async with db.begin():
            db.add(
                JobEvent(
                    job_id=job_id,
                    job_run_id=run_id,
                    event_type=event_type,
                    event_message=message,
                    event_data=event_data,
                )
            )


def _make_event_inserter(job_id: uuid.UUID, run_id: uuid.UUID):
    """Create a closure for inserting events for a specific job/run."""

    async def inserter(event_type: str, message: str, data: dict | None = None):
        await _insert_event(job_id, run_id, event_type, message, data)

    return inserter


async def _mark_run_failed(
    run_id: uuid.UUID,
    worker_id: uuid.UUID,
    error_message: str,
) -> None:
    """Mark a run and its parent job as failed."""
    async with async_session_factory() as db:
        async with db.begin():
            now = datetime.now(timezone.utc)

            run_result = await db.execute(
                select(JobRun).where(JobRun.id == run_id)
            )
            job_run = run_result.scalars().first()
            if job_run:
                job_run.status = "failed"
                job_run.finished_at = now
                job_run.error_message = error_message

                job_result = await db.execute(
                    select(Job).where(Job.id == job_run.job_id)
                )
                job = job_result.scalars().first()
                if job:
                    job.status = "failed"
                    job.finished_at = now
                    job.failure_reason = error_message

                # Release GPUs
                alloc_result = await db.execute(
                    select(JobRunGpuAllocation).where(
                        JobRunGpuAllocation.job_run_id == run_id,
                        JobRunGpuAllocation.released_at.is_(None),
                    )
                )
                for alloc in alloc_result.scalars().all():
                    alloc.released_at = now
                    gpu_result = await db.execute(
                        select(GpuDevice).where(GpuDevice.id == alloc.gpu_device_id)
                    )
                    gpu = gpu_result.scalars().first()
                    if gpu:
                        gpu.status = "available"
                        gpu.current_job_run_id = None

                # Events
                db.add(
                    JobEvent(
                        job_id=job_run.job_id,
                        job_run_id=run_id,
                        event_type="run_failed",
                        event_message=error_message,
                    )
                )

            # Reset worker
            worker_result = await db.execute(
                select(Worker).where(Worker.id == worker_id)
            )
            worker = worker_result.scalars().first()
            if worker:
                worker.status = "idle"
                worker.current_job_run_id = None


async def _mark_run_failed_in_session(
    db: AsyncSession,
    job: Job,
    job_run: JobRun,
    worker_id: uuid.UUID,
    error_message: str,
) -> None:
    """Mark a run as failed within an existing session."""
    now = datetime.now(timezone.utc)

    job_run.status = "failed"
    job_run.finished_at = now
    job_run.error_message = error_message

    job.status = "failed"
    job.finished_at = now
    job.failure_reason = error_message

    db.add(
        JobEvent(
            job_id=job.id,
            job_run_id=job_run.id,
            event_type="run_failed",
            event_message=error_message,
        )
    )

    # Reset worker
    worker_result = await db.execute(
        select(Worker).where(Worker.id == worker_id)
    )
    worker = worker_result.scalars().first()
    if worker:
        worker.status = "idle"
        worker.current_job_run_id = None


# ── Entry point for standalone execution ──────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(run_worker())
