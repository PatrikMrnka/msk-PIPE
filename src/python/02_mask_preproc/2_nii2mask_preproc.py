import argparse
import subprocess
import sys
from pathlib import Path


"""Backward-compatible wrapper around split preprocessing scripts.

The original monolithic workflow has been decomposed into:
- 2_run_totalsegmentator.py
- 2_clean_masks.py
"""


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Compatibility wrapper: runs TotalSegmentator and then mask cleaning. "
            "Use 2_run_totalsegmentator.py and 2_clean_masks.py directly for new workflows."
        )
    )
    p.add_argument("input_nii", help="Path to input .nii or .nii.gz file")
    p.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    p.add_argument("--fast", action="store_true")
    p.add_argument("--model", choices=["mr", "ct"], required=True)
    p.add_argument("--iso", type=float, default=0.5)
    p.add_argument("--min-voxels", type=int, default=2000)
    p.add_argument("--keep-largest", action="store_true")
    p.add_argument("--no-keep-largest", dest="keep_largest", action="store_false")
    p.set_defaults(keep_largest=True)
    p.add_argument("--opening", type=int, default=1)
    p.add_argument("--closing", type=int, default=1)
    p.add_argument("--fill-holes", action="store_true")
    p.add_argument("--fully-connected", action="store_true")
    p.add_argument("--inplace", action="store_true")
    return p


def main() -> None:
    args = build_argparser().parse_args()

    in_path = Path(args.input_nii).resolve()
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    base_dir = in_path.parent
    raw_dir = base_dir / "segmentations_raw"
    final_dir = base_dir / "segmentations"

    here = Path(__file__).resolve().parent
    seg_script = here / "2_run_totalsegmentator.py"
    clean_script = here / "2_clean_masks.py"

    py = sys.executable

    seg_cmd = [
        py,
        str(seg_script),
        str(in_path),
        "--output-dir",
        str(raw_dir),
        "--device",
        args.device,
        "--model",
        args.model,
    ]
    if args.fast:
        seg_cmd.append("--fast")

    subprocess.run(seg_cmd, check=True)

    clean_cmd = [
        py,
        str(clean_script),
        "--input-dir",
        str(raw_dir),
        "--output-dir",
        str(final_dir),
        "--labels",
        "femur_l",
        "femur_r",
        "hip_left",
        "hip_right",
        "--iso",
        str(args.iso),
        "--min-voxels",
        str(args.min_voxels),
        "--opening",
        str(args.opening),
        "--closing",
        str(args.closing),
    ]

    if args.keep_largest:
        clean_cmd.append("--keep-largest")
    else:
        clean_cmd.append("--no-keep-largest")

    if args.fill_holes:
        clean_cmd.append("--fill-holes")
    if args.fully_connected:
        clean_cmd.append("--fully-connected")
    if args.inplace:
        clean_cmd.append("--inplace")

    subprocess.run(clean_cmd, check=True)


if __name__ == "__main__":
    main()
