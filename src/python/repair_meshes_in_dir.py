"""
Repair all STL meshes from a directory and write repaired meshes to another directory.
"""

import argparse
import sys
from pathlib import Path

import pymeshlab

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from runner.ui import print_info, print_success, print_warning
except ImportError:
    def print_info(msg):
        print(f"[INFO] {msg}")

    def print_success(msg):
        print(f"[SUCCESS] {msg}")

    def print_warning(msg):
        print(f"[WARNING] {msg}")


def repair_mesh(input_path: Path, output_path: Path) -> None:
    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(input_path))
    ms.meshing_repair_non_manifold_edges()
    ms.meshing_repair_non_manifold_vertices()
    ms.meshing_remove_unreferenced_vertices()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ms.save_current_mesh(str(output_path))


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair all .stl meshes in a directory.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_argparser().parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print_warning(f"Input directory not found: {input_dir}")
        return 1

    meshes = sorted(input_dir.glob("*.stl"))
    if not meshes:
        print_warning(f"No .stl files found in {input_dir}")
        return 1

    repaired_count = 0
    for mesh_path in meshes:
        out_path = output_dir / mesh_path.name
        print_info(f"Repairing merged mesh: {mesh_path.name}")
        repair_mesh(mesh_path, out_path)
        repaired_count += 1

    print_success(f"Repaired {repaired_count} merged bone mesh(es) into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
