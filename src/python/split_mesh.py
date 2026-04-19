"""Generic mesh splitting CLI."""

import argparse
import sys
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mesh_ops import split_into_left_right_components


def main():
    parser = argparse.ArgumentParser(description="Generic left/right mesh split.")
    parser.add_argument(
        "--input-mesh",
        required=True,
        help="Input mesh to split into left and right components.",
    )
    parser.add_argument(
        "--left-output",
        required=True,
        help="Output file for the left-side mesh.",
    )
    parser.add_argument(
        "--right-output",
        required=True,
        help="Output file for the right-side mesh.",
    )
    args = parser.parse_args()

    if not split_into_left_right_components(
        args.input_mesh,
        args.left_output,
        args.right_output,
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())