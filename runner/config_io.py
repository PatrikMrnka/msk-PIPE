"""
config_io.py – Load and save config.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import constants as C
from .ui import print_success, print_warning


def update_dict_recursive(d: dict, u: dict) -> dict:
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = update_dict_recursive(d.get(k, {}), v)
        else:
            d.setdefault(k, v)
    return d

def load_config(path: Path) -> dict:
    """Return config dict from *path*, or default skeleton if missing/invalid."""
    default: dict = {
        "user_settings": {
            "auto_run_pipeline": True,
            "generate_snakemake_report": True,
            "generate_summary": True,
            "generate_dag": True,
            "generate_rulegraph": True,
            "enable_benchmarking": True,
            "input_format": "nifti",
            "skip_preflight_checks": False,
            "snakemake_cores": "all",
            "snakemake_latency_wait": 30,
            "muscle_segmentator": "musclemap"
        },
        "raw_input": {
            "shape": "381x245x1120"
        },
        "paths": {
            "input_dir": "data/input",
            "output_dir": "data/output",
            "extract_attachments_path": "src/cpp/extract_attachments",
            "mask_to_mesh_path": "src/cpp/mask_to_mesh",
            "muscle_wrapping_path": str(C.MUSCLE_WRAPPING_DEFAULT),
            "staple_path": "src\\STAPLE",
            "vtk_path": "src\\MW2\\ExternalLibs\\VTK\\Bin\\lib\\cmake\\vtk-9.4",
            "input_path": "data/input/ct/ct.nii.gz",
            "cpp_tools_path": str(C.CPP_TOOLS_DEFAULT_DIR.resolve())
        },
        "totalsegmentator": {
            "fast": False,
            "device": "gpu",
            "model": "ct"
        },
        "bone_preprocessing": {
            "min_voxels": 2000,
            "opening_kernel": 1,
            "closing_kernel": 1,
            "fill_holes": True,
            "keep_largest": True,
            "inplace": True
        },
        "bone_to_mesh": {
            "smooth_iterations": 40,
            "passband": 0.01,
            "target_reduction": 0.8
        },
        "muscle_preprocessing": {
            "min_voxels": 1000,
            "opening_kernel": 1,
            "closing_kernel": 1,
            "fill_holes": True,
            "keep_largest": True,
            "bone_subtraction_dilation_radius": 0
        },
        "muscle_to_mesh": {
            "smooth_iterations": 30,
            "passband": 0.01,
            "target_reduction": 0.8
        },
        "attachment_extraction": {
            "method": "atlas_based",
            "lhdl_bones_dir": "data/DATA_LHDL/bones",
            "lhdl_muscles_dir": "data/DATA_LHDL/muscles",
            "threshold_mm": 5.0,
            "clip_fraction": 0.22
        },
        "muscle_wrapping": {
            "kinematics_algorithm": "luca",
            "num_lines": 100,
            "line_res": 15
        },
        "muscle_map": {
            "spatial_overlap": 90,
            "default_model": "default",
                    "labels": {
            "adductor_brevis_l": 7221,
            "adductor_brevis_r": 7222,
            "adductor_longus_l": 7211,
            "adductor_longus_r": 7212,
            "adductor_magnus_l": 7201,
            "adductor_magnus_r": 7202,
            "biceps_femoris_l": 7181,
            "biceps_femoris_r": 7182,
            "gluteus_maximus_l": 6121,
            "gluteus_maximus_r": 6122,
            "gluteus_medius_l": 6111,
            "gluteus_medius_r": 6112,
            "gluteus_minimus_l": 6101,
            "gluteus_minimus_r": 6102,
            "gracilis_l": 7151,
            "gracilis_r": 7152,
            "iliacus_l": 6141,
            "iliacus_r": 6142,
            "pectineus_l": 6191,
            "pectineus_r": 6192,
            "piriformis_l": 6181,
            "piriformis_r": 6182,
            "rectus_femoris_l": 7131,
            "rectus_femoris_r": 7132,
            "sartorius_l": 7141,
            "sartorius_r": 7142,
            "semimembranosus_l": 7161,
            "semimembranosus_r": 7162,
            "semitendinosus_l": 7171,
            "semitendinosus_r": 7172,
            "tensor_fasciae_latae_l": 6131,
            "tensor_fasciae_latae_r": 6132,
            "obturator_internus_l": 6201,
            "obturator_internus_r": 6202,
            "obturator_externus_l": 6211,
            "obturator_externus_r": 6212,
            "vastus_lateralis_l": 7101,
            "vastus_lateralis_r": 7102,
            "vastus_medialis_l": 7121,
            "vastus_medialis_r": 7122,
            "vastus_intermedius_l": 7111,
            "vastus_intermedius_r": 7112
        }
        },
        "env_file_hashes": {},
        "snakemake_env": {}
    }
    
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            update_dict_recursive(data, default)
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
