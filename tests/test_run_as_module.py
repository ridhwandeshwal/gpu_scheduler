"""Isolated unit tests for run_as_module feature and artifact collection.

No live services required — database, Redis, MinIO, and Docker are all mocked.
Run with:  pytest tests/ -v
"""

import hashlib
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.api.jobs import _entrypoint_to_module
from app.services.storage import (
    collect_artifacts,
    nas_output_dir,
    snapshot_workspace,
    validate_repo_path,
)


# ── _entrypoint_to_module ─────────────────────────────────────────────────────

class TestEntrypointToModule:
    def test_file_path_nested(self):
        assert _entrypoint_to_module("package/sub/train.py") == "package.sub.train"

    def test_file_path_top_level(self):
        assert _entrypoint_to_module("train.py") == "train"

    def test_file_path_one_level(self):
        assert _entrypoint_to_module("mypackage/train.py") == "mypackage.train"

    def test_already_module_notation(self):
        assert _entrypoint_to_module("mypackage.train") == "mypackage.train"

    def test_already_module_nested(self):
        assert _entrypoint_to_module("pkg.sub.train") == "pkg.sub.train"

    def test_module_with_py_suffix(self):
        # Edge case: someone writes "pkg.train.py" — strip the suffix
        assert _entrypoint_to_module("pkg.train.py") == "pkg.train"

    def test_windows_backslash(self):
        assert _entrypoint_to_module("package\\sub\\train.py") == "package.sub.train"

    def test_no_extension(self):
        # No .py, no slashes — treated as bare module name
        assert _entrypoint_to_module("train") == "train"


# ── validate_repo_path ───────────────────────────────────────────────────────

class TestValidateRepoPath:
    def test_simple_file(self):
        assert validate_repo_path("train.py") == "train.py"

    def test_nested_path(self):
        result = validate_repo_path("scripts/train.py")
        assert result == "scripts/train.py"

    def test_module_notation_passes(self):
        # Module paths should pass validation (no slashes, no ..)
        assert validate_repo_path("package.train") == "package.train"

    def test_rejects_absolute(self):
        with pytest.raises(ValueError, match="relative"):
            validate_repo_path("/etc/passwd")

    def test_rejects_traversal(self):
        with pytest.raises(ValueError):
            validate_repo_path("../../secrets.txt")


# ── Module-path entrypoint detection in _prepare_github_repo ─────────────────

class TestModulePathDetection:
    """
    Test the logic that converts a module-notation entrypoint to a file path
    for existence checking. We test the heuristic directly on examples rather
    than calling _prepare_github_repo (which needs a real git remote).
    """

    def _detect(self, entrypoint: str) -> str:
        """Replicate the detection logic from _prepare_github_repo."""
        validated = validate_repo_path(entrypoint)
        if "." in validated and "/" not in validated and not validated.endswith((".py", ".sh")):
            return validated.replace(".", "/") + ".py"
        return validated

    def test_module_notation_converts(self):
        assert self._detect("package.train") == "package/train.py"

    def test_module_notation_nested(self):
        assert self._detect("pkg.sub.train") == "pkg/sub/train.py"

    def test_file_path_unchanged(self):
        assert self._detect("package/train.py") == "package/train.py"

    def test_top_level_py_unchanged(self):
        assert self._detect("train.py") == "train.py"

    def test_sh_unchanged(self):
        assert self._detect("setup.sh") == "setup.sh"


# ── snapshot_workspace ───────────────────────────────────────────────────────

