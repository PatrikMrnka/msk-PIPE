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

STAPLE_REPO_URL = "https://github.com/modenaxe/msk-STAPLE.git"
STAPLE_DEFAULT_DIR = SRC_DIR / "STAPLE"


# Fast-RNRR (attachment_extraction.method = "fast_rnrr"), prebuilt Windows binaries
# from https://github.com/dannystefy/muscle-attachment-registration pinned to a commit.
# Fast-RNRR (Yao et al., CVPR 2020) is patented - research use only.
FAST_RNRR_DEFAULT_EXE = SRC_DIR / "FAST_RNRR" / "Fast_RNRR.exe"
FAST_RNRR_COMMIT = "2604a17d00af1033e1015960ca52f204ab4de4af"
FAST_RNRR_BASE_URL = (
    "https://raw.githubusercontent.com/dannystefy/muscle-attachment-registration"
    f"/{FAST_RNRR_COMMIT}/win/"
)
FAST_RNRR_FILES = {
    "Fast_RNRR.exe": "3eff52e596cac351f5370b2e9f083661dcbbbe0de33033beff83b70ed4c76082",
    "OpenMeshCore.dll": "d9f710de4be3cf692aa6f9af70384c623ba923061d74922d1bd5e54ae05b6723",
}

CPP_TOOLS_DEFAULT_DIR = SRC_DIR / "cpp"
MUSCLE_WRAPPING_DEFAULT = SRC_DIR / "MW2" / "Build"

# ── Python executable inside a conda env ──────────────────────────────────────
PYTHON_REL = "python.exe" if platform.system() == "Windows" else "bin/python"

# ── Micromamba download URL (Windows only for now) ────────────────────────────
MICROMAMBA_DEFAULT_VERSION = "2.6.0-0"
# resolving this issue https://github.com/mamba-org/mamba/issues/4276

# Template for a release download URL. We will substitute the release tag
# (e.g. "v2.6.0-0" or "2.6.0-0") into `{tag}`. Keep a fallback to the
# `latest` download URL for backwards compatibility.
MICROMAMBA_WIN_URL_TEMPLATE = (
    "https://github.com/mamba-org/micromamba-releases"
    "/releases/download/{tag}/micromamba-win-64.tar.bz2"
)

MICROMAMBA_WIN_URL = (
    "https://github.com/mamba-org/micromamba-releases"
    "/releases/latest/download/micromamba-win-64.tar.bz2"
)
