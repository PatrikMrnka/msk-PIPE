#!/usr/bin/env python3
"""
MuscleMap Segmentation Runner
Segmentuje svaly (zvrášť Abductor Brevis, Gluteus Medius, Gluteus Maximus, Iliacus) 
z CT/MRI snímků pomocí MuscleMap.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_musclemap(input_nifti: str, output_dir: str, spatial_overlap: int = 75):
    """
    Run MuscleMap segmentation.
    
    Args:
        input_nifti: Path to input NIfTI file (.nii.gz)
        output_dir: Output directory for masks
        spatial_overlap: Spatial overlap for sliding window inference (75-90)
    """
    
    input_path = Path(input_nifti)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_nifti}")
        return False
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Prefer invocation methods that do not depend on PATH activation.
    # This avoids WinError 2 when Snakemake runs Python directly from env.
    
    print(f"[INFO] Running MuscleMap segmentation on {input_nifti}")
    print(f"[INFO] Spatial overlap: {spatial_overlap}%")
    print(f"[INFO] Output directory: {output_dir}")
    
    try:
        common_args = [
            "-i",
            str(input_path),
            "-s",
            str(spatial_overlap),
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

        # 3) Direct script fallback from local repository clone
        # .../src/python/02a_muscles_segm/2a_run_musclemap.py -> .../src/MuscleMap/scripts/mm_segment.py
        mm_script = Path(__file__).resolve().parents[2] / "MuscleMap" / "scripts" / "mm_segment.py"
        if mm_script.exists():
            candidates.append([sys.executable, str(mm_script), *common_args])

        # 4) Legacy PATH call as last resort
        candidates.append(["mm_segment", *common_args])

        success = False
        for cmd in candidates:
            print(f"[INFO] Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                success = True
                break
            print(
                f"[WARNING] Command failed with return code {result.returncode}, trying fallback..."
            )

        if not success:
            print("[ERROR] All MuscleMap invocation methods failed")
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

        if preferred.exists():
            shutil.copy2(preferred, target_mask)
            print(f"[INFO] Segmentation saved to {target_mask}")
        elif fallback_local.exists():
            shutil.copy2(fallback_local, target_mask)
            print(f"[INFO] Segmentation saved to {target_mask}")
        else:
            dseg_files = sorted(output_path.glob("*_dseg.nii.gz"))
            if dseg_files:
                shutil.copy2(dseg_files[0], target_mask)
                print(f"[INFO] Segmentation saved to {target_mask}")
            else:
                print("[ERROR] No segmentation output found")
                return False

        print("[INFO] ✓ MuscleMap segmentation completed successfully")
        return True

    except Exception as e:
        print(f"[ERROR] Exception during MuscleMap execution: {e}")
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
    
    args = parser.parse_args()
    
    success = run_musclemap(
        args.input_nifti,
        args.output_dir,
        args.spatial_overlap,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
