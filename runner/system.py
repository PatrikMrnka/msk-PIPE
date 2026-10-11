"""
system.py – Low-level system utilities.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import signal
import subprocess
from pathlib import Path

from .ui import print_check, print_error, print_info, print_subprocess_error, print_warning, print_success, console


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


def get_driver_cuda_version() -> tuple[int, int] | None:
    """Highest CUDA version supported by the installed driver (nvidia-smi header)."""
    try:
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None
        match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_compute_capability() -> tuple[int, int] | None:
    """Compute capability of the first GPU, e.g. (12, 0) for RTX 50xx."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        major, minor = result.stdout.strip().splitlines()[0].strip().split(".")
        return int(major), int(minor)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


# ── PyTorch wheel index selection ─────────────────────────────────────────────

TORCH_INDEX_CU128 = "https://download.pytorch.org/whl/cu128"
TORCH_INDEX_CU126 = "https://download.pytorch.org/whl/cu126"


def get_torch_pip_index() -> str:
    """
    Return the pip --index-url for CUDA PyTorch wheels.

    cu128 is the default: it ships kernels for sm_75 … sm_120, i.e. every RTX
    generation (Turing 20xx, Ampere 30xx, Ada 40xx, Blackwell 50xx).
    cu126 is used only for pre-Turing GPUs (GTX 10xx, Volta), which cu128 no
    longer supports, or for drivers that cannot run CUDA 12.8 (< 570).
    """
    cc = get_compute_capability()
    cuda = get_driver_cuda_version()

    if cc is not None and cc < (7, 5):
        print_info(f"GPU sm_{cc[0]}{cc[1]} is older than Turing → torch index cu126.")
        return TORCH_INDEX_CU126

    if cuda is not None and cuda < (12, 8):
        if cc is not None and cc >= (12, 0):
            # Blackwell has no usable fallback – cu126 has no sm_120 kernels.
            print_error(
                f"Blackwell GPU (sm_{cc[0]}{cc[1]}) needs a driver with CUDA >= 12.8, "
                f"but the installed driver only supports CUDA {cuda[0]}.{cuda[1]}. "
                "Please update the NVIDIA driver (570 series or newer)."
            )
            return TORCH_INDEX_CU128
        print_warning(
            f"Driver supports only CUDA {cuda[0]}.{cuda[1]} → torch index cu126. "
            "Updating the NVIDIA driver is recommended."
        )
        return TORCH_INDEX_CU126

    print_info("Torch index: cu128")
    return TORCH_INDEX_CU128


# ── Platform helpers ──────────────────────────────────────────────────────────

def matlab_args(cmd: str) -> list[str]:
    """Build a `matlab -batch` command, adding -wait on Windows."""
    args = ["matlab"]
    if platform.system() == "Windows":
        args.append("-wait")
    args += ["-batch", cmd]
    return args
