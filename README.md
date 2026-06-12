# Quda AIMS-DTU

GPU job scheduler for the lab's shared RTX Titan workstation. Submit Python training scripts or GitHub repos, queue them, track progress, and download artifacts — all from a web UI.

## Architecture

```
PostgreSQL (source of truth, self-hosted via Docker)
    |
Scheduler  (polls every 2s, allocates GPUs, pushes run IDs to Redis)
    |
Redis      (ephemeral dispatch queue)
    |
Worker     (BLPOP, prepares workspace, runs Docker container)
    |
Docker     (hardened sandbox - pip install -> setup.sh -> train.py)
    |
/outputs   (bind-mounted host path - artifacts uploaded to MinIO after run)
    |
MinIO      (S3-compatible object store - presigned URLs for direct download)
```

## Tech Stack

- **FastAPI** + **SQLAlchemy 2.0 async** (asyncpg) - backend API
- **PostgreSQL 16** (self-hosted, Docker) - database
- **Redis** - ephemeral dispatch queue (Docker)
- **MinIO** - artifact object storage, S3-compatible (Docker)
- **Docker** (rootless on shared machines) - sandboxed job execution with GPU passthrough
- **Mantine v9** + **TanStack Query v5** - frontend
- **Pydantic v2**, **Uvicorn**

---

## Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker

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

Fill in:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://gpu_scheduler:gpu_scheduler@localhost:5432/gpu_scheduler` (matches docker-compose defaults) |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `MINIO_ACCESS_KEY` | pick any username |
| `MINIO_SECRET_KEY` | pick a strong password (min 8 chars) |
| `UPLOAD_ROOT` | e.g. `/tmp/quda/uploads` |
| `JOBS_ROOT` | e.g. `/tmp/quda/jobs` |
| `NAS_ROOT` | e.g. `/tmp/quda/nas` |
| `GPU_MODE` | `nvidia` with RTX Titan, `none` for CPU-only |

### 3. Docker (rootless, for shared workstation)

```bash
curl -fsSL https://get.docker.com/rootless | sh

echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc
echo 'export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock' >> ~/.bashrc
source ~/.bashrc

systemctl --user start docker
systemctl --user enable docker
sudo loginctl enable-linger $USER

nvidia-ctk runtime configure --runtime=docker --config=$HOME/.config/docker/daemon.json
systemctl --user restart docker
```

Set in `.env`:
```
DOCKER_HOST=unix:///run/user/1000/docker.sock   # replace 1000 with: id -u
GPU_MODE=nvidia
```

### 4. Start infrastructure

```bash
docker compose up -d   # starts Postgres, Redis, MinIO
```

### 5. Run the DB migration

```bash
python scripts/migrate.py
```

### 6. Seed hardware

Run once to register the workstation's GPU:

```bash
python -c "
import asyncio, uuid
from sqlalchemy import select
from app.database import async_session_factory
from app.models import ComputeNode, GpuDevice

async def seed():
    async with async_session_factory() as db:
        async with db.begin():
            existing = (await db.execute(select(ComputeNode).where(ComputeNode.node_name == 'workstation'))).scalars().first()
            if not existing:
                node = ComputeNode(id=uuid.uuid4(), node_name='workstation', hostname='localhost',
                    total_gpus=1, total_cpu_cores=8, total_memory_mb=32768, is_active=True)
                db.add(node)
                await db.flush()
                db.add(GpuDevice(id=uuid.uuid4(), node_id=node.id, gpu_index=0,
                    gpu_model='NVIDIA RTX Titan', gpu_memory_mb=24576, status='available'))
                print('Seeded.')
            else:
                print('Already seeded.')

asyncio.run(seed())
"
```

### 7. Start all processes

```bash
# Terminal 1 — API
source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Scheduler
source .venv/bin/activate && python -m app.services.scheduler

# Terminal 3 — Worker
source .venv/bin/activate && python -m app.services.worker

# Terminal 4 — Frontend
cd frontend && npm run dev
```

Open `http://localhost:5173`.

---

## Production deployment

All services run as Docker containers via `docker-compose.prod.yml`. Traffic is exposed through a **Cloudflare Tunnel** — no open firewall ports required.

### Architecture

```
Internet
    |
Cloudflare (DNS: quda.yourdomain.com -> Tunnel)
    |
cloudflared (outbound-only tunnel, runs on workstation)
    |
nginx (port 80, localhost only)
    +-- /api/*  ->  FastAPI (port 8000, internal)
    +-- /*      ->  React SPA (static files)

Internal services (Docker network, not exposed):
    PostgreSQL, Redis, MinIO, Scheduler, Worker
```

nginx is necessary because Cloudflare Tunnel routes to a single endpoint. nginx acts as the internal router between the frontend and the API.

### First-time setup

**1. Set up Cloudflare Tunnel**

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com) → Networks → Tunnels
2. Create a tunnel named `quda`
3. Under **Public Hostnames**, add:
   - Subdomain: `quda` (or whatever you want), Domain: `yourdomain.com`
   - Service: `http://localhost:80`
4. Copy the tunnel token

**2. Configure environment**

```bash
cp .env.prod.example .env
# Fill in: POSTGRES_PASSWORD, SECRET_KEY, MINIO_SECRET_KEY, CLOUDFLARE_TUNNEL_TOKEN
# Also update DATABASE_URL to use the same password as POSTGRES_PASSWORD
```

