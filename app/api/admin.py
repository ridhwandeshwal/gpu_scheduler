"""Admin management API endpoints: user management, global job view, priority updates."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Job, User
from app.schemas import JobListResponse, JobResponse

router = APIRouter()


# ── Pydantic Request/Response Schemas ──────────────────────

class AdminUserUpdate(BaseModel):
    role: Optional[str] = Field(None, description="User role (e.g. admin, user)")
    status: Optional[str] = Field(None, description="User status (e.g. active, suspended)")


class AdminJobUpdate(BaseModel):
    priority: Optional[int] = Field(None, ge=1, le=10, description="Job priority (1-10)")
    status: Optional[str] = Field(None, description="Job status override (e.g. queued, cancelled)")


class UserAdminResponse(BaseModel):
    id: uuid_mod.UUID
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dependency: Require Admin Role ────────────────────────

def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to enforce that the calling user has the admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access this resource",
        )
    return current_user


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /admin/users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/users",
    response_model=list[UserAdminResponse],
    summary="List all users",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
) -> list[UserAdminResponse]:
    """Retrieve details of all registered users in the database."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserAdminResponse.model_validate(u) for u in users]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PATCH /admin/users/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.patch(
    "/users/{user_id}",
    response_model=UserAdminResponse,
    summary="Update a user's role or status",
)
async def update_user(
    user_id: uuid_mod.UUID,
    body: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
) -> UserAdminResponse:
    """Update a user's role or status in the system."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id and body.role == "user":
        raise HTTPException(
            status_code=400,
            detail="Cannot demote yourself from admin role",
        )

    if body.role is not None:
        if body.role not in ("admin", "user"):
            raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'user'")
        user.role = body.role

    if body.status is not None:
        if body.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'active' or 'suspended'")
        user.status = body.status

    await db.commit()
    await db.refresh(user)
    return UserAdminResponse.model_validate(user)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DELETE /admin/users/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.delete(
    "/users/{user_id}",
    summary="Delete a user",
)
async def delete_user(
    user_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """Delete a user from the system."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    await db.delete(user)
    await db.commit()
    return {"message": f"User {user.username} successfully deleted"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /admin/jobs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List all cluster jobs",
)
async def list_all_jobs(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
) -> JobListResponse:
    """Retrieve all jobs in the cluster across all users, sorted by priority and date."""
    query = select(Job)
    count_query = select(func.count(Job.id))

    if status_filter:
        query = query.where(Job.status == status_filter)
        count_query = count_query.where(Job.status == status_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (max(page, 1) - 1) * page_size
    query = query.order_by(Job.priority.asc(), Job.submitted_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PATCH /admin/jobs/{job_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.patch(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Modify job settings",
)
async def update_job_priority_or_status(
    job_id: uuid_mod.UUID,
    body: AdminJobUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
) -> JobResponse:
    """Modify a job's priority or force override its status (Admins only)."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if body.priority is not None:
        job.priority = body.priority

    if body.status is not None:
        # Simple safety check on status transitions if overridden manually
        allowed_statuses = ("queued", "scheduled", "running", "completed", "failed", "cancelled")
        if body.status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {body.status}. Must be one of {allowed_statuses}",
            )
        job.status = body.status

    await db.commit()
    await db.refresh(job)

    # Return full updated job details
    result = await db.execute(select(Job).where(Job.id == job_id))
    updated_job = result.scalars().first()
    return JobResponse.model_validate(updated_job)
