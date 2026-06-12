"""
Idempotent migration script for local PostgreSQL.

Usage:
    python scripts/migrate.py

Reads DATABASE_URL from .env in the project root.
Requires: asyncpg  (already in requirements.txt / venv)
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

_raw = os.environ.get("DATABASE_URL", "")
if not _raw:
    sys.exit("ERROR: DATABASE_URL is not set in .env or environment.")

_dsn = re.sub(r"^postgresql\+asyncpg://", "postgresql://", _raw)

_STATEMENTS = [
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',

    """
    CREATE TABLE IF NOT EXISTS users (
        id                    UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
        username              VARCHAR(64)  NOT NULL UNIQUE,
        email                 VARCHAR(255) NOT NULL UNIQUE,
        full_name             VARCHAR(255),
        password_hash         VARCHAR(255) NOT NULL,
        role                  VARCHAR(32)  NOT NULL DEFAULT 'user',
        status                VARCHAR(32)  NOT NULL DEFAULT 'active',
        failed_login_attempts INTEGER      NOT NULL DEFAULT 0,
        last_login_at         TIMESTAMPTZ,
        password_changed_at   TIMESTAMPTZ,
        created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at            TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id                 UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id            UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_token_hash VARCHAR(255) NOT NULL,
        ip_address         VARCHAR(64),
        user_agent         VARCHAR(512),
        expires_at         TIMESTAMPTZ  NOT NULL,
        revoked_at         TIMESTAMPTZ,
        created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        last_seen_at       TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(session_token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id    ON user_sessions(user_id)",

    """
    CREATE TABLE IF NOT EXISTS compute_nodes (
        id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        node_name         VARCHAR(128) NOT NULL UNIQUE,
        hostname          VARCHAR(255) NOT NULL,
        total_gpus        INTEGER      NOT NULL DEFAULT 0,
        total_cpu_cores   INTEGER      NOT NULL DEFAULT 0,
        total_memory_mb   INTEGER      NOT NULL DEFAULT 0,
        is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
        last_heartbeat_at TIMESTAMPTZ,
        metadata          JSONB,
        created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at        TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workers (
        id                 UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        worker_name        VARCHAR(128) NOT NULL UNIQUE,
        hostname           VARCHAR(255) NOT NULL,
        status             VARCHAR(32)  NOT NULL DEFAULT 'idle',
        current_job_run_id UUID,
        last_heartbeat_at  TIMESTAMPTZ,
        version            VARCHAR(32),
        metadata           JSONB,
        created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gpu_devices (
        id                 UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        node_id            UUID         NOT NULL REFERENCES compute_nodes(id) ON DELETE CASCADE,
        gpu_index          INTEGER      NOT NULL,
        gpu_model          VARCHAR(128),
        gpu_memory_mb      INTEGER,
        status             VARCHAR(32)  NOT NULL DEFAULT 'available',
        current_job_run_id UUID,
        metadata           JSONB,
        created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gpu_devices_status  ON gpu_devices(status)",
    "CREATE INDEX IF NOT EXISTS idx_gpu_devices_node_id ON gpu_devices(node_id)",

    """
    CREATE TABLE IF NOT EXISTS jobs (
        id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id             UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title               VARCHAR(255),
        description         TEXT,
        source_type         VARCHAR(32)  NOT NULL,
        status              VARCHAR(32)  NOT NULL DEFAULT 'queued',
        priority            INTEGER      NOT NULL DEFAULT 5,
        queue_name          VARCHAR(64)  NOT NULL DEFAULT 'default',
        requested_gpu_count INTEGER      NOT NULL DEFAULT 1,
        requested_cpu_cores INTEGER,
        requested_memory_mb INTEGER,
        max_runtime_seconds INTEGER,
        working_dir         VARCHAR(512),
        entry_type          VARCHAR(32),
        job_config          JSONB,
        submitted_at        TIMESTAMPTZ,
        scheduled_at        TIMESTAMPTZ,
        started_at          TIMESTAMPTZ,
        finished_at         TIMESTAMPTZ,
        latest_run_id       UUID,
        scheduler_notes     TEXT,
        failure_reason      TEXT,
        created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_queue   ON jobs(status, priority, submitted_at)",
    """
    CREATE TABLE IF NOT EXISTS job_inputs (
        id                         UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_id                     UUID          NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        source_type                VARCHAR(32)   NOT NULL,
        uploaded_file_name         VARCHAR(255),
        uploaded_file_storage_path VARCHAR(1024),
        uploaded_file_sha256       VARCHAR(64),
        repo_url                   VARCHAR(2048),
        repo_branch                VARCHAR(255),
        repo_commit_hash           VARCHAR(64),
        repo_subdir                VARCHAR(512),
        requirements_file_path     VARCHAR(512),
        environment_file_path      VARCHAR(512),
        notes                      TEXT,
        created_at                 TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_inputs_job_id ON job_inputs(job_id)",
    """
    CREATE TABLE IF NOT EXISTS job_commands (
        id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        step_order      INTEGER     NOT NULL DEFAULT 0,
        command_text    TEXT        NOT NULL,
        run_in_shell    BOOLEAN     NOT NULL DEFAULT TRUE,
        stop_on_failure BOOLEAN     NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_commands_job_id ON job_commands(job_id)",
    """
    CREATE TABLE IF NOT EXISTS job_env_vars (
        id         UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_id     UUID         NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        var_name   VARCHAR(255) NOT NULL,
        var_value  TEXT,
        is_secret  BOOLEAN      NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_env_vars_job_id ON job_env_vars(job_id)",

    """
    CREATE TABLE IF NOT EXISTS job_runs (
        id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_id            UUID         NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        attempt_number    INTEGER      NOT NULL DEFAULT 1,
        status            VARCHAR(32)  NOT NULL DEFAULT 'scheduled',
        worker_id         UUID         REFERENCES workers(id),
        node_id           UUID         REFERENCES compute_nodes(id),
        container_id      VARCHAR(128),
        container_image   VARCHAR(512),
        assigned_at       TIMESTAMPTZ,
        started_at        TIMESTAMPTZ,
        finished_at       TIMESTAMPTZ,
        exit_code         INTEGER,
        duration_seconds  DOUBLE PRECISION,
        stdout_log_path   VARCHAR(1024),
        stderr_log_path   VARCHAR(1024),
        combined_log_path VARCHAR(1024),
        nas_output_path   VARCHAR(1024),
        error_message     TEXT,
        created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_runs_status ON job_runs(status)",

    """
    CREATE TABLE IF NOT EXISTS job_events (
        id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_id        UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        job_run_id    UUID        REFERENCES job_runs(id) ON DELETE SET NULL,
        event_type    VARCHAR(64) NOT NULL,
        event_message TEXT,
        event_data    JSONB,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_type   ON job_events(event_type)",

    """
    CREATE TABLE IF NOT EXISTS job_artifacts (
        id              UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_run_id      UUID          NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
        artifact_type   VARCHAR(64)   NOT NULL,
        file_name       VARCHAR(255)  NOT NULL,
        object_key      VARCHAR(1024) NOT NULL,
        file_size_bytes BIGINT,
        checksum_sha256 VARCHAR(64),
        metadata        JSONB,
        created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_artifacts_run_id ON job_artifacts(job_run_id)",

    """
    CREATE TABLE IF NOT EXISTS job_run_gpu_allocations (
        id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_run_id    UUID        NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
        gpu_device_id UUID        NOT NULL REFERENCES gpu_devices(id) ON DELETE CASCADE,
        allocated_at  TIMESTAMPTZ,
        released_at   TIMESTAMPTZ,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gpu_alloc_run_id ON job_run_gpu_allocations(job_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_gpu_alloc_gpu_id ON job_run_gpu_allocations(gpu_device_id)",
]


async def migrate() -> None:
    try:
        import asyncpg
    except ImportError:
        sys.exit("ERROR: asyncpg not installed. Run: pip install asyncpg")

    print(f"Connecting to: {re.sub(r':([^:@]+)@', ':***@', _dsn)}")
    conn = await asyncpg.connect(_dsn)

    try:
        for stmt in _STATEMENTS:
            stmt = stmt.strip()
            label = stmt.split("\n")[0][:72]
            await conn.execute(stmt)
            print(f"  ok  {label}")
    finally:
        await conn.close()

    print("\nMigration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