class TestSnapshotWorkspace:
    def test_empty_dir(self, tmp_path):
        assert snapshot_workspace(tmp_path) == {}

    def test_single_file(self, tmp_path):
        f = tmp_path / "train.py"
        f.write_text("print('hello')")
        snap = snapshot_workspace(tmp_path)
        assert "train.py" in snap
        assert len(snap["train.py"]) == 64  # SHA-256 hex

    def test_nested_files(self, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "model.py").write_text("class Model: pass")
        snap = snapshot_workspace(tmp_path)
        assert "pkg/model.py" in snap

    def test_git_dir_excluded(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")
        snap = snapshot_workspace(tmp_path)
        assert not any(".git" in k for k in snap)

    def test_detects_modification(self, tmp_path):
        f = tmp_path / "weights.pt"
        f.write_bytes(b"\x00" * 100)
        before = snapshot_workspace(tmp_path)

        f.write_bytes(b"\xff" * 100)
        after = snapshot_workspace(tmp_path)

        assert before["weights.pt"] != after["weights.pt"]


# ── collect_artifacts ────────────────────────────────────────────────────────

class TestCollectArtifacts:
    """
    collect_artifacts uploads files to MinIO and returns metadata.
    MinIO is mocked so no live service is needed.
    """

    def test_no_outputs_returns_empty(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "train.py").write_text("print('hi')")
        before = snapshot_workspace(ws)
        after = snapshot_workspace(ws)  # unchanged

        run_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch("app.services.minio_client.upload_artifact", return_value=0) as mock_upload, \
             patch("app.services.storage.nas_output_dir", return_value=tmp_path / "nonexistent_outputs"):
            result = collect_artifacts(run_id, user_id, before, after, ws)

        assert result == []
        mock_upload.assert_not_called()

    def test_new_workspace_file_collected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "train.py").write_text("print('hi')")
        before = snapshot_workspace(ws)

        # Simulate job creating a new file in workspace
        (ws / "checkpoint.pt").write_bytes(b"\x01" * 50)
        after = snapshot_workspace(ws)

        run_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch("app.services.minio_client.upload_artifact", return_value=50) as mock_upload, \
             patch("app.services.storage.nas_output_dir", return_value=tmp_path / "nonexistent_outputs"):
            result = collect_artifacts(run_id, user_id, before, after, ws)

        assert len(result) == 1
        assert result[0]["file_name"] == "checkpoint.pt"
        assert result[0]["artifact_type"] == "output_new"
        assert result[0]["file_size_bytes"] == 50
        assert result[0]["object_key"] == f"{user_id}/{run_id}/checkpoint.pt"
        mock_upload.assert_called_once()

    def test_outputs_dir_files_collected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        before = snapshot_workspace(ws)
        after = snapshot_workspace(ws)

        out_dir = tmp_path / "outputs"
        out_dir.mkdir()
        (out_dir / "model.pth").write_bytes(b"\x42" * 200)
        (out_dir / "metrics.json").write_text('{"accuracy": 0.95}')

        run_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch("app.services.minio_client.upload_artifact", return_value=1) as mock_upload, \
             patch("app.services.storage.nas_output_dir", return_value=out_dir):
            result = collect_artifacts(run_id, user_id, before, after, ws)

        assert len(result) == 2
        file_names = {r["file_name"] for r in result}
        assert "model.pth" in file_names
        assert "metrics.json" in file_names
        assert all(r["artifact_type"] == "output_file" for r in result)

    def test_data_subdir_excluded(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        before = snapshot_workspace(ws)
        after = snapshot_workspace(ws)

        out_dir = tmp_path / "outputs"
        (out_dir / "data").mkdir(parents=True)
        (out_dir / "data" / "dataset.bin").write_bytes(b"\x00" * 1000)
        (out_dir / "model.pth").write_bytes(b"\x01" * 50)

        run_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch("app.services.minio_client.upload_artifact", return_value=1) as mock_upload, \
             patch("app.services.storage.nas_output_dir", return_value=out_dir):
            result = collect_artifacts(run_id, user_id, before, after, ws)

        file_names = {r["file_name"] for r in result}
        assert "model.pth" in file_names
        assert "dataset.bin" not in file_names

    def test_object_key_format(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        before = snapshot_workspace(ws)
        (ws / "result.txt").write_text("done")
        after = snapshot_workspace(ws)

        run_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch("app.services.minio_client.upload_artifact", return_value=4), \
             patch("app.services.storage.nas_output_dir", return_value=tmp_path / "nonexistent"):
            result = collect_artifacts(run_id, user_id, before, after, ws)

        assert result[0]["object_key"] == f"{user_id}/{run_id}/result.txt"


# ── GitHubJobRequest schema ───────────────────────────────────────────────────

class TestGitHubJobRequestSchema:
    def test_run_as_module_defaults_false(self):
        from app.schemas import GitHubJobRequest
        req = GitHubJobRequest(repo_url="https://github.com/a/b.git", entrypoint="train.py")
        assert req.run_as_module is False

    def test_run_as_module_can_be_set(self):
        from app.schemas import GitHubJobRequest
        req = GitHubJobRequest(
            repo_url="https://github.com/a/b.git",
            entrypoint="pkg/train.py",
            run_as_module=True,
        )
        assert req.run_as_module is True

    def test_entrypoint_required(self):
        from pydantic import ValidationError
        from app.schemas import GitHubJobRequest
        with pytest.raises(ValidationError):
            GitHubJobRequest(repo_url="https://github.com/a/b.git")
