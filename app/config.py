"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the GPU Job Scheduler."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://gpu_scheduler:gpu_scheduler@localhost:5432/gpu_scheduler"

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Security ──────────────────────────────────────────
    secret_key: str = "change-me-to-a-random-64-char-string"
    session_expiry_hours: int = 72

    # ── Storage Paths ─────────────────────────────────────
    upload_root: str = "/gpu_scheduler/uploads"
    jobs_root: str = "/gpu_scheduler/jobs"
    nas_root: str = "/mnt/nas/gpu_scheduler"

    # ── Container Runtime ─────────────────────────────────
    container_runtime: str = "docker"
    default_container_image: str = "gpu-scheduler-python-gpu:latest"
    gpu_mode: str = "none"  # none | nvidia

    # ── Container Security ────────────────────────────────
    container_user: str = "1000:1000"
    container_read_only: bool = True
    container_tmpfs_size_mb: int = 512
    container_log_max_size: str = "50m"
    container_disk_quota: str = "10G"

    # ── Scheduler ─────────────────────────────────────────
    scheduler_interval_seconds: int = 2
    default_queue_name: str = "default"

    # ── Worker ────────────────────────────────────────────
    worker_name: str = "worker-01"
    worker_queue: str = "default"
    worker_heartbeat_interval: int = 10


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
