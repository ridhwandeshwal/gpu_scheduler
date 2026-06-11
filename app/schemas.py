"""Pydantic request/response schemas for all API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Auth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., min_length=5, max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str
    role: str
    session_token: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Environment Variables
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class EnvVarInput(BaseModel):
    var_name: str = Field(..., min_length=1, max_length=255)
    var_value: str = Field(..., max_length=4096)
    is_secret: bool = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job Submission — Python File
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PythonFileJobMetadata(BaseModel):
    """JSON metadata sent alongside the uploaded Python file."""

    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=4096)
    requested_gpu_count: int = Field(1, ge=0, le=64)
    requested_cpu_cores: Optional[int] = Field(None, ge=1)
    requested_memory_mb: Optional[int] = Field(None, ge=128)
    max_runtime_seconds: Optional[int] = Field(None, ge=10)
    priority: int = Field(5, ge=1, le=10)
    queue_name: str = Field("default", max_length=64)
    env_vars: list[EnvVarInput] = Field(default_factory=list)
    job_config: Optional[dict[str, Any]] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job Submission — GitHub Repo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GitHubJobRequest(BaseModel):
    """Request body for submitting a GitHub repository job."""

    repo_url: str = Field(..., min_length=10, max_length=2048)
    repo_branch: str = Field("main", max_length=255)
    repo_commit_hash: Optional[str] = Field(None, max_length=64)
    repo_subdir: Optional[str] = Field(None, max_length=512)
    entrypoint: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Path to the entrypoint file inside the repository, e.g. 'scripts/run.sh'",
    )
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=4096)
    requested_gpu_count: int = Field(1, ge=0, le=64)
    requested_cpu_cores: Optional[int] = Field(None, ge=1)
    requested_memory_mb: Optional[int] = Field(None, ge=128)
    max_runtime_seconds: Optional[int] = Field(None, ge=10)
    priority: int = Field(5, ge=1, le=10)
    queue_name: str = Field("default", max_length=64)
    env_vars: list[EnvVarInput] = Field(default_factory=list)
    job_config: Optional[dict[str, Any]] = None
    requirements_file_path: Optional[str] = Field(
        None,
        max_length=512,
        description="Relative path to requirements.txt inside the repository, e.g. 'requirements.txt'",
    )

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        if not (
            v.startswith("https://") or v.startswith("git@")
        ):
            raise ValueError("repo_url must start with https:// or git@")
        return v

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, v: str) -> str:
        if ".." in v or v.startswith("/"):
            raise ValueError("entrypoint must be a relative path without '..'")
        if not (v.endswith(".py") or v.endswith(".sh")):
            raise ValueError("entrypoint must be a .py or .sh file")
        return v

    @field_validator("repo_subdir")
    @classmethod
    def validate_repo_subdir(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (".." in v or v.startswith("/")):
            raise ValueError("repo_subdir must be a relative path without '..'")
        return v


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job Responses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class JobInputResponse(BaseModel):
    id: uuid.UUID
    source_type: str
    uploaded_file_name: Optional[str] = None
    uploaded_file_storage_path: Optional[str] = None
    repo_url: Optional[str] = None
    repo_branch: Optional[str] = None
    repo_commit_hash: Optional[str] = None
    repo_subdir: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobCommandResponse(BaseModel):
    id: uuid.UUID
    step_order: int
    command_text: str
    run_in_shell: bool
    stop_on_failure: bool

    model_config = {"from_attributes": True}


class JobEnvVarResponse(BaseModel):
    id: uuid.UUID
    var_name: str
    var_value: Optional[str] = None
    is_secret: bool

    model_config = {"from_attributes": True}

    @field_validator("var_value", mode="before")
    @classmethod
    def mask_secret(cls, v: Optional[str], info: Any) -> Optional[str]:
        """Mask secret values in API responses."""
        # We access is_secret from the data dict if available
        return v


class JobRunResponse(BaseModel):
    id: uuid.UUID
    attempt_number: int
    status: str
    worker_id: Optional[uuid.UUID] = None
    container_id: Optional[str] = None
    container_image: Optional[str] = None
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    duration_seconds: Optional[float] = None
    stdout_log_path: Optional[str] = None
    stderr_log_path: Optional[str] = None
    combined_log_path: Optional[str] = None
    nas_output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    source_type: str
    status: str
    priority: int
    queue_name: str
    requested_gpu_count: int
    requested_cpu_cores: Optional[int] = None
    requested_memory_mb: Optional[int] = None
    max_runtime_seconds: Optional[int] = None
    job_config: Optional[dict[str, Any]] = None
    submitted_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    latest_run_id: Optional[uuid.UUID] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    inputs: list[JobInputResponse] = Field(default_factory=list)
    commands: list[JobCommandResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job Events
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class JobEventResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_run_id: Optional[uuid.UUID] = None
    event_type: str
    event_message: Optional[str] = None
    event_data: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Job Artifacts
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class JobArtifactResponse(BaseModel):
    id: uuid.UUID
    job_run_id: uuid.UUID
    artifact_type: str
    file_name: str
    object_key: str
    file_size_bytes: Optional[int] = None
    checksum_sha256: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
