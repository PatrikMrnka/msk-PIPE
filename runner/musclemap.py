"""
musclemap.py – MuscleMap repository setup and installation into conda env.

Two public functions:
  check_and_setup_musclemap – entry point called from preflight
  install_musclemap_in_env  – pip-installs MuscleMap into the target env
                              (was a nested function in the original code)

GPU environments skip torch/torchvision/torchaudio during dependency
install to preserve the conda-installed pytorch-cuda variant.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from rich.prompt import Confirm

from . import constants as C
from .micromamba import make_mamba_env
from .ui import print_check, print_error, print_info, print_step, print_subprocess_error, print_success, print_warning

_TORCH_PACKAGES = {"torch", "torchvision", "torchaudio"}


# ── Env helpers ───────────────────────────────────────────────────────────────

def _python_exe(env_name: str) -> Path:
    env_path = (C.ENVS_DIR / env_name).resolve()
    rel = "python.exe" if platform.system() == "Windows" else "bin/python"
    return env_path / rel


def _micromamba_run(env_name: str, *cmd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    env_path = str((C.ENVS_DIR / env_name).resolve())
    return subprocess.run(
        ["micromamba", "run", "-p", env_path, *cmd],
        capture_output=True, text=True, timeout=timeout,
        env=make_mamba_env(),
    )


# ── GPU-safe requirements filtering ──────────────────────────────────────────

def _remove_torch_from_requirements(req_file: Path) -> None:
    """
    Overwrite the requirements file with torch packages removed.
    """
    filtered: list[str] = []
    with open(req_file, encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            pkg = raw.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].strip().lower()
            if pkg not in _TORCH_PACKAGES:
                filtered.append(raw)

    with open(req_file, "w", encoding="utf-8") as tf:
        tf.write("\n".join(filtered) + "\n")


# ── Installation ──────────────────────────────────────────────────────────────

def install_musclemap_in_env(repo_path: Path, env_name: str) -> bool:
    """
    pip-install MuscleMap from *repo_path* into *env_name*.

    GPU environments first install dependencies from a filtered requirements
    file (torch excluded) then install MuscleMap itself with --no-deps so
    the conda-managed pytorch-cuda is not overwritten.
    """
    python_exe = _python_exe(env_name)
    if not python_exe.exists():
        print_error(f"Python not found for {env_name} at {python_exe}")
        return False

    is_gpu_env = env_name.endswith("_gpu")
    print_info(f"Installing MuscleMap into '{env_name}'...")

    if is_gpu_env:
        req_file = repo_path / "requirements.txt"
        if not req_file.exists():
            print_error(f"requirements.txt not found at {req_file}")
            return False

        print_info("GPU env: removing torch from requirements.txt to respect conda pytorch-cuda.")
        _remove_torch_from_requirements(req_file)

    install_result = _micromamba_run(
        env_name, "python", "-m", "pip", "install",
        "-e", str(repo_path.resolve()),
    )

    if install_result.returncode != 0:
        print_error("MuscleMap pip install failed.")
        if install_result.stderr:
            print_subprocess_error(install_result.stderr)
        return False

    # Smoke-test: mm_segment must be importable
    verify = _micromamba_run(env_name, "mm_segment", "-h", timeout=120)
    if verify.returncode != 0:
        print_warning("MuscleMap installed but mm_segment verification failed.")
        if verify.stderr:
            print_subprocess_error(verify.stderr)
        return False

    print_success("MuscleMap installed – mm_segment is available.")
    return True


def _clone_musclemap(dest: Path) -> bool:
    """Clone the MuscleMap repository into *dest*. Returns True on success."""
    print_info("Cloning MuscleMap repository...")
    clone_cmd = [
        "git", "clone", "--depth", "1", "--single-branch",
        C.MUSCLEMAP_REPO_URL, str(dest),
    ]
    try:
        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except subprocess.TimeoutExpired:
        print_error("Timed out while cloning MuscleMap after 30 minutes.")
        print_warning("Check your network connection and try again.")
        return False
    if result.returncode == 0:
        print_success("MuscleMap cloned successfully.")
        return True
    print_error(f"Failed to clone MuscleMap: {result.stderr}")
    return False


# ── Public entry point ────────────────────────────────────────────────────────

def check_and_setup_musclemap(env_name: str) -> bool:
    """
    Ensure MuscleMap is present and installed into *env_name*.

    If the repository is missing, offer to clone it from GitHub.
    Returns True only when MuscleMap is installed and mm_segment works.
    """
    print_check("Checking MuscleMap repository")

    repo_path = C.MUSCLEMAP_DEFAULT_DIR

    if repo_path.is_dir():
        print_success("MuscleMap found at src/MuscleMap.")
        
        # Check if it is already installed before trying to install again
        print_info(f"Checking if MuscleMap is already installed in '{env_name}'...")
        verify = _micromamba_run(env_name, "mm_segment", "-h", timeout=120)
        if verify.returncode == 0:
            print_success("MuscleMap is already installed and working.")
            return True
            
        return install_musclemap_in_env(repo_path, env_name)

    print_warning("MuscleMap not found at src/MuscleMap.")

    if not Confirm.ask("Clone MuscleMap from GitHub automatically?", default=True):
        print_warning("MuscleMap skipped. Muscle segmentation may not work.")
        return False

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    if not _clone_musclemap(repo_path):
        return False

    return install_musclemap_in_env(repo_path, env_name)