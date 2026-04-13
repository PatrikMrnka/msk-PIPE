import sys
import yaml
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step, print_section

# Snakemake injects the `snakemake` object into the script's global namespace.
# We can use snakemake.config to access configuration parameters.
# If run outside snakemake, this won't work, which is intended.

def main():
    print_section("Validating input images (Snakemake pipeline)")
    
    # In Snakemake context, working directory should be the project root
    input_dir = Path("data/input")
    if not input_dir.exists():
        print_error(f"Input directory ({input_dir}) not found.")
        sys.exit(1)

    try:
        import pydicom
        has_pydicom = True
    except ImportError:
        has_pydicom = False
        print_warning("pydicom not installed. Skipping advanced DICOM validation.")

    try:
        import nibabel as nib
        has_nib = True
    except ImportError:
        has_nib = False
        print_warning("nibabel not installed. Skipping NIfTI validation.")

    # 1. Validation of DICOM folders
    print_step("Checking DICOM folders...")
    directories = [d for d in input_dir.iterdir() if d.is_dir()]
    for d in directories:
        dicom_files = []
        for f in d.iterdir():
            if f.is_file() and (f.suffix.lower() == '.dcm' or f.suffix == ''):
                if has_pydicom:
                    try:
                        pydicom.dcmread(f, stop_before_pixels=True)
                        dicom_files.append(f)
                    except Exception:
                        pass
                else:
                    dicom_files.append(f)
        
        if dicom_files and has_pydicom:
            print_info(f"- Validating DICOM folder: {d.name} ({len(dicom_files)} files)")
            datasets = []
            for f in dicom_files:
                try:
                    ds = pydicom.dcmread(f, stop_before_pixels=True)
                    if hasattr(ds, 'InstanceNumber'):
                        datasets.append((int(ds.InstanceNumber), ds, f))
                except Exception:
                    pass
            
            if datasets:
                datasets.sort(key=lambda x: x[0])
                first_ds = datasets[0][1]
                last_ds = datasets[-1][1]
                
                if hasattr(first_ds, 'SeriesInstanceUID') and hasattr(last_ds, 'SeriesInstanceUID'):
                    if first_ds.SeriesInstanceUID != last_ds.SeriesInstanceUID:
                        print_error(f"WARNING: Multiple SeriesInstanceUIDs detected in {d.name}! You might have mixed different scans.")
                
                missing_meta = []
                if not hasattr(first_ds, 'PixelSpacing'): missing_meta.append("PixelSpacing")
                if not hasattr(first_ds, 'SliceThickness'): missing_meta.append("SliceThickness")
                
                if missing_meta:
                    print_warning(f"Missing DICOM metadata in {d.name}: {', '.join(missing_meta)}.")
                
                instance_numbers = [item[0] for item in datasets]
                expected_numbers = list(range(min(instance_numbers), max(instance_numbers) + 1))
                missing_numbers = set(expected_numbers) - set(instance_numbers)
                if missing_numbers:
                    print_error(f"WARNING: Missing DICOM slices detected in {d.name}! Missing InstanceNumbers: {sorted(list(missing_numbers))}")
                else:
                    print_success(f"DICOM continuity verified for {d.name}.")

    files = list(input_dir.glob("**/*"))
    data_files = [f for f in files if f.is_file() and (f.suffix.lower() in [".dcm", ".nii", ".gz", ".raw"] or "dicom" in f.parent.name.lower())]

    if not data_files:
        print_warning(f"No input medical image files found in {input_dir}/ (DICOM, NII.GZ, RAW)")
    else:
        print_success(f"Found {len(data_files)} image files.")

    # 2. Validation of NIfTI files
    if has_nib:
        print_step("Checking NIfTI files...")
        nii_files = [f for f in data_files if f.name.endswith(".nii.gz") or f.name.endswith(".nii")]
        for nf in nii_files:
            try:
                nib.load(nf)
                print_success(f"NIfTI file {nf.name} is valid.")
            except Exception as e:
                print_error(f"Corrupted NIfTI file detected: {nf.name} - {e}")
                sys.exit(1)

    # 3. Validation of RAW files
    print_step("Checking RAW files...")
    raw_files = [f for f in data_files if f.suffix.lower() == ".raw"]
    if raw_files:
        # Přečteme `user_settings.yaml` nativně namísto `snakemake.config`, abychom vypsali chybu
        # pokud tam ještě nebylo nic uloženo
        user_settings = getattr(snakemake, 'config', {}) if 'snakemake' in globals() else {}
        
        raw_params = user_settings.get('raw_parameters') or {}
        
        for rf in raw_files:
            file_key = str(rf.name)
            if file_key not in raw_params:
                print_error(f"RAW file {file_key} is missing dimensionality and coordinate info in config/user_settings.yaml!")
                print_info("  Please add:")
                print_info("  raw_parameters:")
                print_info(f"    {file_key}:")
                print_info("      dimensions: '...x...x...'")
                print_info("      z_spacing: '...'")
                print_info("      bytes_per_pixel: ...")
                sys.exit(1)
            
            # Mathematical validation
            params = raw_params[file_key]
            dims_str = params.get("dimensions", "")
            bpp = float(params.get("bytes_per_pixel", 2))
            
            try:
                w, h, d = map(int, dims_str.lower().split('x'))
                expected_size = w * h * d * bpp
                actual_size = rf.stat().st_size
                if actual_size != expected_size:
                    print_error(f"RAW file size mismatch for {file_key}!")
                    print_info(f"  Expected: {expected_size} bytes (based on {dims_str} and {bpp} Bpp)")
                    print_info(f"  Actual:   {actual_size} bytes on disk.")
                    sys.exit(1)
                else:
                    print_success(f"RAW file size for {file_key} verified ({actual_size} bytes).")
            except ValueError:
                print_warning(f"Could not parse dimensions for {file_key} (expected WxHxD format).")

    print_success("\nInput validation successful.")
    
    # TOUCH output file to satisfy rule dependency
    if 'snakemake' in globals():
        for out_file in snakemake.output:
            Path(out_file).touch()

if __name__ == "__main__":
    main()
