"""
run_totalsegmentator.py
~~~~~~~~~~~~~~~~~~~~~~~
Run TotalSegmentator and write masks to a folder.

Supports MR and CT models, and allows segmenting specific ROIs (e.g. bones).

Usage
-----
    python run_totalsegmentator.py \
        input.nii.gz \
        --output-dir output_masks/ \
        --model ct \
        --device cpu
"""

import argparse
import sys
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step

from totalsegmentator.python_api import totalsegmentator
from totalsegmentator.map_to_binary import class_map


def run_totalsegmentator(
    input_nii: Path,
    output_dir: Path,
    device: str,
    fast: bool,
    model: str,
    roi_subset: list[str] | None = None,
) -> None:
    in_path = input_nii.resolve()
    if not in_path.exists():
        print_error(f"Input not found: {in_path}")
        sys.exit(1)

    out_dir = output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if roi_subset:
        requested = roi_subset
    else:
        requested = [
            "hip_left",
            "hip_right",
            "sacrum",
            "femur_left",
            "femur_right",
            "tibia",
            "fibula"
        ]

    if model == "mr":
        rois_total = [r for r in requested if r in class_map["total_mr"].values()]
        rois_append = [
            r for r in requested if r in class_map["appendicular_bones_mr"].values()
        ]
        appendicular_map_key = "appendicular_bones_mr"
        
        # Add variables for task names
        task_total = "total_mr"
        task_append = "appendicular_bones_mr"
        
        print_info("Using MR model.")
    elif model =="ct":
        rois_total = [r for r in requested if r in class_map["total"].values()]
        rois_append = [
            r for r in requested if r in class_map["appendicular_bones"].values()
        ]
        appendicular_map_key = "appendicular_bones"
        
        # Variables for CT tasks
        task_total = "total"
        task_append = "appendicular_bones"
        
        print_info("Using CT model.")

    print_info(f"Input: {in_path}")
    print_info(f"Output: {out_dir}")
    print_info(f"ROIs total: {', '.join(rois_total) or '-'}")
    print_info(f"ROIs appendicular: {', '.join(rois_append) or '-'}")

    if rois_total:
        totalsegmentator(
            input=str(in_path),
            output=str(out_dir),
            task=task_total,
            fast=bool(fast),
            device=device,
            roi_subset=rois_total,
        )

    if rois_append:
        totalsegmentator(
            input=str(in_path),
            output=str(out_dir),
            task=task_append, # Dynamic variable
            fast=bool(fast),
            device=device,
        )

        # Remove labels produced by appendicular_bones that are not requested.
        for label in class_map[appendicular_map_key].values():
            p = out_dir / f"{label}.nii.gz"
            if p.exists() and label not in rois_append:
                try:
                    p.unlink()
                except OSError:
                    pass

    print_success("TotalSegmentator step finished.")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run TotalSegmentator and write masks to a folder."
    )
    p.add_argument("input_nii", help="Path to input .nii or .nii.gz file")
    p.add_argument(
        "--output-dir", required=True, help="Directory where masks are written"
    )
    p.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    p.add_argument("--fast", action="store_true")
    p.add_argument("--model", choices=["mr", "ct", "muscle"], required=True)
    p.add_argument("--roi-subset", nargs="+", help="Space-separated list of ROIs to segment", default=None)
    return p


def main() -> None:
    args = build_argparser().parse_args()
    run_totalsegmentator(
        input_nii=Path(args.input_nii),
        output_dir=Path(args.output_dir),
        device=args.device,
        fast=bool(args.fast),
        model=args.model,
        roi_subset=args.roi_subset,
    )


if __name__ == "__main__":
    main()
