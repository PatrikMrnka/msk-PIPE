#!/usr/bin/env python3
"""
Extract selected muscle masks from MuscleMap multi-label segmentation.
"""

import argparse
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step

def load_muscle_labels(config_path: Path) -> dict[str, int]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    labels = config.get("muscle_map", {}).get("labels", {})
    if not isinstance(labels, dict) or not labels:
        raise ValueError("Missing 'muscle_map.labels' mapping in config.json")

    parsed: dict[str, int] = {}
    for k, v in labels.items():
        parsed[str(k)] = int(v)
    return parsed


def extract_muscles(
    input_seg: str,
    output_dir: str,
    labels_map: dict[str, int],
) -> bool:
    """
    Extract individual muscles from MuscleMap multi-label segmentation.
    
    Args:
        input_seg: Path to MuscleMap segmentation output (_dseg.nii.gz)
        output_dir: Output directory for individual muscle masks
        labels_map: Mapping muscle_name -> integer label ID
    
    Returns:
        True if successful, False otherwise
    """
    
    input_path = Path(input_seg)
    if not input_path.exists():
        print_error(f"Input segmentation not found: {input_seg}")
        return False
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print_step(f"Loading segmentation from {input_seg}")
    
    try:
        # Load the multi-label segmentation
        nib_img = nib.load(input_seg)
        seg_data = nib_img.get_fdata()
        affine = nib_img.affine
        
        print_info(f"Segmentation shape: {seg_data.shape}")
        print_info(f"Unique labels: {np.unique(seg_data)}")
        
        # Process each muscle
        processed_count = 0
        for muscle_name, label_num in labels_map.items():
            # Extract mask for this label
            muscle_mask = (seg_data == label_num).astype(np.uint8)
            
            if muscle_mask.sum() == 0:
                print_warning(f"Label {label_num} ({muscle_name}) not found in segmentation")
                continue

            print_step(f"Processing {muscle_name} (label {label_num})")

            # Save cleaned mask
            output_file = output_path / f"{muscle_name}.nii.gz"
            cleaned_img = nib.Nifti1Image(muscle_mask.astype(np.uint8), affine)
            nib.save(cleaned_img, output_file)
            
            print_success(f"Saved {muscle_name} to {output_file}")
            processed_count += 1
        
        if processed_count == 0:
            print_warning("No muscles were extracted. Check label numbers in config.json.")
            return False

        print_success(f"Extracted {processed_count} muscle masks successfully.")
        return True
        
    except Exception as e:
        print_error(f"Error processing segmentation: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Extract selected muscle masks from MuscleMap output"
    )
    parser.add_argument(
        "input_seg",
        type=str,
        help="Path to MuscleMap segmentation output (_dseg.nii.gz)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        required=True,
        help="Output directory for extracted masks",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.json",
        help="Path to config.json with muscle_map.labels mapping",
    )

    args = parser.parse_args()

    labels_map = load_muscle_labels(Path(args.config))
    success = extract_muscles(
        args.input_seg,
        args.output_dir,
        labels_map=labels_map,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
