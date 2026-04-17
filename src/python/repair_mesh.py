"""
Repairs non-manifold mesh topology.
"""

import argparse
import sys
from pathlib import Path
import pymeshlab

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from runner.ui import print_info, print_success
except ImportError:
    def print_info(msg): print(f"[INFO] {msg}")
    def print_success(msg): print(f"[SUCCESS] {msg}")


def repair_mesh(input_path: Path, output_path: Path) -> None:
    ms = pymeshlab.MeshSet()
    
    ms.load_new_mesh(str(input_path))
    
    # 1. Rozpojení non-manifold hran (hrany sdílené >2 trojúhelníky)
    ms.meshing_repair_non_manifold_edges()
    
    # 2. Rozpojení non-manifold vrcholů (vrcholy spojující dvě jinak oddělené plochy)
    ms.meshing_repair_non_manifold_vertices()
    
    # 3. Odstranění "osamocených" vrcholů bez napojení na stěny
    ms.meshing_remove_unreferenced_vertices()
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ms.save_current_mesh(str(output_path))


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Repair non-manifold mesh topology.")
    p.add_argument("--input-mesh", type=Path, required=True)
    p.add_argument("--output-mesh", type=Path, required=True)
    return p


def main() -> None:
    args = _build_argparser().parse_args()
    print_info(f"Opravuji síť: {args.input_mesh.name}")
    repair_mesh(args.input_mesh, args.output_mesh)
    print_success(f"Opravená síť uložena: {args.output_mesh}")


if __name__ == "__main__":
    main()