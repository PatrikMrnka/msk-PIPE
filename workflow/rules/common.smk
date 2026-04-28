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

# Bone masks expected from TotalSegmentator (after internal renaming).
BONE_MASKS = [
    "hip_left",
    "hip_right",
    "sacrum",
    "femur_left",
    "femur_right",
    "tibia",
    "fibula",
]


# Muscle topology and labels from config/muscle_topology.json.
with open("config/muscle_topology.json", encoding="utf-8") as f:
    TOPOLOGY = json.load(f)

MUSCLE_LABELS = [roles["label"] for roles in TOPOLOGY.values()]


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


def mask_to_mesh_bin():
    """Return the platform-appropriate path to the mask_to_mesh binary."""
    if os.name == "nt":
        return "src/cpp/build/bin/Release/mask_to_mesh.exe"
    return "src/cpp/build/bin/mask_to_mesh"


def extract_attachments_bin():
    """Return the platform-appropriate path to the extract_attachments binary."""
    if os.name == "nt":
        return "src/cpp/build/bin/Release/extract_attachments.exe"
    return "src/cpp/build/bin/extract_attachments"
