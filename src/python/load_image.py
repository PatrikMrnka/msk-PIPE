import sys
import shutil
import subprocess
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import (
    print_info,
    print_success,
    print_warning,
    print_error,
    print_step,
    print_section,
)

# V prostředí Snakemake je globálně dostupný objekt `snakemake`.


def main():
    print_section("STEP 1: Converting input data to NIfTI")

    in_dir = Path(snakemake.input.in_dir)
    out_nii = Path(snakemake.output.nii)

    # Načtení výběru formátu vstupu
    user_settings = getattr(snakemake, "config", {})
    input_format = user_settings.get("input_format", "auto").lower()
    print_info(f"Input format selected from config: {input_format}")

    # 1. Je na vstupu rovnou NIfTI?
    if input_format in ["auto", "nifti"]:
        nii_files = list(in_dir.rglob("*.nii.gz")) + list(in_dir.rglob("*.nii"))
        if nii_files:
            print_info(f"NIfTI file found: {nii_files[0]}")
            print_step(
                "Copying file to the expected output location, skipping conversion."
            )
            shutil.copy2(nii_files[0], out_nii)
            sys.exit(0)
        elif input_format == "nifti":
            print_error(
                "NIfTI format was forced but no NIfTI file was found in the input folder."
            )
            sys.exit(1)

    # 2. Jsou na vstupu RAW data?
    if input_format in ["auto", "raw"]:
        raw_files = list(in_dir.rglob("*.raw"))
        if raw_files:
            raw_file = raw_files[0]
            # Pokus o nalezení coordinates.txt buď hned ve složce s RAWem nebo kdekoliv
            coords_files = list(raw_file.parent.glob("coordinates.txt"))
            if not coords_files:
                coords_files = list(in_dir.rglob("coordinates.txt"))

            if not coords_files:
                print_error(f"coordinates.txt not found for {raw_file}.")
                sys.exit(1)

            coords_file = coords_files[0]

            # Načtení případných parametrů z configu
            raw_params = user_settings.get("raw_parameters", {}).get(raw_file.name, {})
            dims = raw_params.get("dimensions", "512x512x120")

            script_path = str(
                Path("src/python/01_converting/1_raw_ct2nifti.py").resolve()
            )
            print_info(f"RAW file found: {raw_file}.")
            print_step(
                f"Running RAW-to-NIfTI conversion script (dimensions: {dims})..."
            )

            cmd = [
                sys.executable,
                script_path,
                str(raw_file),
                str(coords_file),
                "-o",
                str(out_nii),
                "--shape",
                dims,
            ]

            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                print_error(f"CT_raw_to_nifti.py exited with code {res.returncode}.")
                sys.exit(1)
            sys.exit(0)
        elif input_format == "raw":
            print_error("RAW format was forced but no RAW file was found.")
            sys.exit(1)

    # 3. Jsou na vstupu DICOMy?
    if input_format in ["auto", "dicom"]:
        # Kontrolujeme i rovnou kořenovou složku `in_dir`, nebo jakoukoliv podřízenou složku.
        directories_to_check = [in_dir] + [d for d in in_dir.iterdir() if d.is_dir()]
        for d in directories_to_check:
            has_dicom = False
            for f in d.iterdir():
                # DICOMy často končí .dcm nebo nemají žádnou příponu (přitom to nesmí být coordinates.txt)
                if f.is_file() and (
                    f.suffix.lower() == ".dcm"
                    or (f.suffix == "" and f.name.lower() != "coordinates.txt")
                ):
                    has_dicom = True
                    break

            if has_dicom:
                script_path = str(
                    Path("src/python/01_converting/1_dicom_ct2nifti.py").resolve()
                )
                print_info(f"DICOM files found in folder: {d}.")
                print_step("Running DICOM-to-NIfTI conversion script...")
                cmd = [sys.executable, script_path, str(d), "-o", str(out_nii)]
                res = subprocess.run(cmd, check=False)
                if res.returncode != 0:
                    print_error(
                        f"ct_to_nifti_dicom.py exited with code {res.returncode}."
                    )
                    sys.exit(1)
                sys.exit(0)
        if input_format == "dicom":
            print_error("DICOM format was forced but no DICOM files were found.")
            sys.exit(1)

    print_error(f"No input files found for the selected format '{input_format}'.")
    print_info(
        "Please check the data/input folder or set the correct format in the configuration."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
