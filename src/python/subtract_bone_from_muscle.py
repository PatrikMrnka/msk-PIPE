"""
subtract_bone_from_muscle.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Subtract combined bone masks from a muscle segmentation volume.

Dilates the muscle mask to bridge gaps, then subtracts the bone masks to
eliminate overlap.

Usage
-----
    python subtract_bone_from_muscle.py \
        --muscle-mask muscle.nii.gz \
        --bone-mask-dir bone_masks/ \
        --output-mask output.nii.gz \
        --dilation-radius 1
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import print_info, print_success, print_warning


def _to_binary_array(img: sitk.Image) -> np.ndarray:
    """Return uint8 array with values {0,1}."""
    arr = sitk.GetArrayFromImage(img)
    return (arr > 0).astype(np.uint8)


def _resample_to_reference(moving: sitk.Image, reference: sitk.Image) -> sitk.Image:
    """Resample moving image to reference geometry with nearest-neighbor."""
    if (
        moving.GetSize() == reference.GetSize()
        and moving.GetSpacing() == reference.GetSpacing()
        and moving.GetOrigin() == reference.GetOrigin()
        and moving.GetDirection() == reference.GetDirection()
    ):
        return moving

    return sitk.Resample(
        moving,
        reference,
        sitk.Transform(),
        sitk.sitkNearestNeighbor,
        0,
        sitk.sitkUInt8,
    )


def subtract_bone_from_muscle(
    muscle_path: Path,
    bone_mask_dir: Path,
    output_path: Path,
    dilation_radius: int = 0,
) -> None:
    """Dilate muscle to bridge gaps, then subtract bone masks to eliminate overlap."""
    muscle_img = sitk.ReadImage(str(muscle_path))
    
    # Dilate muscle mask to bridge gaps between muscle and bone.
    if dilation_radius > 0:
        # Using GrayscaleDilate to preserve original high label IDs (e.g. 7xxx).
        # The algorithm takes the maximum value in the neighborhood (label) and dilates it into the background (0).
        muscle_img = sitk.GrayscaleDilate(muscle_img, [dilation_radius] * 3)

    muscle_arr = sitk.GetArrayFromImage(muscle_img)
    original_dtype = muscle_arr.dtype

    combined_bone = np.zeros_like(muscle_arr, dtype=np.uint8)
    bone_files = sorted(bone_mask_dir.glob("*.nii.gz"))

    if not bone_files:
        print_warning(f"No bone masks found in {bone_mask_dir}; writing unchanged mask.")

    for bone_file in bone_files:
        bone_img = sitk.ReadImage(str(bone_file))
        bone_img = _resample_to_reference(bone_img, muscle_img)
        bone_arr = _to_binary_array(bone_img)
        combined_bone = np.maximum(combined_bone, bone_arr)

    # subtracting bone from dilated muscle - keeps original muscle labels, zeroes out voxels where bone is present
    muscle_arr[combined_bone > 0] = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve original dtype so high label IDs (e.g. 7xxx) are not truncated.
    result = sitk.GetImageFromArray(muscle_arr.astype(original_dtype, copy=False))
    result.CopyInformation(muscle_img)
    sitk.WriteImage(result, str(output_path))

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Subtract combined bone mask from a single muscle mask volume."
    )
    p.add_argument("--muscle-mask", type=Path, required=True)
    p.add_argument("--bone-mask-dir", type=Path, required=True)
    p.add_argument("--output-mask", type=Path, required=True)
    p.add_argument("--dilation-radius", type=int, default=0)
    return p


def main() -> None:
    args = _build_argparser().parse_args()
    print_info(f"Subtracting bones from: {args.muscle_mask.name}")
    subtract_bone_from_muscle(
        muscle_path=args.muscle_mask,
        bone_mask_dir=args.bone_mask_dir,
        output_path=args.output_mask,
        dilation_radius=args.dilation_radius,
    )
    print_success(f"Wrote bone-subtracted mask: {args.output_mask}")


if __name__ == "__main__":
    main()