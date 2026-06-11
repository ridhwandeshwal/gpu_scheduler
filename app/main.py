"""GPU Job Scheduler — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.jobs import router as jobs_router
from app.api.admin import router as admin_router
from app.services.minio_client import ensure_bucket
from app.services.redis_queue import close_redis, get_redis

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    # Startup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("GPU Job Scheduler starting up")

    # Warm up Redis connection
    await get_redis()
    logger.info("Redis connection established")

    # Ensure MinIO artifact bucket exists
    ensure_bucket()
    logger.info("MinIO bucket ready")

    yield

    # Shutdown
    logger.info("GPU Job Scheduler shutting down")
    await close_redis()


app = FastAPI(
    title="Quda",
    description=(
        "GPU job scheduler for the AIMS-DTU lab workstation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
app.include_router(admin_router, prefix="/admin", tags=["Admin Control"])


# ── Health check ──────────────────────────────────────────


@app.get("/health", tags=["System"])
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "gpu-job-scheduler"}
