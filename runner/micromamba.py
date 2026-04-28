"""
micromamba.py – All Micromamba / conda-environment logic.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from rich.prompt import Confirm

from .constants import (
    BIN_DIR, ENVS_DIR,
    MICROMAMBA_EXE, MICROMAMBA_WIN_URL,
    BASE_ENVS, MUSCLEMAP_ENV_CPU, MUSCLEMAP_ENV_GPU,
    MUSCLEMAP_YAML_CPU, MUSCLEMAP_YAML_GPU,
)
from .system import compute_file_hash
from .ui import console, print_check, print_error, print_info, print_step, print_subprocess_error, print_success, print_warning


# ── Internal helpers ──────────────────────────────────────────────────────────

def _env_map(has_gpu: bool) -> dict[str, Path]:
    """Return {env_name: yaml_path} dict for the current GPU configuration."""
    musclemap_name = MUSCLEMAP_ENV_GPU if has_gpu else MUSCLEMAP_ENV_CPU
    musclemap_yaml = MUSCLEMAP_YAML_GPU if has_gpu else MUSCLEMAP_YAML_CPU
    return {**BASE_ENVS, musclemap_name: musclemap_yaml}


def _python_exe(env_path: Path) -> Path:
    rel = "python.exe" if platform.system() == "Windows" else "bin/python"
    return env_path / rel


def _run_micromamba(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["micromamba", *args], capture_output=True, text=True
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_env_file_hashes(has_gpu: bool = False) -> dict[str, str | None]:
    """Return SHA-256 hashes for every environment YAML."""
    return {
        name: compute_file_hash(yaml_path)
        for name, yaml_path in _env_map(has_gpu).items()
        if yaml_path.exists()
    }


def install_micromamba() -> bool:
    """Download and install Micromamba into ./bin/ (Windows-only for now)."""
    print_check("Attempting automatic Micromamba installation")

    if platform.system() != "Windows":
        raise NotImplementedError(
            "Automatic Micromamba install is only implemented for Windows. "
            "Please install Micromamba manually: https://mamba.readthedocs.io"
        )

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = BIN_DIR / "micromamba.tar.bz2"

    try:
        urllib.request.urlretrieve(MICROMAMBA_WIN_URL, str(tmp_file))
        with tarfile.open(tmp_file, "r:bz2") as tar:
            tar.extractall(path=BIN_DIR)
        tmp_file.unlink(missing_ok=True)

        extracted = BIN_DIR / "Library" / "bin" / "micromamba.exe"
        if extracted.exists():
            import shutil as _shutil
            _shutil.copy2(extracted, MICROMAMBA_EXE)

        print_success(f"Micromamba installed to {MICROMAMBA_EXE}")
    except Exception as exc:
        print_error(f"Failed to install Micromamba: {exc}")
        return False

    os.environ["PATH"] = str(MICROMAMBA_EXE.parent) + os.pathsep + os.environ["PATH"]
    return True


def update_conda_envs(config: dict, has_gpu: bool = False) -> tuple[bool, dict]:
    """Create or update all required Micromamba environments (with change detection)."""
    print_check("Checking Micromamba environments")

    envs = _env_map(has_gpu)
    previous_hashes: dict = config.get("env_file_hashes", {})
    current_hashes = get_env_file_hashes(has_gpu)
    all_ok = True

    for env_name, yaml_path in envs.items():
        if not yaml_path.exists():
            print_error(f"Missing environment recipe: {yaml_path}")
            all_ok = False
            continue

        env_path  = (ENVS_DIR / env_name).resolve()
        env_exists = _python_exe(env_path).exists()
        prev_hash  = previous_hashes.get(env_name)
        curr_hash  = current_hashes.get(env_name)

        if not env_exists:
            print_step(f"Creating '{env_name}' from {yaml_path}...")
            result = _run_micromamba("create", "-p", str(env_path), "-f", str(yaml_path), "-y")
            action = "created"
        elif prev_hash and curr_hash and prev_hash != curr_hash:
            print_step(f"Updating '{env_name}' (YAML changed)...")
            result = _run_micromamba("env", "update", "-p", str(env_path), "-f", str(yaml_path), "-y")
            action = "updated"
        else:
            print_success(f"'{env_name}' is up-to-date.")
            if env_name == "msk_base":
                patch_snakemake_benchmark(env_path)
            continue

        if result.returncode == 0:
            print_success(f"'{env_name}' {action} successfully.")
            if env_name == "msk_base":
                patch_snakemake_benchmark(env_path)
        else:
            print_error(f"Error ({action}) '{env_name}' (code {result.returncode}):")
            if result.stderr:
                print_subprocess_error(result.stderr)
            all_ok = False

    config["env_file_hashes"] = current_hashes
    return all_ok, config


def patch_snakemake_benchmark(env_path: Path):
    """Automatically patch Snakemake benchmark.py on Windows to fix missing `pss` attribute."""
    if platform.system() != "Windows":
        return
    site_packages = env_path / "Lib" / "site-packages"
    benchmark_py = site_packages / "snakemake" / "benchmark.py"
    if not benchmark_py.exists():
        return
    
    content = benchmark_py.read_text(encoding="utf-8")
    # Patch `pss += meminfo.pss` -> `pss += getattr(meminfo, "pss", 0)`
    if 'pss += meminfo.pss' in content and 'getattr(meminfo, "pss", 0)' not in content:
        content = content.replace('pss += meminfo.pss', 'pss += getattr(meminfo, "pss", 0)')
        benchmark_py.write_text(content, encoding="utf-8")
        print_success("Patched snakemake/benchmark.py (missing `pss` on Windows fix)")


def check_micromamba(config: dict, has_gpu: bool = False) -> tuple[bool, dict]:
    """Ensure Micromamba is available and all envs are up-to-date."""
    print_check("Checking for Micromamba")

    if shutil.which("micromamba"):
        print_success("Micromamba found in PATH.")
    elif MICROMAMBA_EXE.exists():
        print_success(f"Micromamba found locally at {MICROMAMBA_EXE}.")
        os.environ["PATH"] = str(MICROMAMBA_EXE.parent) + os.pathsep + os.environ["PATH"]
    else:
        print_warning("Micromamba not found.")
        if not Confirm.ask("Install Micromamba automatically?", default=True):
            return False, config
        try:
            if not install_micromamba():
                return False, config
        except NotImplementedError as exc:
            print_error(str(exc))
            return False, config

    env_ok, config = update_conda_envs(config, has_gpu=has_gpu)
    if not env_ok:
        print_error("One or more environment checks failed.")
        return False, config

    return True, config