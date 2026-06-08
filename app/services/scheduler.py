"""Scheduler service — polls for queued jobs and dispatches them to workers.

Runs as an async loop every SCHEDULER_INTERVAL_SECONDS:
  1. Find queued jobs ordered by priority ASC, submitted_at ASC.
  2. Check available GPUs with row-level locking.
  3. Allocate GPUs, create job_runs, push to Redis queue.
  4. All changes are atomic within a single transaction.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

# pyrefly: ignore [missing-import]
from sqlalchemy import select, update
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models import (
    GpuDevice,
    Job,
    JobEvent,
    JobRun,
    JobRunGpuAllocation,
)
from app.services.redis_queue import push_job

logger = logging.getLogger("scheduler")
settings = get_settings()


async def run_scheduler() -> None:
    """Main scheduler loop — runs indefinitely."""
    logger.info(
        "Scheduler started (interval=%ds)", settings.scheduler_interval_seconds
    )

    while True:
        try:
            await _schedule_tick()
        except Exception:
            logger.exception("Scheduler tick failed")

        await asyncio.sleep(settings.scheduler_interval_seconds)


async def _schedule_tick() -> None:
    """Single scheduling pass — find queued jobs and allocate GPUs."""

    dispatched_runs = []

    async with async_session_factory() as db:
        async with db.begin():
            # 1. Find all queued jobs, ordered by priority then submission time.
            #    FOR UPDATE SKIP LOCKED prevents double-scheduling by concurrent
            #    scheduler instances.
            result = await db.execute(
                select(Job)
                .where(Job.status == "queued")
                .order_by(Job.priority.asc(), Job.submitted_at.asc())
                .with_for_update(skip_locked=True)
            )
            queued_jobs = result.scalars().all()

            if not queued_jobs:
                return

            for job in queued_jobs:
                scheduled = await _try_schedule_job(db, job)
                if scheduled:
                    dispatched_runs.append(scheduled)
                    logger.info("Scheduled job %s → run dispatched", job.id)
                else:
                    logger.debug(
                        "Job %s needs %d GPUs — not enough available",
                        job.id,
                        job.requested_gpu_count,
                    )

    # Push to Redis after the database transaction commits to avoid race conditions
    for queue_name, run_id in dispatched_runs:
        await push_job(queue_name, run_id)


async def _try_schedule_job(db: AsyncSession, job: Job) -> tuple[str, uuid.UUID] | None:
    """Attempt to schedule a single job by allocating GPUs.

    Returns (queue_name, run_id) if the job was successfully scheduled, None if not enough
    GPUs are available.
    """
    gpu_count = job.requested_gpu_count or 0

    # If job requires 0 GPUs, schedule immediately
    if gpu_count == 0:
        return await _create_run_and_dispatch(db, job, [])

    # 2. Find available GPUs with row locking
    gpu_result = await db.execute(
        select(GpuDevice)
        .where(GpuDevice.status == "available")
        .with_for_update(skip_locked=True)
        .limit(gpu_count)
    )
    available_gpus = gpu_result.scalars().all()

    if len(available_gpus) < gpu_count:
        return None  # Not enough GPUs

    return await _create_run_and_dispatch(db, job, available_gpus)


async def _create_run_and_dispatch(
    db: AsyncSession,
    job: Job,
    gpus: list[GpuDevice],
) -> tuple[str, uuid.UUID]:
    """Create a job_run, allocate GPUs, update statuses, and push to Redis.

    All mutations happen within the caller's transaction.
    Returns (queue_name, run_id) to be pushed to Redis after commit.
    """
    now = datetime.now(timezone.utc)

    # Determine attempt number
    from sqlalchemy import func as sa_func

    count_result = await db.execute(
        select(sa_func.count(JobRun.id)).where(JobRun.job_id == job.id)
    )
    attempt = (count_result.scalar() or 0) + 1

    # 3a. Create job_run
    job_run = JobRun(
        job_id=job.id,
        attempt_number=attempt,
        status="scheduled",
        container_image=settings.default_container_image,
        assigned_at=now,
    )
    db.add(job_run)
    await db.flush()  # Populate job_run.id

    # 3b. Allocate GPUs
    for gpu in gpus:
        allocation = JobRunGpuAllocation(
            job_run_id=job_run.id,
            gpu_device_id=gpu.id,
            allocated_at=now,
        )
        db.add(allocation)

        # Mark GPU as allocated
        gpu.status = "allocated"
        gpu.current_job_run_id = job_run.id

    # 3c. Update job status
    job.status = "scheduled"
    job.scheduled_at = now
    job.latest_run_id = job_run.id

    # 3d. Insert events
    db.add(
        JobEvent(
            job_id=job.id,
            job_run_id=job_run.id,
            event_type="job_scheduled",
            event_message=f"Job scheduled (attempt {attempt})",
        )
    )

    if gpus:
        gpu_info = [
            {"gpu_id": str(g.id), "gpu_index": g.gpu_index, "gpu_model": g.gpu_model}
            for g in gpus
        ]
        db.add(
            JobEvent(
                job_id=job.id,
                job_run_id=job_run.id,
                event_type="gpu_allocated",
                event_message=f"Allocated {len(gpus)} GPU(s)",
                event_data={"gpus": gpu_info},
            )
        )

    await db.flush()

    # 3e. Determine queue name
    queue_name = job.queue_name or settings.default_queue_name

    return queue_name, job_run.id


# ── Entry point for standalone execution ──────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(run_scheduler())
