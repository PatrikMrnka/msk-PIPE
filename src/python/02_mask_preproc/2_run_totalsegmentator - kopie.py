import argparse
from pathlib import Path
import sys

from totalsegmentator.python_api import totalsegmentator
from totalsegmentator.map_to_binary import class_map


def run_totalsegmentator(
    input_nii: Path,
    output_dir: Path,
    device: str,
    fast: bool,
    model: str,
) -> None:
    in_path = input_nii.resolve()
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    requested = [
        "hip_left",
        "hip_right",
        "femur_left",
        "femur_right",
        "tibia",
        "fibula",
    ]

    if model == "mr":
        rois_total = [r for r in requested if r in class_map["total_mr"].values()]
        rois_append = [
            r for r in requested if r in class_map["appendicular_bones_mr"].values()
        ]
        appendicular_map_key = "appendicular_bones_mr"
        print("Using MR model.")
    else:
        rois_total = [r for r in requested if r in class_map["total"].values()]
        rois_append = [
            r for r in requested if r in class_map["appendicular_bones"].values()
        ]
        appendicular_map_key = "appendicular_bones"
        print("Using CT model.")

    print(f"Input: {in_path}")
    print(f"Output: {out_dir}")
    print(f"ROIs total: {', '.join(rois_total) or '-'}")
    print(f"ROIs appendicular: {', '.join(rois_append) or '-'}")

    if rois_total:
        totalsegmentator(
            input=str(in_path),
            output=str(out_dir),
            task="total",
            roi_subset=rois_total,
            fast=bool(fast),
            device=device,
        )

    if rois_append:
        totalsegmentator(
            input=str(in_path),
            output=str(out_dir),
            task="appendicular_bones",
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

    # Normalize naming expected by the downstream steps.
    rename = {"femur_left": "femur_l", "femur_right": "femur_r"}
    for old_name, new_name in rename.items():
        old_path = out_dir / f"{old_name}.nii.gz"
        new_path = out_dir / f"{new_name}.nii.gz"
        if old_path.exists() and not new_path.exists():
            try:
                old_path.rename(new_path)
            except OSError:
                pass

    print("TotalSegmentator step finished.")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run TotalSegmentator and write masks to a folder.")
    p.add_argument("input_nii", help="Path to input .nii or .nii.gz file")
    p.add_argument("--output-dir", required=True, help="Directory where masks are written")
    p.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    p.add_argument("--fast", action="store_true")
    p.add_argument("--model", choices=["mr", "ct"], required=True)
    return p


def main() -> None:
    args = build_argparser().parse_args()
    run_totalsegmentator(
        input_nii=Path(args.input_nii),
        output_dir=Path(args.output_dir),
        device=args.device,
        fast=bool(args.fast),
        model=args.model,
    )


if __name__ == "__main__":
    main()
