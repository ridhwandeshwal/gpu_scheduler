# Quda — AIMS-DTU

GPU job scheduler for the lab's shared RTX Titan workstation. Submit Python training scripts or GitHub repos, queue them, track progress, and download artifacts — all from a web UI.

## Architecture

```
NeonDB (PostgreSQL — source of truth)
    ↓
Scheduler  (polls every 2s, allocates GPUs, pushes run IDs to Redis)
    ↓
Redis      (dispatch queue — ephemeral, local only)
    ↓
Worker     (BLPOP, prepares workspace, runs Docker container)
    ↓
Docker     (hardened sandbox — pip install → setup.sh → train.py)
    ↓
/outputs   (bind-mounted host path — artifacts uploaded to MinIO after run)
    ↓
MinIO      (S3-compatible object store — presigned URLs for direct download)
```

## Tech Stack

- **FastAPI** + **SQLAlchemy 2.0 async** (asyncpg) — backend API
- **NeonDB** — serverless hosted Postgres, no local DB needed
- **Redis** — ephemeral dispatch queue (Docker, local only)
- **MinIO** — artifact object storage, S3-compatible, runs locally via Docker
- **Docker** (rootless on shared machines) — sandboxed job execution with GPU passthrough
- **Mantine v7** + **TanStack Query v5** — frontend
- **Pydantic v2**, **Uvicorn**

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (see rootless setup below for shared machines)
- Access to the shared NeonDB project (get `DATABASE_URL` from Shreshth)

### 1. Clone and install

```bash
git clone <repo-url>
cd gpu_scheduler

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Where to get it |
|----------|-----------------|
| `DATABASE_URL` | Get from Shreshth — shared NeonDB connection string |
| `SECRET_KEY` | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `UPLOAD_ROOT` | Local path for uploaded scripts, e.g. `/tmp/quda/uploads` |
| `JOBS_ROOT` | Local path for job workspaces, e.g. `/tmp/quda/jobs` |
| `NAS_ROOT` | Local path for outputs, e.g. `/tmp/quda/nas` |
| `DOCKER_HOST` | See Docker setup below |
| `GPU_MODE` | `nvidia` if you have a GPU + toolkit, `none` for CPU-only |

Everything else can stay as the defaults in `.env.example`.

### 3. Docker setup

**Option A — Personal machine (you are the only user)**

Add yourself to the docker group:
```bash
sudo usermod -aG docker $USER
newgrp docker   # applies immediately without logout
```

**Option B — Shared workstation (no sudo for lab members)**

Install rootless Docker:
```bash
# Install
curl -fsSL https://get.docker.com/rootless | sh

# Add to ~/.bashrc
echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc
echo 'export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock' >> ~/.bashrc
source ~/.bashrc

# Start daemon and keep it alive across SSH sessions
systemctl --user start docker
systemctl --user enable docker
sudo loginctl enable-linger $USER  # survives logout

# GPU passthrough (only if nvidia-container-toolkit is installed on the machine)
nvidia-ctk runtime configure --runtime=docker --config=$HOME/.config/docker/daemon.json
systemctl --user restart docker
```

Then set in `.env`:
```
DOCKER_HOST=unix:///run/user/1000/docker.sock   # replace 1000 with: id -u
GPU_MODE=nvidia
```

Pull the base job image:
```bash
docker pull python:3.11-slim
```

### 4. Start infrastructure (Redis + MinIO)

```bash
docker compose up -d
```

This starts:
- **Redis** on `localhost:6379` — job dispatch queue
- **MinIO** on `localhost:9100` — artifact storage
  - S3 API: `http://localhost:9100`
  - Web console: `http://localhost:9101` (login: `minioadmin` / `minioadmin`)

### 5. Run the database migration

Only needs to be run once (or when the schema changes). It is idempotent — safe to re-run:

```bash
python scripts/migrate_neon.py
```

> **Note:** If this is a fresh setup and the database has never been migrated before, this creates all tables. If you are joining an existing project where another team member already ran this, you can skip it.

### 6. Seed your machine's hardware

Run once to register a compute node and GPU in the database. **Skip this if someone else has already done it for this machine.**

```bash
source .venv/bin/activate
python -c "
import asyncio, uuid
from app.database import async_session_factory
from app.models import ComputeNode, GpuDevice

async def seed():
    async with async_session_factory() as db:
        async with db.begin():
            node = ComputeNode(
                id=uuid.uuid4(), node_name='workstation', hostname='localhost',
                total_gpus=1, total_cpu_cores=8, total_memory_mb=32768, is_active=True,
            )
            db.add(node)
            await db.flush()
            db.add(GpuDevice(
                id=uuid.uuid4(), node_id=node.id, gpu_index=0,
                gpu_model='NVIDIA RTX Titan', gpu_memory_mb=24576, status='available',
            ))
        print('Seeded.')

asyncio.run(seed())
"
```

### 7. Start all processes

Open four terminals, all from the project root with `.venv` activated:

```bash
# Terminal 1 — API server
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Scheduler (moves queued jobs → scheduled, allocates GPUs)
source .venv/bin/activate
python -m app.services.scheduler

# Terminal 3 — Worker (executes jobs in Docker containers)
source .venv/bin/activate
python -m app.services.worker

# Terminal 4 — Frontend
cd frontend && npm run dev
```

Open `http://localhost:5173` in your browser. Register an account and submit a job.

