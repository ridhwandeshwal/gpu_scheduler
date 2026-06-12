"""Job management API endpoints: submit, list, get, cancel."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import (
    Job,
    JobCommand,
    JobEnvVar,
    JobEvent,
    JobInput,
    JobRun,
    JobRunGpuAllocation,
    GpuDevice,
    User,
)
from app.schemas import (
    GitHubJobRequest,
    JobArtifactResponse,
    JobEventResponse,
    JobListResponse,
    JobResponse,
    MessageResponse,
    PythonFileJobMetadata,
)

router = APIRouter()
settings = get_settings()

# ── Validation helpers ────────────────────────────────────

_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-][a-zA-Z0-9_\-. ]*$")


def _validate_filename(name: str) -> str:
    """Reject path traversal and unsafe characters in uploaded file names."""
    if not name:
        raise HTTPException(status_code=400, detail="Empty file name")
    basename = os.path.basename(name)
    if basename != name:
        raise HTTPException(status_code=400, detail="File name contains path separators")
    if ".." in name:
        raise HTTPException(status_code=400, detail="File name contains '..'")
    if not _SAFE_FILENAME_RE.match(name):
        raise HTTPException(status_code=400, detail="File name contains invalid characters")
    return basename


def _determine_command(file_path: str) -> str:
    """Determine the execution command based on file extension."""
    if file_path.endswith(".py"):
        return f"python {file_path}"
    elif file_path.endswith(".sh"):
        return f"bash {file_path}"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {file_path}. Only .py and .sh are allowed.",
        )


def _entrypoint_to_module(entrypoint: str) -> str:
    """Convert a file-path-style entrypoint to a Python module path.

    Examples:
        'package/sub/train.py'  -> 'package.sub.train'
        'train.py'              -> 'train'
        'package.sub.train'     -> 'package.sub.train'  (already module notation)
    """
    if "/" not in entrypoint and "\\" not in entrypoint:
        # Already module notation (or bare name) — strip .py if present
        return entrypoint.removesuffix(".py")
    return entrypoint.replace("\\", "/").replace("/", ".").removesuffix(".py")


def _compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of file content."""
    return hashlib.sha256(data).hexdigest()


