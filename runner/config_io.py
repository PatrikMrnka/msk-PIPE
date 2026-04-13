"""
config_io.py – Load and save config.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import constants as C
from .ui import print_success, print_warning


def load_config(path: Path) -> dict:
    """Return config dict from *path*, or default skeleton if missing/invalid."""
    default: dict = {
        "snakemake_env": {},
        "paths": {
            "muscle_wrapping_path": str(C.MUSCLE_WRAPPING_DEFAULT),
            "mask_to_mesh_path": str(C.MASK_TO_MESH_DEFAULT_DIR.resolve()),
        },
    }
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("snakemake_env", {})
            data.setdefault("user_settings", {})
            data.setdefault("paths", {})
            data["paths"].setdefault(
                "muscle_wrapping_path", str(C.MUSCLE_WRAPPING_DEFAULT)
            )
            data["paths"].setdefault(
                "mask_to_mesh_path", str(C.MASK_TO_MESH_DEFAULT_DIR.resolve())
            )
            print_success("Existing config.json loaded.")
            return data
    except Exception as exc:
        print_warning(f"Failed to load {path}: {exc}")
    return default


def save_config(config: dict, path: Path) -> None:
    """Persist *config* to *path* (JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    print_success(f"config.json written to {path}.")