---

## Testing with sample workloads

Two sample workloads are included in `scripts/`:

### MNIST (Python file mode)

1. Go to **My Jobs** → **New Job** → **Python / Shell Script** tab
2. Upload `scripts/sample_python_file.py` as the Python script
3. Create a `requirements.txt` with:
   ```
   torch
   torchvision
   ```
   Upload it as the requirements file
4. Set GPUs to `1` (or `0` for CPU-only)
5. Submit — the job trains a small CNN for 3 epochs and saves a checkpoint to `/outputs`

### CIFAR-10 (GitHub repo mode)

Push the contents of `scripts/sample_github_job/` to a GitHub repo, then:

1. Go to **New Job** → **GitHub Repository** tab
2. Fill in your repo URL, branch `main`, entrypoint `train.py`
3. Set requirements file path to `requirements.txt`
4. Submit

### Viewing artifacts

Go to **Artifacts** in the sidebar. Completed jobs appear as folders — click to expand and download output files.

---

## Job submission reference

### Execution order inside the container

```
1. pip install -q --user -r requirements.txt   (if provided)
2. bash setup.sh                                (if provided)
3. python train.py
```

### Writing scripts

- Write all outputs to `/outputs` — this is the only path that persists after the container exits and gets uploaded to MinIO as artifacts
- `/tmp` and `/home` are writable tmpfs (8GB each) — use for datasets, pip cache, and temporary files
- `/workspace` is **read-only** — your script lives here, do not write to it
- Network is enabled by default — scripts can download datasets from the internet

### File upload (Python file mode)

| Field | Required | Description |
|-------|----------|-------------|
| Python script (`.py`) | Yes | Main training/experiment script |
| Setup script (`.sh`) | No | Runs before the Python script — env setup, data prep, etc. |
| `requirements.txt` | No | Python dependencies installed at container start |

### GitHub repo mode

| Field | Required | Description |
|-------|----------|-------------|
| Repo URL | Yes | `https://github.com/org/repo.git` |
| Branch | No | Defaults to `main` |
| Entrypoint | Yes | Relative path to the script, e.g. `train.py` |
| Requirements file path | No | Relative path to requirements.txt inside the repo |
| Subdirectory | No | If the relevant code is in a subdirectory |
| Commit hash | No | Pin to a specific commit; latest if blank |

---

## Admin

To grant admin access to a user (allows priority override when submitting jobs):

```sql
UPDATE users SET role = 'admin' WHERE email = 'user@example.com';
```

Run this against NeonDB using the connection string in your `.env`.

---

## Project structure

```
app/
├── main.py                   # FastAPI app entry point
├── config.py                 # All settings — configurable via .env
├── database.py               # Async SQLAlchemy engine (NeonDB/asyncpg)
├── models.py                 # ORM models
├── schemas.py                # Pydantic request/response schemas
├── auth.py                   # Session token auth
├── api/
│   ├── auth.py               # /auth endpoints
│   ├── jobs.py               # /jobs endpoints
│   └── admin.py              # /admin endpoints
└── services/
    ├── scheduler.py           # Polls DB, allocates GPUs, pushes to Redis
    ├── worker.py              # BLPOP from Redis, runs Docker containers
    ├── docker_runner.py       # Builds hardened docker run commands
    ├── storage.py             # Workspace prep, repo cloning, artifact upload
    ├── minio_client.py        # MinIO upload + presigned URL generation
    ├── redis_queue.py         # Redis push/pop helpers
    └── seccomp_default.json   # Container syscall allowlist

frontend/src/
├── api/                      # Typed axios API client
├── hooks/                    # TanStack Query hooks (polling, mutations)
├── components/               # JobDetailDrawer, SubmitJobForm, SidebarLogo, etc.
├── pages/                    # JobsPage, ArtifactsPage, AdminPage, LoginPage
└── lib/                      # Auth helpers, formatting utils

scripts/
├── migrate_neon.py           # Idempotent DB schema migration
├── migrate_neon.sql          # Same migration in raw SQL
├── sample_python_file.py     # MNIST smoke test (python-file mode)
└── sample_github_job/        # CIFAR-10 smoke test (github-repo mode)
    ├── train.py
    └── requirements.txt
```

---

## Security model

All user code runs inside hardened Docker containers — no user code ever runs on the host.

| Layer | Control | Purpose |
|-------|---------|---------|
| Identity | `--user 1000:1000` | Non-root execution inside container |
| Capabilities | `--cap-drop=ALL` | Zero Linux capabilities |
| Privileges | `--security-opt=no-new-privileges` | No escalation path |
| Syscalls | Custom seccomp profile | Block dangerous kernel calls |
| Filesystem | `--read-only` + tmpfs | Immutable root, no persistent writes except `/outputs` |
| Resources | `--memory=4096m`, `--cpus=2`, `--pids-limit=512` | Prevent resource exhaustion |
| Logs | `--log-opt max-size=50m` | Prevent log bombs |
| Network | On by default, can disable per-job via `job_config` | Dataset downloads work; can isolate if needed |
| Volumes | Path validation + `:ro` workspace | No host filesystem access beyond explicit mounts |

Credential storage:
- Passwords hashed with **bcrypt**
- Session tokens stored as **SHA-256 hashes** — raw token never written to DB
- Path traversal protection on all uploaded filenames and repo paths
