"""
run_extraction.py
~~~~~~~~~~~~~~~~~
Orchestrates the C++ extract_attachments binary using a muscle-topology JSON.

Groups tasks by bone so the locator is built ONCE per bone, then calls the
binary with the new batch CLI:

    extract_attachments <bone.obj> <threshold_mm> <clip_fraction> \\
        <muscle1.obj> <out1.vtk>  \\
        <muscle2.obj> <out2.vtk>  \\
        ...

Usage
-----
    python run_extraction.py \\
        --bones     data/temp/meshes_processed \\
        --muscles   data/temp/muscle_models \\
        --topology  config/muscle_topology.json \\
        --out-dir   data/temp/attachments \\
        --threshold 3.0 \\
        --clip-fraction 0.25 \\
        --cpp-bin   src/cpp/6_extract_attachments/build/Release/extract_attachments.exe
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Ensure runner/ and src/python/ are on the path regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step
from muscle_names import MUSCLE_NAME_TO_STEM

# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────

def find_obj(directory: Path, name: str) -> Path | None:
    """Return the first .obj file whose stem matches *name* (case-insensitive),
    or None if not found."""
    for ext in (".obj", ".OBJ"):
        candidate = directory / (name + ext)
        if candidate.exists():
            return candidate
            
    prefix = MUSCLE_NAME_TO_STEM.get(name)
    if prefix:
        for side in ("_r", "_l"):
            candidate = directory / (prefix + side + ".obj")
            if candidate.exists():
                return candidate

    # fallback: name may already be a filename
    for f in directory.glob("*.obj"):
        if f.stem.lower() == name.lower():
            return f
    return None


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run extract_attachments C++ binary grouped by bone."
    )
    p.add_argument(
        "--bones", required=True, help="Directory with processed bone meshes (.obj)."
    )
    p.add_argument(
        "--muscles", required=True, help="Directory with muscle meshes (.obj)."
    )
    p.add_argument(
        "--topology", required=True, help="Path to config/muscle_topology.json."
    )
    p.add_argument(
        "--out-dir", required=True, help="Directory to save output .vtk files."
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Distance threshold in mm (default: 3.0).",
    )
    p.add_argument(
        "--clip-fraction",
        type=float,
        default=0.25,
        help="Fraction to keep at each muscle end before clipping the middle (default: 0.25).",
    )
    p.add_argument(
        "--cpp-bin", required=True, help="Path to compiled extract_attachments binary."
    )
    return p


# ─────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────


def main() -> None:
    args = build_argparser().parse_args()

    bones_dir = Path(args.bones).resolve()
    muscles_dir = Path(args.muscles).resolve()
    out_dir = Path(args.out_dir).resolve()
    topology_p = Path(args.topology).resolve()
    cpp_bin = Path(args.cpp_bin).resolve()

    # ── Validation ────────────────────────────────────────────────
    if not cpp_bin.exists():
        print_error(f"C++ binary not found: {cpp_bin}")
        sys.exit(1)
    if not topology_p.exists():
        print_error(f"topology JSON not found: {topology_p}")
        sys.exit(1)
    if not bones_dir.is_dir():
        print_error(f"bones directory not found: {bones_dir}")
        sys.exit(1)
    if not muscles_dir.is_dir():
        print_error(f"muscles directory not found: {muscles_dir}")
        sys.exit(1)
    if not (0.0 < args.clip_fraction < 0.5):
        print_error(f"clip_fraction must be in (0, 0.5), got: {args.clip_fraction}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    with open(topology_p, encoding="utf-8") as fh:
        topology: dict[str, dict[str, str]] = json.load(fh)

    # ── Group tasks by bone ───────────────────────────────────────
    # Each task is: (muscle_name, role, bone_name)
    # role ∈ {"origin", "insertion"}
    # Output file: <MuscleN>_Ori.vtk  or  <MuscleN>_Ins.vtk
    #
    # bone_tasks[bone_name] = list of (muscle_path, output_vtk_path)
    bone_tasks: dict[str, list[tuple[Path, Path]]] = defaultdict(list)

    missing_muscles: list[str] = []

    for muscle_name, roles in topology.items():
        for role, bone_name in roles.items():
            suffix = "Ori" if role == "origin" else "Ins"
            muscle_path = find_obj(muscles_dir, muscle_name)

            if muscle_path is None:
                print_warning(
                    f"muscle mesh not found for '{muscle_name}' ({role}) – skipping."
                )
                missing_muscles.append(f"{muscle_name}/{role}")
                continue

            out_vtk = out_dir / f"{muscle_name}_{suffix}.vtk"
            bone_tasks[bone_name].append((muscle_path, out_vtk))

    if missing_muscles:
        print_warning(f"{len(missing_muscles)} muscle(s) were skipped (mesh not found):")
        for m in missing_muscles:
            print_info(f"       {m}")

    # ── Execute one C++ call per bone ─────────────────────────────
    total_bones = len(bone_tasks)
    success_bones = 0

    for bone_name, pairs in bone_tasks.items():
        bone_path = find_obj(bones_dir, bone_name)
        if bone_path is None:
            print_error(
                f"bone mesh not found for '{bone_name}' – skipping {len(pairs)} muscle(s)."
            )
            continue

        # Build the flat argument list:
        # [cpp_bin] [bone.obj] [threshold] [clip_fraction] [m1.obj] [out1.vtk] ...
        cmd = [str(cpp_bin), str(bone_path), str(args.threshold), str(args.clip_fraction)]
        for muscle_path, out_vtk in pairs:
            cmd += [str(muscle_path), str(out_vtk)]

        print_step(f"[bone] {bone_name}  ({len(pairs)} muscle(s))")
        print_info(f"  cmd: {' '.join(cmd[:6])} ...")

        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode == 0:
            success_bones += 1
        else:
            print_error(
                f"extract_attachments returned code {result.returncode} for bone '{bone_name}'"
            )

    status_msg = f"{success_bones}/{total_bones} bone groups processed successfully."
    if success_bones < total_bones:
        print_error(status_msg)
        sys.exit(1)
    else:
        print_success(status_msg)


if __name__ == "__main__":
    main()
