"""
system.py – Low-level system utilities.
"""
from __future__ import annotations

import hashlib
import os
import platform
import signal
import subprocess
from pathlib import Path

from .ui import print_check, print_warning, print_success, console


# ── Process management ────────────────────────────────────────────────────────

def terminate_process_tree(pid: int | None) -> None:
    """Kill an entire process group across platforms."""
    if pid is None:
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception as exc:
        print_warning(f"Failed to terminate process tree for PID {pid}: {exc}")


# ── File hashing ──────────────────────────────────────────────────────────────

def compute_file_hash(filepath: Path | str) -> str | None:
    """Return SHA-256 hex digest of *filepath*, or None on error."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(4096), b""):
                sha256.update(block)
        return sha256.hexdigest()
    except Exception as exc:
        print_warning(f"Failed to compute hash for {filepath}: {exc}")
        return None


# ── GPU detection ─────────────────────────────────────────────────────────────

def check_gpu() -> bool:
    """Return True if an NVIDIA GPU is reachable via nvidia-smi."""
    print_check("Checking for NVIDIA GPU")
    try:
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print_success("NVIDIA GPU detected.")
            return True
        print_warning("nvidia-smi returned non-zero. GPU unavailable.")
    except FileNotFoundError:
        print_warning("nvidia-smi not found. Assuming CPU-only.")
    return False


# ── Platform helpers ──────────────────────────────────────────────────────────

def matlab_args(cmd: str) -> list[str]:
    """Build a `matlab -batch` command, adding -wait on Windows."""
    args = ["matlab"]
    if platform.system() == "Windows":
        args.append("-wait")
    args += ["-batch", cmd]
    return args