"""
constants.py – All paths and magic strings in one place.
"""

from pathlib import Path
import platform

# ── Directories ───────────────────────────────────────────────────────────────
CONFIG_DIR = Path("config")
ENVS_DIR = Path("envs")
BIN_DIR = Path("bin")
SRC_DIR = Path("src")
REPORTS_DIR = Path("data/output/reports")

# ── Config files ──────────────────────────────────────────────────────────────
MAIN_CONFIG_PATH = CONFIG_DIR / "config.json"

# ── Micromamba binary ─────────────────────────────────────────────────────────
MICROMAMBA_EXE = (
    BIN_DIR / "micromamba.exe"
    if platform.system() == "Windows"
    else BIN_DIR / "micromamba"
)

# ── Conda environment definitions ─────────────────────────────────────────────
BASE_ENVS = {
    "msk_base": CONFIG_DIR / "env_base.yaml",
    "msk_totalseg_cpu": CONFIG_DIR / "env_totalseg_cpu.yaml",
    "msk_totalseg_gpu": CONFIG_DIR / "env_totalseg_gpu.yaml",
}

MUSCLEMAP_ENV_GPU = "msk_musclemap_gpu"
MUSCLEMAP_ENV_CPU = "msk_musclemap_cpu"
MUSCLEMAP_YAML_GPU = CONFIG_DIR / "env_musclemap_gpu.yaml"
MUSCLEMAP_YAML_CPU = CONFIG_DIR / "env_musclemap_cpu.yaml"

# ── External tool defaults ────────────────────────────────────────────────────
MUSCLEMAP_REPO_URL = "https://github.com/MuscleMap/MuscleMap.git"
MUSCLEMAP_DEFAULT_DIR = SRC_DIR / "MuscleMap"
STAPLE_DEFAULT_DIR = SRC_DIR / "STAPLE"
MASK_TO_MESH_DEFAULT_DIR = SRC_DIR / "cpp" / "mask_to_mesh"
EXTRACT_ATTACHMENTS_DEFAULT_DIR = SRC_DIR / "cpp" / "extract_attachments"
MUSCLE_WRAPPING_DEFAULT = SRC_DIR / "MW2" / "Build"

# ── Python executable inside a conda env ──────────────────────────────────────
PYTHON_REL = "python.exe" if platform.system() == "Windows" else "bin/python"

# ── Micromamba download URL (Windows only for now) ────────────────────────────
MICROMAMBA_WIN_URL = (
    "https://github.com/mamba-org/micromamba-releases"
    "/releases/latest/download/micromamba-win-64.tar.bz2"
)
