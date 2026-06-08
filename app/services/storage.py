"""File storage operations: workspace preparation, repo cloning, and artifact collection.

Handles both job submission modes:
  - python_file: copy uploaded file into workspace
  - github_repo: clone repo, checkout branch/commit, resolve entrypoint
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

import git  # GitPython

from app.config import get_settings

logger = logging.getLogger("storage")
settings = get_settings()


# ── Validation ────────────────────────────────────────────


def validate_filename(name: str) -> str:
    """Validate and sanitise a filename, rejecting path traversal attempts."""
    if not name:
        raise ValueError("Empty filename")
    basename = os.path.basename(name)
    if basename != name:
        raise ValueError(f"Filename contains path separators: {name}")
    if ".." in name:
        raise ValueError(f"Filename contains '..': {name}")
    return basename


def validate_repo_path(path: str) -> str:
    """Validate a path inside a repository, rejecting traversal and absolutes."""
    if not path:
        raise ValueError("Empty path")
    if path.startswith("/"):
        raise ValueError(f"Path must be relative, got: {path}")
    if ".." in path.split(os.sep):
        raise ValueError(f"Path contains '..': {path}")
    # Normalise and re-check
    normed = os.path.normpath(path)
    if normed.startswith("..") or normed.startswith("/"):
        raise ValueError(f"Normalised path escapes root: {normed}")
    return normed


# ── Path builders ─────────────────────────────────────────


def workspace_dir(run_id: uuid.UUID) -> Path:
    """Return the workspace directory for a run."""
    return Path(settings.jobs_root) / str(run_id) / "workspace"


def logs_dir(run_id: uuid.UUID) -> Path:
    """Return the logs directory for a run."""
    return Path(settings.jobs_root) / str(run_id) / "logs"


def nas_output_dir(run_id: uuid.UUID) -> Path:
    """Return the NAS output directory for a run."""
    return Path(settings.nas_root) / "outputs" / str(run_id)


def nas_logs_dir(run_id: uuid.UUID) -> Path:
    """Return the NAS logs directory for a run."""
    return Path(settings.nas_root) / "logs" / str(run_id)


def nas_artifacts_dir(run_id: uuid.UUID) -> Path:
    """Return the NAS artifacts directory for a run."""
    return Path(settings.nas_root) / "artifacts" / str(run_id)


# ── Workspace preparation ────────────────────────────────


def prepare_workspace(
    run_id: uuid.UUID,
    source_type: str,
    *,
    # python_file mode
    uploaded_file_name: Optional[str] = None,
    uploaded_file_storage_path: Optional[str] = None,
    # github_repo mode
    repo_url: Optional[str] = None,
    repo_branch: Optional[str] = None,
    repo_commit_hash: Optional[str] = None,
    repo_subdir: Optional[str] = None,
    entrypoint: Optional[str] = None,
) -> Path:
    """Create and populate the workspace for a job run.

    Returns:
        The workspace directory path.
    """
    ws = workspace_dir(run_id)
    ws.mkdir(parents=True, exist_ok=True)

    logs = logs_dir(run_id)
    logs.mkdir(parents=True, exist_ok=True)

    nas_out = nas_output_dir(run_id)
    nas_out.mkdir(parents=True, exist_ok=True)

    nas_art = nas_artifacts_dir(run_id)
    nas_art.mkdir(parents=True, exist_ok=True)

    nas_log = nas_logs_dir(run_id)
    nas_log.mkdir(parents=True, exist_ok=True)

    if source_type == "python_file":
        _prepare_python_file(ws, uploaded_file_name, uploaded_file_storage_path)
    elif source_type == "github_repo":
        _prepare_github_repo(
            ws,
            repo_url=repo_url,
            repo_branch=repo_branch,
            repo_commit_hash=repo_commit_hash,
            repo_subdir=repo_subdir,
            entrypoint=entrypoint,
        )
    else:
        raise ValueError(f"Unknown source_type: {source_type}")

    return ws


def _prepare_python_file(
    workspace: Path,
    filename: Optional[str],
    storage_path: Optional[str],
) -> None:
    """Copy the uploaded Python file into the workspace."""
    if not filename or not storage_path:
        raise ValueError("uploaded_file_name and uploaded_file_storage_path are required")

    src = Path(storage_path)
    if not src.exists():
        raise FileNotFoundError(f"Uploaded file not found: {src}")

    dst = workspace / validate_filename(filename)
    shutil.copy2(src, dst)
    logger.info("Copied %s → %s", src, dst)


def _prepare_github_repo(
    workspace: Path,
    *,
    repo_url: Optional[str],
    repo_branch: Optional[str],
    repo_commit_hash: Optional[str],
    repo_subdir: Optional[str],
    entrypoint: Optional[str],
) -> None:
    """Clone a GitHub repository into the workspace and checkout the right ref."""
    if not repo_url:
        raise ValueError("repo_url is required for github_repo jobs")

    branch = repo_branch or "main"
    logger.info("Cloning %s (branch=%s) → %s", repo_url, branch, workspace)

    # Clone into workspace
    repo = git.Repo.clone_from(
        repo_url,
        str(workspace),
        branch=branch,
        depth=1 if not repo_commit_hash else 0,  # Shallow clone unless commit is specified
    )

    # Checkout specific commit if provided
    if repo_commit_hash:
        logger.info("Checking out commit %s", repo_commit_hash)
        repo.git.checkout(repo_commit_hash)

    # Verify entrypoint exists
    if entrypoint:
        entry_path = workspace
        if repo_subdir:
            validated_subdir = validate_repo_path(repo_subdir)
            entry_path = workspace / validated_subdir

        validated_entry = validate_repo_path(entrypoint)
        full_entry_path = workspace / validated_entry

        if not full_entry_path.exists():
            raise FileNotFoundError(
                f"Entrypoint not found in repository: {entrypoint} "
                f"(looked at {full_entry_path})"
            )

    logger.info("Repository cloned and ready")


# ── Workspace snapshotting & artifact collection ──────────


def snapshot_workspace(workspace: Path) -> dict[str, str]:
    """Create a snapshot of all files in the workspace.

    Returns:
        A dict mapping relative file paths to their SHA-256 checksums.
    """
    snapshot: dict[str, str] = {}

    for root, _dirs, files in os.walk(workspace):
        # Skip .git directory
        if ".git" in root.split(os.sep):
            continue

        for fname in files:
            full_path = Path(root) / fname
            rel_path = str(full_path.relative_to(workspace))
            sha256 = _file_sha256(full_path)
            snapshot[rel_path] = sha256

    return snapshot


def collect_artifacts(
    run_id: uuid.UUID,
    before: dict[str, str],
    after: dict[str, str],
    workspace: Path,
) -> list[dict]:
    """Compare before/after snapshots to find new and modified files.

    Copies discovered artifacts to NAS and returns metadata for DB insertion.

    Returns:
        List of dicts with keys: artifact_type, file_name, file_path,
        file_size_bytes, checksum_sha256.
    """
    artifacts: list[dict] = []
    dest_dir = nas_artifacts_dir(run_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, sha256 in after.items():
        if rel_path not in before:
            artifact_type = "output_new"
        elif before[rel_path] != sha256:
            artifact_type = "output_modified"
        else:
            continue  # Unchanged

        src = workspace / rel_path
        dst = dest_dir / rel_path

        # Create parent directories in destination
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        file_size = src.stat().st_size

        artifacts.append(
            {
                "artifact_type": artifact_type,
                "file_name": os.path.basename(rel_path),
                "file_path": str(dst),
                "file_size_bytes": file_size,
                "checksum_sha256": sha256,
            }
        )

    # 2. Scan nas_output_dir (since the container writes directly to the NAS /outputs mount)
    out_dir = nas_output_dir(run_id)
    if out_dir.exists():
        for root, _dirs, files in os.walk(out_dir):
            # Skip checking/cataloging downloaded datasets like MNIST in 'data' directory
            if "data" in Path(root).parts:
                continue
            for fname in files:
                full_path = Path(root) / fname
                rel_path = str(full_path.relative_to(out_dir))
                file_size = full_path.stat().st_size
                sha256 = _file_sha256(full_path)

                artifacts.append(
                    {
                        "artifact_type": "output_file",
                        "file_name": os.path.basename(rel_path),
                        "file_path": str(full_path),
                        "file_size_bytes": file_size,
                        "checksum_sha256": sha256,
                    }
                )

    logger.info(
        "Collected %d artifact(s) for run %s (%d from workspace diff, %d from output dir)",
        len(artifacts),
        run_id,
        sum(1 for a in artifacts if a["artifact_type"] in ("output_new", "output_modified")),
        sum(1 for a in artifacts if a["artifact_type"] == "output_file"),
    )

    return artifacts


def copy_logs_to_nas(run_id: uuid.UUID) -> dict[str, str]:
    """Copy local log files to NAS storage.

    Returns:
        Dict mapping log type to NAS path.
    """
    local_logs = logs_dir(run_id)
    nas_logs = nas_logs_dir(run_id)
    nas_logs.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}

    for log_name in ("stdout.log", "stderr.log", "combined.log"):
        src = local_logs / log_name
        if src.exists():
            dst = nas_logs / log_name
            shutil.copy2(src, dst)
            paths[log_name.replace(".log", "")] = str(dst)

    return paths


# ── Helpers ───────────────────────────────────────────────


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file in 64KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