async def _insert_event(
    db: AsyncSession,
    job_id: uuid_mod.UUID,
    event_type: str,
    message: str | None = None,
    event_data: dict | None = None,
    job_run_id: uuid_mod.UUID | None = None,
) -> None:
    """Insert a job event row."""
    event = JobEvent(
        job_id=job_id,
        job_run_id=job_run_id,
        event_type=event_type,
        event_message=message,
        event_data=event_data,
    )
    db.add(event)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /jobs/python-file
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post(
    "/python-file",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a Python file job with optional shell setup script",
)
async def submit_python_file_job(
    file: UploadFile = File(..., description="The .py script to execute"),
    setup_script: Optional[UploadFile] = File(None, description="Optional .sh script run before the Python file"),
    requirements_file: Optional[UploadFile] = File(None, description="Optional requirements.txt"),
    metadata: str = Form(
        ..., description="JSON string of PythonFileJobMetadata"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    """Upload a Python script (+ optional shell setup script) and create a queued job.

    Execution order inside the container:
      1. pip install -r requirements.txt  (if provided)
      2. bash setup.sh                    (if provided)
      3. python <script>.py
    """

    # Parse metadata
    try:
        meta = PythonFileJobMetadata.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metadata JSON: {e}",
        )

    # Validate main script — must be .py
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    filename = _validate_filename(file.filename)
    if not filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Main script must be a .py file")

    # Read main script
    file_content = await file.read()
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    file_sha256 = _compute_sha256(file_content)

    # Generate job ID and save files
    job_id = uuid_mod.uuid4()
    upload_dir = Path(settings.upload_root) / str(job_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    file_path.write_bytes(file_content)
    storage_path = str(file_path)

    # Handle optional setup shell script
    setup_script_storage_path: Optional[str] = None
    setup_script_name: Optional[str] = None
    if setup_script and setup_script.filename:
        sh_filename = _validate_filename(setup_script.filename)
        if not sh_filename.endswith(".sh"):
            raise HTTPException(status_code=400, detail="Setup script must be a .sh file")
        sh_content = await setup_script.read()
        if sh_content:
            sh_path = upload_dir / sh_filename
            sh_path.write_bytes(sh_content)
            setup_script_storage_path = str(sh_path)
            setup_script_name = sh_filename

    # Handle optional requirements.txt
    req_storage_path: Optional[str] = None
    if requirements_file and requirements_file.filename:
        req_filename = _validate_filename(requirements_file.filename)
        if req_filename != "requirements.txt":
            raise HTTPException(status_code=400, detail="Requirements file must be named requirements.txt")
        req_content = await requirements_file.read()
        if req_content:
            req_path = upload_dir / "requirements.txt"
            req_path.write_bytes(req_content)
            req_storage_path = str(req_path)

    now = datetime.now(timezone.utc)

    # Create job
    job = Job(
        id=job_id,
        user_id=current_user.id,
        title=meta.title,
        description=meta.description,
        source_type="python_file",
        status="queued",
        priority=meta.priority if current_user.role == "admin" else 5,
        queue_name=meta.queue_name,
        requested_gpu_count=meta.requested_gpu_count,
        requested_cpu_cores=meta.requested_cpu_cores,
        requested_memory_mb=meta.requested_memory_mb,
        max_runtime_seconds=meta.max_runtime_seconds,
        entry_type="python_file",
        job_config=meta.job_config,
        submitted_at=now,
    )
    db.add(job)

    # Store setup script name in job_config so the worker can find it
    if setup_script_name:
        job.job_config = {**(meta.job_config or {}), "setup_script_name": setup_script_name}

    # Create job input
    job_input = JobInput(
        job_id=job_id,
        source_type="python_file",
        uploaded_file_name=filename,
        uploaded_file_storage_path=storage_path,
        uploaded_file_sha256=file_sha256,
        requirements_file_path=req_storage_path,
    )
    db.add(job_input)

    # Command is just the python script — worker prepends pip install and bash setup
    command = JobCommand(
        job_id=job_id,
        step_order=0,
        command_text=f"python {filename}",
        run_in_shell=True,
        stop_on_failure=True,
    )
    db.add(command)

    # Create env vars
    for ev in meta.env_vars:
        env_var = JobEnvVar(
            job_id=job_id,
            var_name=ev.var_name,
            var_value=ev.var_value,
            is_secret=ev.is_secret,
        )
        db.add(env_var)

    # Insert events
    await _insert_event(db, job_id, "job_submitted", "Job submitted via python-file upload")
    await _insert_event(db, job_id, "job_queued", "Job queued for scheduling")

    await db.flush()

    # Re-fetch with relationships
    result = await db.execute(select(Job).where(Job.id == job_id))
    created_job = result.scalars().first()

    return JobResponse.model_validate(created_job)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /jobs/github
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post(
    "/github",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a GitHub repository job",
)
async def submit_github_job(
    body: GitHubJobRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    """Create a queued job from a GitHub repository and entrypoint."""

    entrypoint = body.entrypoint
    basename = os.path.basename(entrypoint)

    # Determine execution command
    if body.run_as_module:
        command_text = f"python -m {_entrypoint_to_module(entrypoint)}"
    else:
        command_text = _determine_command(entrypoint)

    job_id = uuid_mod.uuid4()
    now = datetime.now(timezone.utc)

    # Create job
    job = Job(
        id=job_id,
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        source_type="github_repo",
        status="queued",
        priority=body.priority if current_user.role == "admin" else 5,
        queue_name=body.queue_name,
        requested_gpu_count=body.requested_gpu_count,
        requested_cpu_cores=body.requested_cpu_cores,
        requested_memory_mb=body.requested_memory_mb,
        max_runtime_seconds=body.max_runtime_seconds,
        entry_type="github_repo",
        job_config={**(body.job_config or {}), "run_as_module": body.run_as_module},
        submitted_at=now,
    )
    db.add(job)

    # Create job input
    job_input = JobInput(
        job_id=job_id,
        source_type="github_repo",
        uploaded_file_name=basename,
        uploaded_file_storage_path=entrypoint,  # Relative path inside repo
        repo_url=body.repo_url,
        repo_branch=body.repo_branch,
        repo_commit_hash=body.repo_commit_hash,
        repo_subdir=body.repo_subdir,
        requirements_file_path=body.requirements_file_path or None,
    )
    db.add(job_input)

    # Create job command
    command = JobCommand(
        job_id=job_id,
        step_order=0,
        command_text=command_text,
        run_in_shell=True,
        stop_on_failure=True,
    )
    db.add(command)

    # Create env vars
    for ev in body.env_vars:
        env_var = JobEnvVar(
            job_id=job_id,
            var_name=ev.var_name,
            var_value=ev.var_value,
            is_secret=ev.is_secret,
        )
        db.add(env_var)

    # Insert events
    await _insert_event(db, job_id, "job_submitted", "Job submitted via GitHub repository")
    await _insert_event(db, job_id, "job_queued", "Job queued for scheduling")

    await db.flush()

    # Re-fetch with relationships
    result = await db.execute(select(Job).where(Job.id == job_id))
    created_job = result.scalars().first()

    return JobResponse.model_validate(created_job)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /jobs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get(
    "",
    response_model=JobListResponse,
    summary="List jobs for the current user",
)
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobListResponse:
    """Return a paginated list of jobs owned by the authenticated user."""

    query = select(Job).where(Job.user_id == current_user.id)
    count_query = select(func.count(Job.id)).where(Job.user_id == current_user.id)

    if status_filter:
        query = query.where(Job.status == status_filter)
        count_query = count_query.where(Job.status == status_filter)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated results
    offset = (max(page, 1) - 1) * page_size
    query = query.order_by(Job.submitted_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /jobs/{job_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job details",
)
async def get_job(
    job_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    """Return full details of a specific job."""

    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /jobs/{job_id}/events
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get(
    "/{job_id}/events",
    response_model=list[JobEventResponse],
    summary="List events for a job",
)
async def list_job_events(
    job_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobEventResponse]:
    """Return all events for a specific job, ordered chronologically."""

    # Verify ownership
    job_result = await db.execute(
        select(Job.id).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if job_result.scalars().first() is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(JobEvent)
        .where(JobEvent.job_id == job_id)
        .order_by(JobEvent.created_at.asc())
    )
    events = result.scalars().all()
    return [JobEventResponse.model_validate(e) for e in events]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /jobs/{job_id}/artifacts
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get(
    "/{job_id}/artifacts",
    response_model=list[JobArtifactResponse],
    summary="List artifacts for a job",
)
async def list_job_artifacts(
    job_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobArtifactResponse]:
    """Return all artifacts from the latest run of a job."""

    # Verify ownership and get latest_run_id
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.latest_run_id is None:
        return []

    from app.models import JobArtifact
    from app.services.minio_client import presign_download

    result = await db.execute(
        select(JobArtifact)
        .where(JobArtifact.job_run_id == job.latest_run_id)
        .order_by(JobArtifact.created_at.asc())
    )
    artifacts = result.scalars().all()

    responses = []
    for a in artifacts:
        try:
            url = presign_download(a.object_key, expires_in=900)
        except Exception:
            url = None
        responses.append(JobArtifactResponse(
            id=a.id,
            job_run_id=a.job_run_id,
            artifact_type=a.artifact_type,
            file_name=a.file_name,
            object_key=a.object_key,
            file_size_bytes=a.file_size_bytes,
            checksum_sha256=a.checksum_sha256,
            created_at=a.created_at,
            download_url=url,
        ))
    return responses


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /jobs/{job_id}/cancel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post(
    "/{job_id}/cancel",
    response_model=MessageResponse,
    summary="Cancel a job",
)
async def cancel_job(
    job_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Cancel a queued, scheduled, or running job."""

    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now(timezone.utc)

    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = now
        await _insert_event(db, job_id, "job_cancelled", "Job cancelled while queued")
        await db.flush()
        return MessageResponse(message="Job cancelled")

    elif job.status == "scheduled":
        job.status = "cancelled"
        job.finished_at = now

        # Cancel the run and release GPUs
        if job.latest_run_id:
            await _cancel_run_and_release_gpus(db, job.latest_run_id, now)

        await _insert_event(db, job_id, "job_cancelled", "Job cancelled while scheduled")
        await db.flush()
        return MessageResponse(message="Job cancelled")

    elif job.status == "running":
        job.status = "cancelled"
        job.finished_at = now

        # Cancel the run and release GPUs
        if job.latest_run_id:
            await _cancel_run_and_release_gpus(db, job.latest_run_id, now)

        await _insert_event(db, job_id, "job_cancelled", "Job cancelled while running")
        await db.flush()

        # Attempt container stop (best-effort, non-blocking)
        if job.latest_run_id:
            import asyncio
            container_name = f"gpu-job-{job.latest_run_id}"
            asyncio.create_task(_stop_container(container_name))

        return MessageResponse(message="Job cancellation initiated")

    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel job in '{job.status}' status",
        )


async def _cancel_run_and_release_gpus(
    db: AsyncSession,
    run_id: uuid_mod.UUID,
    now: datetime,
) -> None:
    """Mark a run as cancelled and release its GPU allocations."""

    # Update run
    run_result = await db.execute(select(JobRun).where(JobRun.id == run_id))
    run = run_result.scalars().first()
    if run and run.status not in ("completed", "failed", "cancelled"):
        run.status = "cancelled"
        run.finished_at = now

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

        # Mark GPU as available
        gpu_result = await db.execute(
            select(GpuDevice).where(GpuDevice.id == alloc.gpu_device_id)
        )
        gpu = gpu_result.scalars().first()
        if gpu:
            gpu.status = "available"
            gpu.current_job_run_id = None


async def _stop_container(container_id: str) -> None:
    """Best-effort attempt to stop a Docker container."""
    import asyncio

    from app.config import get_settings
    _settings = get_settings()
    runtime = _settings.container_runtime

    try:
        process = await asyncio.create_subprocess_exec(
            runtime, "stop", "-t", "10", container_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=30)
    except Exception:
        pass  # Best-effort — container may already be gone

    # Force-remove as fallback
    try:
        process = await asyncio.create_subprocess_exec(
            runtime, "rm", "-f", container_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=15)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /jobs/{job_id}/artifacts/{artifact_id}/download
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{job_id}/artifacts/{artifact_id}/download",
    summary="Get a presigned download URL for an artifact",
)
async def download_job_artifact(
    job_id: uuid_mod.UUID,
    artifact_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a presigned MinIO URL for direct browser download (valid 15 min)."""
    from fastapi.responses import RedirectResponse
    from app.models import JobArtifact
    from app.services.minio_client import presign_download

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    art_result = await db.execute(select(JobArtifact).where(JobArtifact.id == artifact_id))
    artifact = art_result.scalars().first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    url = presign_download(artifact.object_key)
    return RedirectResponse(url=url, status_code=302)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /jobs/{job_id}/logs/{log_type}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{job_id}/logs/{log_type}",
    summary="Download or view job logs",
)
async def download_job_logs(
    job_id: uuid_mod.UUID,
    log_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download stdout, stderr, or combined logs for the latest run of a job."""
    if log_type not in ("stdout", "stderr", "combined"):
        raise HTTPException(status_code=400, detail="Invalid log type. Choose stdout, stderr, or combined")

    # 1. Fetch job to verify ownership or admin rights
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to access this job's logs")

    if job.latest_run_id is None:
        raise HTTPException(status_code=404, detail="No run has been scheduled for this job yet")

    # 2. Fetch latest run
    run_result = await db.execute(select(JobRun).where(JobRun.id == job.latest_run_id))
    run = run_result.scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="Job run not found")

    # Get log path based on type (fallback to local job workspace log path if DB entry is not yet populated)
    if log_type == "stdout":
        log_path_str = run.stdout_log_path or str(Path(settings.jobs_root) / str(job.latest_run_id) / "logs" / "stdout.log")
    elif log_type == "stderr":
        log_path_str = run.stderr_log_path or str(Path(settings.jobs_root) / str(job.latest_run_id) / "logs" / "stderr.log")
    else:
        log_path_str = run.combined_log_path or str(Path(settings.jobs_root) / str(job.latest_run_id) / "logs" / "combined.log")

    if not log_path_str:
        raise HTTPException(status_code=404, detail=f"Log file path for {log_type} is empty")

    log_path = Path(log_path_str)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Physical log file not found at {log_path_str}")

    return FileResponse(
        path=str(log_path),
        filename=f"job_{job_id}_{log_type}.log",
        media_type="text/plain",
    )
