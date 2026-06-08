"""SQLAlchemy ORM models mapped exactly to the existing PostgreSQL schema.

These models are READ-ONLY reflections of the existing database tables.
Do NOT use metadata.create_all() — the tables already exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Users & Sessions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class User(Base):
    """Maps to the ``users`` table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    sessions: Mapped[list[UserSession]] = relationship(
        "UserSession", back_populates="user", lazy="selectin"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="user", lazy="selectin"
    )


class UserSession(Base):
    """Maps to the ``user_sessions`` table."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    session_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="sessions")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Jobs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Job(Base):
    """Maps to the ``jobs`` table."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    queue_name: Mapped[str] = mapped_column(String, nullable=False, default="default")
    requested_gpu_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    requested_cpu_cores: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    requested_memory_mb: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    max_runtime_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    working_dir: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    job_config: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latest_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    scheduler_notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="jobs")
    inputs: Mapped[list[JobInput]] = relationship(
        "JobInput", back_populates="job", lazy="selectin"
    )
    commands: Mapped[list[JobCommand]] = relationship(
        "JobCommand", back_populates="job", lazy="selectin"
    )
    env_vars: Mapped[list[JobEnvVar]] = relationship(
        "JobEnvVar", back_populates="job", lazy="selectin"
    )
    runs: Mapped[list[JobRun]] = relationship(
        "JobRun", back_populates="job", lazy="selectin"
    )
    events: Mapped[list[JobEvent]] = relationship(
        "JobEvent", back_populates="job", lazy="selectin"
    )


class JobInput(Base):
    """Maps to the ``job_inputs`` table."""

    __tablename__ = "job_inputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_file_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    uploaded_file_storage_path: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    uploaded_file_sha256: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    repo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    repo_branch: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    repo_commit_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    repo_subdir: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    requirements_file_path: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    environment_file_path: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="inputs")


class JobCommand(Base):
    """Maps to the ``job_commands`` table."""

    __tablename__ = "job_commands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    command_text: Mapped[str] = mapped_column(String, nullable=False)
    run_in_shell: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stop_on_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="commands")


class JobEnvVar(Base):
    """Maps to the ``job_env_vars`` table."""

    __tablename__ = "job_env_vars"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    var_name: Mapped[str] = mapped_column(String, nullable=False)
    var_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="env_vars")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job Runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class JobRun(Base):
    """Maps to the ``job_runs`` table."""

    __tablename__ = "job_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    worker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id"), nullable=True
    )
    node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compute_nodes.id"), nullable=True
    )
    container_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    container_image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stdout_log_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stderr_log_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    combined_log_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    nas_output_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="runs")
    worker: Mapped[Optional[Worker]] = relationship("Worker", back_populates="runs")
    events: Mapped[list[JobEvent]] = relationship(
        "JobEvent", back_populates="job_run", lazy="selectin"
    )
    artifacts: Mapped[list[JobArtifact]] = relationship(
        "JobArtifact", back_populates="job_run", lazy="selectin"
    )
    gpu_allocations: Mapped[list[JobRunGpuAllocation]] = relationship(
        "JobRunGpuAllocation", back_populates="job_run", lazy="selectin"
    )


class JobEvent(Base):
    """Maps to the ``job_events`` table."""

    __tablename__ = "job_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    job_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_runs.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="events")
    job_run: Mapped[Optional[JobRun]] = relationship(
        "JobRun", back_populates="events"
    )


class JobArtifact(Base):
    """Maps to the ``job_artifacts`` table."""

    __tablename__ = "job_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_runs.id"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job_run: Mapped[JobRun] = relationship("JobRun", back_populates="artifacts")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Worker(Base):
    """Maps to the ``workers`` table."""

    __tablename__ = "workers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    worker_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    current_job_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    runs: Mapped[list[JobRun]] = relationship(
        "JobRun", back_populates="worker", lazy="selectin"
    )


class ComputeNode(Base):
    """Maps to the ``compute_nodes`` table."""

    __tablename__ = "compute_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    total_gpus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    gpu_devices: Mapped[list[GpuDevice]] = relationship(
        "GpuDevice", back_populates="node", lazy="selectin"
    )


class GpuDevice(Base):
    """Maps to the ``gpu_devices`` table."""

    __tablename__ = "gpu_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compute_nodes.id"), nullable=False
    )
    gpu_index: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gpu_memory_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="available")
    current_job_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    node: Mapped[ComputeNode] = relationship(
        "ComputeNode", back_populates="gpu_devices"
    )
    allocations: Mapped[list[JobRunGpuAllocation]] = relationship(
        "JobRunGpuAllocation", back_populates="gpu_device", lazy="selectin"
    )


class JobRunGpuAllocation(Base):
    """Maps to the ``job_run_gpu_allocations`` table."""

    __tablename__ = "job_run_gpu_allocations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_runs.id"), nullable=False
    )
    gpu_device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gpu_devices.id"), nullable=False
    )
    allocated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job_run: Mapped[JobRun] = relationship(
        "JobRun", back_populates="gpu_allocations"
    )
    gpu_device: Mapped[GpuDevice] = relationship(
        "GpuDevice", back_populates="allocations"
    )
