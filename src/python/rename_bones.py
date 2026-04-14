"""
rename_bones.py -- Rename bone mesh files to STAPLE-compatible names.

Maps TotalSegmentator naming conventions to the names expected by MSK-STAPLE.
For example:
    femur_left.stl  -> femur_l.stl
    hip_left.stl    -> pelvis_no_sacrum.stl  (pelvis has no side suffix)

Usage:
    python rename_bones.py --input-dir bone_models/ --output-dir bone_models_renamed/
"""

import argparse
import shutil
import sys
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import print_info, print_success

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

# Names that never receive a _l / _r suffix.
STAPLE_SIDELESS = {"pelvis_no_sacrum"}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def staple_name(stem: str) -> str:
    """Map a TotalSegmentator bone stem to its STAPLE-compatible name."""
    s = stem.lower()

    # Detect anatomical side.
    if "left" in s or s.endswith("_l") or "_left_" in s:
        side = "_l"
    elif "right" in s or s.endswith("_r") or "_right_" in s:
        side = "_r"
    else:
        side = ""

    # Match against the name map.
    for keyword, staple_base in STAPLE_NAME_MAP.items():
        if keyword in s:
            if staple_base in STAPLE_SIDELESS:
                return staple_base
            return staple_base + side

    # Unrecognised name: keep the original.
    return stem


def rename_bones(input_dir: Path, output_dir: Path) -> None:
    """Copy all .stl files from *input_dir* to *output_dir* with STAPLE names."""
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for src in sorted(input_dir.glob("*.stl")):
        new_name = staple_name(src.stem) + ".stl"
        dst = output_dir / new_name
        print_info(f"[rename] {src.name} -> {new_name}")
        shutil.copy2(src, dst)
        count += 1

    print_success(f"Renamed {count} bone mesh(es).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename bone meshes to STAPLE-compatible names."
    )
    parser.add_argument("--input-dir", required=True, help="Input directory with bone .stl files.")
    parser.add_argument("--output-dir", required=True, help="Output directory for renamed files.")
    args = parser.parse_args()

    rename_bones(Path(args.input_dir), Path(args.output_dir))


if __name__ == "__main__":
    main()
