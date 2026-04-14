"""
__main__.py -- Entry point for ``python -m runner``.

Supports an optional ``--input`` / ``-i`` argument that lets the user
specify a NIfTI file or DICOM directory to process instead of relying on
the default data/input scan.
"""

import argparse

from .preflight import main as preflight_main


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m runner",
        description="MSK Pipeline: medical image segmentation, meshing, and biomechanical modelling.",
    )
    parser.add_argument(
        "--input", "-i",
        metavar="PATH",
        default=None,
        help=(
            "Path to a NIfTI file (.nii / .nii.gz), RAW file (.raw), "
            "or DICOM directory to process.  When omitted the pipeline "
            "scans the configured input directory (default: data/input)."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    preflight_main(input_path=args.input)
