"""GPU Job Scheduler — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.jobs import router as jobs_router
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

    yield

    # Shutdown
    logger.info("GPU Job Scheduler shutting down")
    await close_redis()


app = FastAPI(
    title="GPU Job Scheduler",
    description=(
        "Backend execution layer for scheduling and running GPU-accelerated "
        "jobs in hardened Docker containers."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── Routers ───────────────────────────────────────────────

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])


# ── Health check ──────────────────────────────────────────


@app.get("/health", tags=["System"])
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "gpu-job-scheduler"}
