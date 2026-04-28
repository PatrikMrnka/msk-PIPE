"""
CT_dicom_to_nifti.py
~~~~~~~~~~~~~~~~~~~~
Convert a DICOM series to NIfTI.

Scans the given directory for DICOM files, identifies series, and converts
the selected series (first by default) to NIfTI (.nii.gz). SimpleITK
automatically handles the spatial transform (pixel spacing, slice thickness,
origin, and orientation).

Usage
-----
    python CT_dicom_to_nifti.py ./data/dicom_folder -o ./result/ct.nii.gz
"""

import argparse
import sys
import pathlib
import SimpleITK as sitk

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step


def main():
    """CLI entry point for converting a DICOM series to NIfTI."""
    ap = argparse.ArgumentParser(
        description="Convert a DICOM folder to a NIfTI volume (.nii.gz)."
    )
    ap.add_argument("dicom_dir", type=pathlib.Path,
                    help="Path to the folder containing the DICOM files for the series.")
    ap.add_argument("-o", "--out", type=pathlib.Path, default=None,
                    help="Output NIfTI path (e.g. result.nii.gz). Defaults to the DICOM folder parent.")
    ap.add_argument("--series-id", type=str, default=None,
                    help="Series ID to convert if the folder contains multiple series.")

    args = ap.parse_args()

    dicom_dir_str = str(args.dicom_dir)

    if not args.dicom_dir.is_dir():
        sys.exit(f"ERROR: Path '{args.dicom_dir}' does not exist or is not a directory.")

    # Initialise the DICOM series reader.
    print_step(f"Scanning folder: {dicom_dir_str} ...")
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(dicom_dir_str)

    if not series_ids:
        sys.exit("ERROR: No valid DICOM series found in the folder.")

    # Select the series.
    if args.series_id:
        if args.series_id not in series_ids:
            print_info("Available series in the folder:")
            for s_id in series_ids:
                print_info(f"  - {s_id}")
            sys.exit(f"ERROR: Series with ID '{args.series_id}' was not found.")
        selected_series = args.series_id
    else:
        selected_series = series_ids[0]
        if len(series_ids) > 1:
            print_warning(f"Multiple series found ({len(series_ids)}).")
            print_info("Available series:")
            for s_id in series_ids:
                print_info(f"  - {s_id}")
            print_info(f"\nAutomatically selecting the first series: {selected_series}")
            print_info("Use --series-id to choose a different one.\n")

    # Collect the file list for the selected series.
    dicom_names = reader.GetGDCMSeriesFileNames(dicom_dir_str, selected_series)
    reader.SetFileNames(dicom_names)

    # Load the image into memory.
    print_step(f"Loading {len(dicom_names)} DICOM files...")
    try:
        image = reader.Execute()
    except Exception as e:
        sys.exit(f"ERROR: Failed to load DICOM data. Details: {e}")

    # Log volume info.
    size = image.GetSize()
    spacing = image.GetSpacing()
    print_success("Loaded successfully.")
    print_info(f"  - Dimensions (X, Y, Z): {size[0]} x {size[1]} x {size[2]}")
    print_info(f"  - Spacing (mm):         {spacing[0]:.4f} x {spacing[1]:.4f} x {spacing[2]:.4f}")

    # Determine output path.
    out_path = args.out
    if out_path is None:
        out_path = args.dicom_dir.parent / f"{args.dicom_dir.name}_converted.nii.gz"

    out_path_str = str(out_path)

    # Save to NIfTI.
    print_step("Saving to NIfTI...")
    try:
        sitk.WriteImage(image, out_path_str)
        print_success(f"Done: {out_path_str}")
    except Exception as e:
        sys.exit(f"ERROR: Failed to write NIfTI file. Details: {e}")


if __name__ == "__main__":
    main()