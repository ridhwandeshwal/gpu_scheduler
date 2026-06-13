"""MinIO client — artifact upload and presigned URL generation.

Artifacts are stored at:  {bucket}/{user_id}/{run_id}/{filename}

This keeps each user's files namespaced so presigned URLs can't be
guessed across users, and makes per-user browsing trivial.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.config import get_settings

logger = logging.getLogger("minio")
settings = get_settings()


def _client() -> Minio:
    # Strip scheme from endpoint — Minio SDK takes host:port only
    endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix("https://")
    secure = settings.minio_endpoint.startswith("https://")
    return Minio(endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=secure)


def _public_client() -> Minio:
    if not settings.minio_public_endpoint:
        return _client()
    
    endpoint = settings.minio_public_endpoint.removeprefix("http://").removeprefix("https://")
    secure = settings.minio_public_endpoint.startswith("https://")
    return Minio(endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=secure)


def ensure_bucket() -> None:
    """Create the artifact bucket if it doesn't exist. Call once at startup."""
    client = _client()
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def upload_artifact(local_path: Path, object_key: str) -> int:
    """Upload a file to MinIO and return its size in bytes."""
    client = _client()
    file_size = local_path.stat().st_size
    client.fput_object(settings.minio_bucket, object_key, str(local_path))
    logger.info("Uploaded %s → minio://%s/%s", local_path.name, settings.minio_bucket, object_key)
    return file_size


def presign_download(object_key: str, expires_in: int = 900) -> str:
    """Generate a presigned GET URL valid for `expires_in` seconds (default 15 min)."""
    client = _public_client()
    url = client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(seconds=expires_in),
    )
    return url


def delete_artifact(object_key: str) -> None:
    """Delete an object from MinIO (best-effort, no exception on missing key)."""
    try:
        _client().remove_object(settings.minio_bucket, object_key)
    except S3Error:
        logger.warning("Failed to delete MinIO object: %s", object_key)
