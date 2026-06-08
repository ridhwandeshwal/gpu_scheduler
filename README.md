# GPU Job Scheduler

Backend execution layer for scheduling and running GPU-accelerated jobs in hardened Docker containers.

## Architecture

```
PostgreSQL (source of truth)
    ↓
Scheduler (polls every 2s)
    ↓
Redis Queue (dispatch only)
    ↓
Worker (picks up runs)
    ↓
Docker (hardened sandboxed execution)
    ↓
NAS (outputs + logs + artifacts)
```

## Tech Stack

- **Python 3.11+**
- **FastAPI** — async HTTP API
- **SQLAlchemy 2.0** — async ORM (asyncpg driver)
- **PostgreSQL** — single source of truth
- **Redis** — dispatch queues, heartbeats, locks (ephemeral only)
- **Docker** — hardened container execution (with NVIDIA Container Toolkit for GPUs)
- **Pydantic v2** — request/response validation
- **Uvicorn** — ASGI server

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your database, Redis, and storage paths
```

### 3. Start the API server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start the scheduler

```bash
python -m app.services.scheduler
```

### 5. Start a worker

```bash
python -m app.services.worker
```

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login and receive session token |
| POST | `/auth/logout` | Revoke current session |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs/python-file` | Submit a standalone Python file |
| POST | `/jobs/github` | Submit a GitHub repository job |
| GET | `/jobs` | List jobs (paginated) |
| GET | `/jobs/{id}` | Get job details |
| GET | `/jobs/{id}/events` | List job events |
| GET | `/jobs/{id}/artifacts` | List job artifacts |
| POST | `/jobs/{id}/cancel` | Cancel a job |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

## Job Submission Modes

### Mode 1: Standalone Python File

Upload a `.py` file via multipart form:

```bash
curl -X POST http://localhost:8000/jobs/python-file \
  -H "Authorization: Bearer <token>" \
  -F "file=@train.py" \
  -F 'metadata={"title": "Training Job", "requested_gpu_count": 1}'
```

### Mode 2: GitHub Repository

Submit a JSON body with repo details:

```bash
curl -X POST http://localhost:8000/jobs/github \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/user/project.git",
    "repo_branch": "main",
    "entrypoint": "scripts/run.sh",
    "title": "Training from repo",
    "requested_gpu_count": 2
  }'
```

## Project Structure

```
app/
├── main.py                   # FastAPI application entry
├── config.py                 # Pydantic settings
├── database.py               # Async SQLAlchemy engine
├── models.py                 # ORM models (13 tables)
├── schemas.py                # Pydantic request/response
├── auth.py                   # Auth utilities
├── api/
│   ├── auth.py               # Auth endpoints
│   └── jobs.py               # Job endpoints
└── services/
    ├── scheduler.py           # Job scheduling loop
    ├── worker.py              # Job execution worker
    ├── docker_runner.py       # Docker container runner
    ├── seccomp_default.json   # Container seccomp profile
    ├── storage.py             # File/workspace operations
    └── redis_queue.py         # Redis queue operations
```

## Security

Since Docker runs with root-level access, this project implements defense-in-depth
hardening for all user code execution:

| Layer | Control | Purpose |
|-------|---------|---------|
| Process | `--user 1000:1000` | Non-root execution inside containers |
| Capabilities | `--cap-drop=ALL` | Zero Linux capabilities |
| Privileges | `--security-opt=no-new-privileges` | Prevent privilege escalation |
| Syscalls | Custom seccomp profile | Block dangerous kernel calls |
| Filesystem | `--read-only` + tmpfs | Immutable root filesystem |
| Resources | `--memory`, `--cpus`, `--pids-limit` | Prevent resource exhaustion |
| Logs | `--log-opt max-size` | Prevent log bombs |
| Network | `--network=none` (configurable) | Network isolation |
| Volumes | Path validation + `:ro` workspace | Prevent host access |
| File descriptors | `--ulimit nofile/nproc` | Prevent FD exhaustion |

Additional security measures:
- **bcrypt** password hashing
- **SHA-256** session token hashing (raw tokens never stored)
- **Path traversal** protection on all file inputs
- **Environment variable sanitization** (reject unsafe names)
- **Container naming** (`gpu-job-{run_id}`) for easy audit and cleanup
- **Force-remove** fallback on container stop failures

## Environment Variables

See [.env.example](.env.example) for all configurable values.
