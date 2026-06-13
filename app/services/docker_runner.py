"""Docker container runner for sandboxed job execution.

Executes user code exclusively inside Docker containers — never on the host.
Uses the NVIDIA Container Toolkit for GPU passthrough via ``--gpus``.

Security controls (defense-in-depth):
  - --user (non-root execution inside the container)
  - --read-only (immutable root filesystem)
  - --tmpfs (size-limited writable scratch areas)
  - --security-opt=no-new-privileges
  - --cap-drop=ALL
  - --security-opt seccomp=<profile> (custom syscall filter)
  - --pids-limit (process count limit)
  - --memory (memory limit)
  - --cpus (CPU limit)
  - --ulimit nofile / nproc (file descriptor & process limits)
  - --log-driver json-file with max-size (prevent log bombs)
  - --network=none (optional network isolation)
  - Timeout enforcement via asyncio.wait_for
  - Volume path validation (symlink & traversal protection)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger("docker_runner")
settings = get_settings()

# Path to the bundled seccomp profile (alongside this module)
_SECCOMP_PROFILE = Path(__file__).parent / "seccomp_default.json"


@dataclass
class RunConfig:
    """Configuration for a container run."""

    run_id: uuid.UUID
    workspace: Path
    output_dir: Path
    logs_dir: Path
    execution_command: str
    container_image: str = ""
    memory_mb: int = 4096
    cpu_cores: int = 2
    pids_limit: int = 512
    env_vars: dict[str, str] = field(default_factory=dict)
    gpu_devices: list[dict] = field(default_factory=list)
    network_enabled: bool = True
    max_runtime_seconds: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.container_image:
            self.container_image = settings.default_container_image


@dataclass
class RunResult:
    """Result of a container execution."""

    exit_code: int
    duration_seconds: float
    container_id: Optional[str] = None
    stdout_log_path: Optional[str] = None
    stderr_log_path: Optional[str] = None
    combined_log_path: Optional[str] = None
    error_message: Optional[str] = None
    timed_out: bool = False


# ── Allowed env-var name pattern (block shell injection) ──

_SAFE_ENV_NAME_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
)


def _validate_env_name(name: str) -> bool:
    """Return True if the env var name contains only safe characters."""
    return bool(name) and all(c in _SAFE_ENV_NAME_CHARS for c in name)


def _validate_mount_path(path: Path, expected_root: str) -> None:
    """Ensure *path* resolves within *expected_root* (no symlink escape).

    Raises ValueError on traversal or symlink escape.
    """
    try:
        resolved = path.resolve(strict=False)
        root_resolved = Path(expected_root).resolve(strict=False)
        # Ensure the resolved path is within the expected root
        resolved.relative_to(root_resolved)
    except (ValueError, RuntimeError) as exc:
        raise ValueError(
            f"Mount path escapes expected root: {path} "
            f"(resolved={path.resolve()}, root={expected_root})"
        ) from exc


class DockerRunner:
    """Execute commands inside hardened Docker containers."""

    def __init__(self) -> None:
        if not shutil.which("docker"):
            logger.error(
                "Docker binary not found on PATH — container execution will fail"
            )

    # ── Public API ────────────────────────────────────────

    async def run(self, config: RunConfig) -> RunResult:
        """Run a command inside a Docker container.

        Streams stdout/stderr to log files and enforces timeout limits.
        """
        cmd = self._build_command(config)
        logger.info("Container command: %s", " ".join(cmd))

        stdout_path = config.logs_dir / "stdout.log"
        stderr_path = config.logs_dir / "stderr.log"
        combined_path = config.logs_dir / "combined.log"

        start_time = time.monotonic()
        container_name = f"gpu-job-{config.run_id}"
        timed_out = False
        error_message: Optional[str] = None

        # Ensure logs directory exists
        config.logs_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        if settings.docker_host:
            env["DOCKER_HOST"] = settings.docker_host

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout_file = open(stdout_path, "wb")
            stderr_file = open(stderr_path, "wb")
            combined_file = open(combined_path, "wb")

            stdout_chunks = []
            stderr_chunks = []

            async def read_stream(stream, file_obj, chunks_list):
                try:
                    while True:
                        chunk = await stream.read(4096)
                        if not chunk:
                            break
                        file_obj.write(chunk)
                        file_obj.flush()
                        combined_file.write(chunk)
                        combined_file.flush()
                        chunks_list.append(chunk)
                except asyncio.CancelledError:
                    pass

            stdout_task = asyncio.create_task(read_stream(process.stdout, stdout_file, stdout_chunks))
            stderr_task = asyncio.create_task(read_stream(process.stderr, stderr_file, stderr_chunks))

            timeout = config.max_runtime_seconds

            try:
                if timeout:
                    await asyncio.wait_for(
                        asyncio.gather(stdout_task, stderr_task, process.wait()),
                        timeout=timeout
                    )
                else:
                    await asyncio.gather(stdout_task, stderr_task, process.wait())
            except asyncio.TimeoutError:
                timed_out = True
                error_message = (
                    f"Job exceeded maximum runtime of {timeout} seconds"
                )
                logger.warning(
                    "Run %s timed out after %ds — killing container",
                    config.run_id,
                    timeout,
                )
                # Attempt graceful stop, then force-kill
                await self._force_remove(container_name)
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            finally:
                # Cancel the streaming tasks if they are still running
                stdout_task.cancel()
                stderr_task.cancel()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

                # Close file descriptors
                stdout_file.close()
                stderr_file.close()
                combined_file.close()

            stdout_data = b"".join(stdout_chunks)
            stderr_data = b"".join(stderr_chunks)

            exit_code = process.returncode if process.returncode is not None else -1
            duration = time.monotonic() - start_time

            if exit_code != 0 and not timed_out:
                stderr_text = stderr_data.decode("utf-8", errors="replace")
                last_lines = "\n".join(stderr_text.strip().splitlines()[-10:])
                error_message = last_lines or f"Process exited with code {exit_code}"

            return RunResult(
                exit_code=exit_code,
                duration_seconds=round(duration, 2),
                container_id=container_name,
                stdout_log_path=str(stdout_path),
                stderr_log_path=str(stderr_path),
                combined_log_path=str(combined_path),
                error_message=error_message,
                timed_out=timed_out,
            )

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.exception("Container execution failed for run %s", config.run_id)
            # Best-effort cleanup
            await self._force_remove(container_name)
            return RunResult(
                exit_code=-1,
                duration_seconds=round(duration, 2),
                error_message=str(e),
            )

    async def stop(self, container_id: str, timeout: int = 10) -> bool:
        """Stop a running container (graceful then force-remove)."""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "stop", "-t", str(timeout), container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout + 15
            )
            if process.returncode == 0:
                logger.info("Stopped container %s", container_id)
                return True
            else:
                logger.warning(
                    "Failed to stop container %s: %s",
                    container_id,
                    stderr.decode(errors="replace"),
                )
                # Force remove as fallback
                await self._force_remove(container_id)
                return True
        except asyncio.TimeoutError:
            logger.error("Timeout stopping container %s — force removing", container_id)
            await self._force_remove(container_id)
            return False
        except Exception:
            logger.exception("Error stopping container %s", container_id)
            return False

    # ── Command builder ───────────────────────────────────

    def _build_command(self, config: RunConfig) -> list[str]:
        """Build the full ``docker run`` command with security hardening."""

        container_name = f"gpu-job-{config.run_id}"

        args = [
            "docker", "run", "--rm",
            f"--name={container_name}",

            # ── Identity ──────────────────────────────────
            f"--user={settings.container_user}",

            # ── Capabilities & privileges ─────────────────
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",

            # ── Seccomp ───────────────────────────────────
        ]

        if _SECCOMP_PROFILE.exists():
            args.append(f"--security-opt=seccomp={_SECCOMP_PROFILE}")

        # ── Filesystem isolation ──────────────────────────
        if settings.container_read_only:
            args.append("--read-only")
            # Writable tmpfs for areas that typically need writes
            tmpfs_size = settings.container_tmpfs_size_mb
            args += [
                f"--tmpfs=/tmp:rw,exec,nosuid,size={tmpfs_size}m",
                "--tmpfs=/var/tmp:rw,noexec,nosuid,size=256m",
            ]
            args += [
                "-e", "USER=worker",
                "-e", "LOGNAME=worker",
                # HOME→/tmp so pip's cache lookup resolves to the tmpfs we own,
                # fixing the '/home/.cache/pip not writable' warning.
                "-e", "HOME=/tmp",
                "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-e", "PYTHONPYCACHEPREFIX=/tmp/__pycache__",
                # Packages are installed to disk (/outputs/.pip-user) so Python
                # needs this on its search path at runtime.
                "-e", "PYTHONPATH=/outputs/.pip-user/lib/python3.11/site-packages",
            ]

        # ── Resource limits ───────────────────────────────
        args += [
            f"--pids-limit={config.pids_limit}",
            f"--memory={config.memory_mb}m",
            f"--cpus={config.cpu_cores}",
            "--ulimit=nofile=1024:2048",
        ]

        # ── Log limits (prevent log bombs) ────────────────
        args += [
            "--log-driver=json-file",
            f"--log-opt=max-size={settings.container_log_max_size}",
            "--log-opt=max-file=1",
        ]

        # ── Volume mounts ─────────────────────────────────
        # Workspace is read-only; outputs directory is writable
        _validate_mount_path(config.workspace, settings.jobs_root)
        _validate_mount_path(config.output_dir, settings.nas_root)

        host_workspace = str(config.workspace)
        if settings.host_jobs_root:
            host_workspace = host_workspace.replace(str(settings.jobs_root), str(settings.host_jobs_root), 1)

        host_output_dir = str(config.output_dir)
        if settings.host_nas_root:
            host_output_dir = host_output_dir.replace(str(settings.nas_root), str(settings.host_nas_root), 1)

        args += ["-v", f"{host_workspace}:/workspace:ro"]
        args += ["-v", f"{host_output_dir}:/outputs:rw"]
        args += ["--workdir", "/workspace"]

        # ── Environment variables (sanitised) ─────────────
        for key, value in config.env_vars.items():
            if not _validate_env_name(key):
                logger.warning(
                    "Skipping unsafe env var name: %r", key
                )
                continue
            args += ["-e", f"{key}={value}"]

        # ── Network isolation ─────────────────────────────
        if not config.network_enabled:
            args.append("--network=none")

        # ── GPU arguments ─────────────────────────────────
        gpu_args = self._build_gpu_args(config.gpu_devices)
        args += gpu_args

        # ── Image ─────────────────────────────────────────
        args.append(config.container_image)

        # ── Command ───────────────────────────────────────
        args += ["bash", "-lc", config.execution_command]

        return args

    def _build_gpu_args(self, gpu_devices: list[dict]) -> list[str]:
        """Build GPU-related Docker arguments.

        Supports:
          - none: No GPU passthrough
          - nvidia: NVIDIA GPU passthrough via --gpus (requires nvidia-container-toolkit)
        """
        mode = settings.gpu_mode

        if mode == "none" or not gpu_devices:
            return []

        if mode == "nvidia":
            # Build per-device GPU specification.
            # NOTE: do NOT add shell-quoting around the value here — subprocess
            # exec passes args directly to the kernel without a shell, so quotes
            # would be treated as literal characters and Docker would reject them.
            indices = [str(g.get("gpu_index", 0)) for g in gpu_devices]
            device_str = ",".join(f"device={i}" for i in indices)
            return ["--gpus", device_str]

        logger.warning("Unknown GPU_MODE: %s — ignoring GPU args", mode)
        return []

    # ── Internal helpers ──────────────────────────────────

    async def _force_remove(self, container_name: str) -> None:
        """Force-remove a container (best-effort, no exceptions)."""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=15)
        except Exception:
            pass  # Best-effort
