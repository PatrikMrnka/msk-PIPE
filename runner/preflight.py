"""
preflight.py – Orchestrates all pre-flight checks in order.
This is the main entry point for the pre-flight check phase. It performs the following steps:
1. Loads persisted user settings and main config.
2. Detects GPU availability and updates settings/config accordingly.
3. Checks for micromamba and sets up conda environments for TotalSegmentator and MuscleMap.
4. Checks for Muscle Wrapping 2.0 and exposes OpenSim DLLs to PATH for MATLAB.
5. Checks for MATLAB and OpenSim API availability.
6. Checks for MSK-STAPLE availability.
7. Checks for MuscleMap setup and availability.
8. Checks for mask2stl C++ binary availability.
9. Checks for extract_attachments C++ binary availability.
10. Prompts user to select input data format if not already set.
11. Saves any updated settings/config.
12. Hands off to the main pipeline runner.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from rich.prompt import Prompt

from . import constants as C
from .config_io import load_config, save_config
from .micromamba import check_micromamba
from .system import check_gpu
from .ui import console, print_fatal, print_header, print_section, print_info

# Domain checks (each lives in its own module)
from .external_tools import (
    check_muscle_wrapping,
    find_staple,
    compile_mask_to_mesh,
    compile_extract_attachments,
)
from .matlab import check_matlab
from .musclemap import check_and_setup_musclemap
from .pipeline import run_pipeline

# ── Input-format prompt ────────────────────────────────────────────────────────

_FORMAT_MAP = {"1": "auto", "2": "nifti", "3": "dicom", "4": "raw"}


def _ask_input_format() -> str:
    print_section("Select input data format")
    console.print("1) auto  2) nifti  3) dicom  4) raw")
    val = Prompt.ask("Enter choice (1-4)", choices=list(_FORMAT_MAP), default="1")
    return _FORMAT_MAP[val]


# ── Musclemap env name derivation ─────────────────────────────────────────────


def _musclemap_env_name(has_gpu: bool) -> str:
    return C.MUSCLEMAP_ENV_GPU if has_gpu else C.MUSCLEMAP_ENV_CPU


# ── Preflight abort helper ────────────────────────────────────────────────────


def _abort(reason: str) -> None:
    print_fatal("❌ Pre-flight failed: " + reason)
    sys.exit(1)


# ── Main entry point ──────────────────────────────────────────────────────────


def main(input_path: str | None = None) -> None:
    """Run all pre-flight checks and hand off to the pipeline.

    Parameters
    ----------
    input_path:
        Optional explicit input file or directory provided via ``--input``.
        When set, it is stored in ``config["paths"]["input_path"]`` so the
        Snakefile can pick it up.
    """
    print_header()

    # 1. Load persisted state
    C.CONFIG_DIR.mkdir(exist_ok=True)
    config = load_config(C.MAIN_CONFIG_PATH)
    user_settings = config.setdefault("user_settings", {})
    paths = config.setdefault("paths", {})

    # Store explicit input path (if provided via CLI).
    if input_path:
        paths["input_path"] = str(Path(input_path).resolve())

    # Migrate paths and env_file_hashes if they exist in user_settings
    for path_key in ["muscle_wrapping_path", "staple_path", "mask_to_mesh_path", "vtk_path", "extract_attachments_path"]:
        if path_key in user_settings:
            val = user_settings.pop(path_key)
            if val:
                paths[path_key] = val

    if "env_file_hashes" in user_settings:
        config["env_file_hashes"] = user_settings.pop("env_file_hashes")

    # Handle skip preflight checks early exit
    if user_settings.get("skip_preflight_checks"):
        print_info("Skipping pre-flight checks as requested.")
        mw_path = paths.get("muscle_wrapping_path")
        if mw_path:
            bin_dir = Path(mw_path) / "ExternalLibs" / "OpenSim" / "Bin" / "bin"
            if bin_dir.exists():
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

        if C.MICROMAMBA_EXE.exists():
            os.environ["PATH"] = str(C.MICROMAMBA_EXE.parent) + os.pathsep + os.environ["PATH"]

        save_config(config, C.MAIN_CONFIG_PATH)
        run_pipeline(user_settings, config)
        return

    # 2. GPU detection → drives all env/yaml selection
    has_gpu = check_gpu()
    user_settings["has_gpu"] = has_gpu
    config.setdefault("snakemake_env", {}).update(
        totalseg="env_totalseg_gpu.yaml" if has_gpu else "env_totalseg_cpu.yaml",
        musclemap="env_musclemap_gpu.yaml" if has_gpu else "env_musclemap_cpu.yaml",
    )

    # 3. Micromamba + conda environments
    ok, config = check_micromamba(config, has_gpu=has_gpu)
    if not ok:
        _abort("Micromamba / environment setup failed.")

    # 4. Muscle Wrapping 2.0
    mw_path = check_muscle_wrapping(paths)
    if not mw_path:
        _abort("Muscle Wrapping is not available.")

    # Expose OpenSim DLLs to PATH for MATLAB
    bin_dir = Path(mw_path) / "ExternalLibs" / "OpenSim" / "Bin" / "bin"
    if bin_dir.exists():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

    # 5. MATLAB + OpenSim API
    if not check_matlab(mw_path):
        _abort("MATLAB / OpenSim check failed.")

    # 6. MSK-STAPLE
    if not find_staple(paths):
        _abort("MSK-STAPLE path check failed.")

    # 7. MuscleMap
    if not check_and_setup_musclemap(_musclemap_env_name(has_gpu)):
        _abort("MuscleMap setup / check failed.")

    # 8. mask_to_mesh C++ binary
    if not compile_mask_to_mesh(paths):
        _abort("mask_to_mesh is not available. Pipeline will not start.")

    # 9. extract_attachments C++ binary
    if not compile_extract_attachments(paths):
        _abort("extract_attachments is not available. Pipeline will not start.")

    # 10. Input format
    if not user_settings.get("input_format"):
        user_settings["input_format"] = _ask_input_format()

    # 11. Persist state once (not scattered across the function)
    save_config(config, C.MAIN_CONFIG_PATH)

    print_section("MSK-PIPE Pre-flight completed.")

    # 12. Hand off to pipeline runner
    run_pipeline(user_settings, config)


# ── __main__.py equivalent (can also live as runner/__main__.py) ──────────────

if __name__ == "__main__":
    main()
