# common.smk -- Shared constants, helpers, and configuration for the pipeline.
#
# Every other .smk file that is included by the top-level Snakefile has access
# to the symbols defined here because Snakemake `include` shares the namespace.

import os
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

IN_DIR = config.get("paths", {}).get("input_dir", "data/input")
BASE_OUT_DIR = config.get("paths", {}).get("output_dir", "data/output")
MW_PATH_DIR = config.get("paths", {}).get("muscle_wrapping_path", "src/MW2/Build")
STAPLE_PATH_DIR = config.get("paths", {}).get("staple_path", "src/STAPLE")

# RUN_ID is computed by runner/pipeline.py *before* Snakemake is invoked and
# passed via `--config run_id=run_N`.  This avoids side-effects (directory
# creation, sequence number detection) during the parse phase, which would
# break --dry-run and cause inconsistencies after partial failures.
RUN_ID = config.get("run_id", "run_1")
OUT_DIR = os.path.join(BASE_OUT_DIR, RUN_ID)
BONE_STAPLE_DIR = os.path.join(OUT_DIR, "bones_STAPLE")

# ---------------------------------------------------------------------------
# Known output labels
# ---------------------------------------------------------------------------

BONE_MASKS = [
    "hip_left",
    "hip_right",
    "sacrum",
    "femur_left",
    "femur_right",
    "tibia",
    "fibula",
]

MUSCLE_MASKS_TOTALSEGMENTATOR = [
    "iliopsoas_left",
    "iliopsoas_right",
    "gluteus_maximus_left",
    "gluteus_maximus_right",
    "gluteus_medius_left",
    "gluteus_medius_right",
    "gluteus_minimus_left",
    "gluteus_minimus_right",
]


# Muscle topology and labels from config/muscle_topology.json.
with open("config/muscle_topology.json", encoding="utf-8") as f:
    TOPOLOGY = json.load(f)

MUSCLE_LABELS = [roles["label"] for roles in TOPOLOGY.values()]

if config.get("user_settings", {}).get("muscle_segmentator", "musclemap") == "totalsegmentator":
    ts_supported = [
        "iliacus_l", "iliacus_r",
        "gluteus_maximus_l", "gluteus_maximus_r",
        "gluteus_medius_l", "gluteus_medius_r",
        "gluteus_minimus_l", "gluteus_minimus_r",
    ]
    MUSCLE_LABELS = [m for m in MUSCLE_LABELS if m in ts_supported]



# ---------------------------------------------------------------------------
# STAPLE name mapping
# ---------------------------------------------------------------------------

# Key: substring that must appear in the filename (lowercase).
# Value: STAPLE base name (side suffix _l/_r is appended automatically).
STAPLE_NAME_MAP = {
    "pelvis": "pelvis_no_sacrum",
    "femur": "femur",
    "tibia": "tibia",
    "fibula": "fibula",
    "talus": "talus",
    "calcaneus": "calcn",
    "calcn": "calcn",
    "toes": "toes",
    "metatarsals": "toes",
}
STAPLE_SIDELESS = {"pelvis_no_sacrum"}


# ---------------------------------------------------------------------------
# Helper: resolve the Python executable inside a conda environment
# ---------------------------------------------------------------------------


def get_py_exe(env_name):
    """Return the path to the Python binary inside a named conda env."""
    exe = (
        f"envs/{env_name}/python.exe"
        if os.name == "nt"
        else f"envs/{env_name}/bin/python"
    )
    return os.path.normpath(exe)


def totalseg_env_name():
    """Derive the conda env name from the totalseg YAML filename in config."""
    return (
        config["snakemake_env"]["totalseg"].replace("env_", "msk_").replace(".yaml", "")
    )


def musclemap_env_name():
    """Derive the conda env name from the musclemap YAML filename in config."""
    return (
        config["snakemake_env"]["musclemap"]
        .replace("env_", "msk_")
        .replace(".yaml", "")
    )


def _cpp_tool_default_bin(tool_name):
    """Build default executable path from config.paths.cpp_tools_path."""
    cpp_root = config.get("paths", {}).get("cpp_tools_path", "src/cpp")
    if os.name == "nt":
        return os.path.normpath(
            str(Path(cpp_root) / "build" / "bin" / "Release" / f"{tool_name}.exe")
        )
    return os.path.normpath(str(Path(cpp_root) / "build" / "bin" / tool_name))


def _cpp_tool_from_config(path_key, tool_name):
    """Resolve optional explicit binary path from config.paths[path_key]."""
    raw = config.get("paths", {}).get(path_key, "")
    if not raw:
        return ""

    candidate = Path(raw)
    expected = f"{tool_name}.exe" if os.name == "nt" else tool_name

    # If config points to a directory, append the expected executable name.
    if candidate.is_dir():
        return os.path.normpath(str(candidate / expected))

    # Accept only explicit executable-like paths.
    if candidate.name.lower() == expected.lower():
        return os.path.normpath(str(candidate))

    return ""


def mask_to_mesh_bin():
    """Return config-aware path to the mask_to_mesh binary."""
    return _cpp_tool_from_config("mask_to_mesh_path", "mask_to_mesh") or _cpp_tool_default_bin("mask_to_mesh")


def extract_attachments_bin():
    """Return config-aware path to the extract_attachments binary."""
    return _cpp_tool_from_config("extract_attachments_path", "extract_attachments") or _cpp_tool_default_bin("extract_attachments")