**3. Build and start**

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**4. Run migration and seed (first time only)**

```bash
docker compose -f docker-compose.prod.yml exec api python scripts/migrate.py

docker compose -f docker-compose.prod.yml exec api python -c "
import asyncio, uuid
from app.database import async_session_factory
from app.models import ComputeNode, GpuDevice

async def seed():
    async with async_session_factory() as db:
        async with db.begin():
            node = ComputeNode(id=uuid.uuid4(), node_name='aims-workstation', hostname='localhost',
                total_gpus=1, total_cpu_cores=16, total_memory_mb=65536, is_active=True)
            db.add(node)
            await db.flush()
            db.add(GpuDevice(id=uuid.uuid4(), node_id=node.id, gpu_index=0,
                gpu_model='NVIDIA RTX Titan', gpu_memory_mb=24576, status='available'))
        print('Seeded.')

asyncio.run(seed())
"
```

Once running, the app is live at `https://quda.yourdomain.com`.

### Rootless Docker

If running rootless Docker on the workstation, update `docker-compose.prod.yml` in the `worker` service:

```yaml
# Comment out:
# - /var/run/docker.sock:/var/run/docker.sock
# Uncomment:
- /run/user/1000/docker.sock:/run/user/1000/docker.sock
```

And add to the worker environment:
```yaml
DOCKER_HOST: unix:///run/user/1000/docker.sock
```

### Useful commands

```bash
# Logs
docker compose -f docker-compose.prod.yml logs -f worker

# Rebuild a single service after a code change
docker compose -f docker-compose.prod.yml up -d --build api

# Stop everything
docker compose -f docker-compose.prod.yml down
```

---

## Job submission

### Execution order inside the container

```
1. pip install -q --user -r requirements.txt   (if provided)
2. bash setup.sh                                (if provided)
3. python train.py
```

### Python file mode

Upload a `.py` script directly. Optionally attach a `requirements.txt` and/or `setup.sh`.

### GitHub repo mode

| Field | Required | Notes |
|-------|----------|-------|
| Repo URL | Yes | `https://github.com/org/repo.git` |
| Branch | No | Defaults to `main` |
| Entrypoint | Yes | `scripts/train.py` or `package.train` |
| Run as module | No | Use when the repo has relative imports (`from .utils import ...`) — runs `python -m package.train` |
| Requirements path | No | Relative path inside the repo |
| Subdirectory | No | If code is in a subdirectory |

### Writing scripts

- Write all outputs to `/outputs` — this directory is uploaded to MinIO as artifacts after the run
- `/tmp` and `/home` are writable tmpfs (8 GB each) — use for datasets, pip cache, temp files
- `/workspace` is **read-only**

---

## Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

No live services needed — all external dependencies are mocked.

---

## Admin

Grant admin access (enables priority override when submitting):

```sql
UPDATE users SET role = 'admin' WHERE email = 'user@example.com';
```

Run against the local Postgres using the `DATABASE_URL` in your `.env`.

---

## Security model

| Layer | Control | Purpose |
|-------|---------|---------|
| Identity | `--user 1000:1000` | Non-root execution inside container |
| Capabilities | `--cap-drop=ALL` | Zero Linux capabilities |
| Privileges | `--security-opt=no-new-privileges` | No escalation path |
| Syscalls | Custom seccomp profile | Block dangerous kernel calls |
| Filesystem | `--read-only` + tmpfs | Immutable root, no persistent writes except `/outputs` |
| Resources | `--memory=4096m`, `--cpus=2`, `--pids-limit=512` | Prevent resource exhaustion |
| Network | On by default, can disable per-job | Dataset downloads work; can isolate if needed |

Credential storage:
- Passwords hashed with **bcrypt**
- Session tokens stored as **SHA-256 hashes** — raw token never written to DB

---

## Project structure

```
app/
├── main.py                   # FastAPI entry point
├── config.py                 # Settings via .env
├── database.py               # Async SQLAlchemy engine
├── models.py                 # ORM models
├── schemas.py                # Pydantic schemas
├── auth.py                   # Session token auth
├── api/
│   ├── auth.py               # /auth endpoints
│   ├── jobs.py               # /jobs endpoints
│   └── admin.py              # /admin endpoints
└── services/
    ├── scheduler.py           # GPU allocation, Redis dispatch
    ├── worker.py              # Docker job execution
    ├── docker_runner.py       # Hardened docker run builder
    ├── storage.py             # Workspace prep, artifact upload
    ├── minio_client.py        # MinIO upload + presigned URLs
    ├── redis_queue.py         # Redis helpers
    └── seccomp_default.json   # Container syscall allowlist

frontend/src/
├── api/                      # Typed axios client
├── hooks/                    # TanStack Query hooks
├── components/               # JobDetailDrawer, SubmitJobForm, etc.
├── pages/                    # JobsPage, ArtifactsPage, AdminPage, LoginPage
└── lib/                      # Auth helpers, formatting

scripts/
├── migrate.py                # Idempotent DB schema migration (Python)
├── migrate.sql               # Same in raw SQL
├── requirements.txt          # PyTorch deps for the MNIST smoke test
├── sample_python_file.py     # MNIST smoke test (python-file mode)
└── sample_github_job/        # CIFAR-10 smoke test (github-repo mode)
```
