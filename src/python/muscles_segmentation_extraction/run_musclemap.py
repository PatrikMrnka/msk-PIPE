#!/usr/bin/env python3
"""
run_musclemap.py
~~~~~~~~~~~~~~~~
MuscleMap Segmentation Runner.

Segment muscles from CT/MRI images using MuscleMap.

Usage
-----
    python run_musclemap.py \
        input.nii.gz \
        --output-dir output_masks/ \
        --spatial-overlap 90
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step


def run_musclemap(
    input_nifti: str, output_dir: str, spatial_overlap: int = 90, chunk_size: int = 15
):
    """
    Run MuscleMap segmentation.

    Args:
        input_nifti: Path to input NIfTI file (.nii.gz)
        output_dir: Output directory for masks
        spatial_overlap: Spatial overlap for sliding window inference (75-90)
        chunk_size: Size of chunks for sliding window inference (10, 15, 20 or 'auto')
    """

    input_path = Path(input_nifti)
    if not input_path.exists():
        print_error(f"Input file not found: {input_nifti}")
        return False

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)


    print_step(f"Running MuscleMap segmentation on {input_nifti}")
    print_info(f"Spatial overlap: {spatial_overlap}%")
    print_info(f"Chunk size: {chunk_size} slices")
    print_info(f"Output directory: {output_dir}")

    try:
        common_args = [
            "-i",
            str(input_path),
            "-s",
            str(spatial_overlap),
            "-c",
            str(chunk_size),
            "-o",
            str(output_path),
        ]

        candidates = []

        # 1) Module call via current interpreter (works after pip install -e src/MuscleMap)
        candidates.append([sys.executable, "-m", "scripts.mm_segment", *common_args])

        # 2) Direct console entrypoint in the same environment
        py_dir = Path(sys.executable).resolve().parent
        if os.name == "nt":
            mm_exe = py_dir / "Scripts" / "mm_segment.exe"
        else:
            mm_exe = py_dir.parent / "bin" / "mm_segment"
        if mm_exe.exists():
            candidates.append([str(mm_exe), *common_args])

        # 3) Direct script call as fallback (works if MuscleMap is not installed but source is present)
        mm_script = (
            Path(__file__).resolve().parents[2]
            / "MuscleMap"
            / "scripts"
            / "mm_segment.py"
        )
        if mm_script.exists():
            candidates.append([sys.executable, str(mm_script), *common_args])

        # 4) Legacy PATH call as last resort
        candidates.append(["mm_segment", *common_args])

        success = False
        for cmd in candidates:
            print_step(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                success = True
                break
            print_warning(
                f"Command failed with return code {result.returncode}, trying fallback..."
            )

        if not success:
            print_error("All MuscleMap invocation methods failed.")
            return False

        # Normalize output name expected by downstream steps
        name = input_path.name
        if name.endswith(".nii.gz"):
            base = name[:-7]
        elif name.endswith(".nii"):
            base = name[:-4]
        else:
            base = input_path.stem

        preferred = output_path / f"{base}_dseg.nii.gz"
        fallback_local = input_path.parent / f"{base}_dseg.nii.gz"
        target_mask = output_path / "musclemap_segmentation.nii.gz"
        target_mask_plural = output_path / "musclemap_segmentations.nii.gz"

        if preferred.exists():
            shutil.copy2(preferred, target_mask)
            print_success(f"Segmentation saved to {target_mask}")
        elif fallback_local.exists():
            shutil.copy2(fallback_local, target_mask)
            print_success(f"Segmentation saved to {target_mask}")
        else:
            dseg_files = sorted(output_path.glob("*_dseg.nii.gz"))
            if dseg_files:
                shutil.copy2(dseg_files[0], target_mask)
                print_success(f"Segmentation saved to {target_mask}")
            else:
                print_error("No segmentation output found.")
                return False

        # Keep a compatibility alias used by workflow rules.
        shutil.copy2(target_mask, target_mask_plural)
        print_success(f"Segmentation saved to {target_mask_plural}")

        print_success("MuscleMap segmentation completed successfully.")
        return True

    except Exception as e:
        print_error(f"Exception during MuscleMap execution: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run MuscleMap segmentation on CT/MRI images"
    )
    parser.add_argument(
        "input_nifti",
        type=str,
        help="Path to input NIfTI file (.nii.gz)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        required=True,
        help="Output directory for segmentation masks",
    )
    parser.add_argument(
        "--spatial-overlap",
        "-s",
        type=int,
        default=75,
        choices=[75, 80, 85, 90],
        help="Spatial overlap for sliding window inference (default: 75)",
    )
    parser.add_argument(
        "--chunk-size",
        "-c",
        type=str,
        default="auto",
        choices=["auto", 10, 15, 20],
        help="Number of axial slices to process as a chunk (default: auto)",
    )

    args = parser.parse_args()

    success = run_musclemap(
        args.input_nifti, args.output_dir, args.spatial_overlap, args.chunk_size
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
