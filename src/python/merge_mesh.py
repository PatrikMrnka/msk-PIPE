"""Generic mesh merging CLI."""

import argparse
import sys
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mesh_ops import merge_meshes


def main():
    parser = argparse.ArgumentParser(description="Generic mesh merge utility.")
    parser.add_argument(
        "--input-meshes",
        nargs="+",
        help="One or more input mesh files to merge.",
    )
    parser.add_argument(
        "--output-mesh",
        help="Output file for the merged mesh.",
    )
    args = parser.parse_args()

    if not merge_meshes(args.input_meshes, args.output_mesh):
        print("Mesh merging failed.", file=sys.stderr)
        return 1
    
    print("Mesh merging completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())