# input.smk -- Detect input format and prepare a normalised NIfTI image.
#
# Supports three input formats:
#   - nifti: a .nii / .nii.gz file (simply copied)
#   - raw:   a .raw volume + coordinates.txt (converted via CT_raw_to_nifti.py)
#   - dicom: a folder of .dcm files (converted via CT_dicom_to_nifti.py)
#
# The format can be forced via config["user_settings"]["input_format"] or
# auto-detected from the contents of IN_DIR.
#
# If config["paths"]["input_path"] is set (via the --input CLI flag), that
# specific file or directory is used directly instead of scanning IN_DIR.

import shutil

# ---------------------------------------------------------------------------
# Input format detection
# ---------------------------------------------------------------------------

INPUT_FORMAT = config.get("user_settings", {}).get("input_format", "auto").lower()
INPUT_TYPE = None
INPUT_FILES = {}

_explicit_input = config.get("paths", {}).get("input_path", "")

if _explicit_input:
    _p = Path(_explicit_input)
    if _p.is_file():
        _ext = _p.name.lower()
        if _ext.endswith(".nii.gz") or _ext.endswith(".nii"):
            INPUT_TYPE = "nifti"
            INPUT_FILES["nii"] = str(_p)
        elif _ext.endswith(".raw"):
            coords = list(_p.parent.glob("coordinates.txt"))
            if not coords:
                sys.exit(
                    f"[ERROR] RAW file found but coordinates.txt is missing for {_p}"
                )
            INPUT_TYPE = "raw"
            INPUT_FILES["raw"] = str(_p)
            INPUT_FILES["coords"] = str(coords[0])
        else:
            sys.exit(f"[ERROR] Unrecognised input file extension: {_p}")
    elif _p.is_dir():
        # Treat as a DICOM directory or scan for files inside it.
        dcm_files = list(_p.rglob("*.dcm"))
        if dcm_files:
            INPUT_TYPE = "dicom"
            INPUT_FILES["dicom_dir"] = str(_p)
        else:
            nii = list(_p.rglob("*.nii.gz")) + list(_p.rglob("*.nii"))
            if nii:
                INPUT_TYPE = "nifti"
                INPUT_FILES["nii"] = str(nii[0])
            else:
                raw = list(_p.rglob("*.raw"))
                if raw:
                    coords = list(raw[0].parent.glob("coordinates.txt")) or list(
                        _p.rglob("coordinates.txt")
                    )
                    if not coords:
                        sys.exit(
                            f"[ERROR] RAW file found but coordinates.txt is missing for {raw[0]}"
                        )
                    INPUT_TYPE = "raw"
                    INPUT_FILES["raw"] = str(raw[0])
                    INPUT_FILES["coords"] = str(coords[0])
                else:
                    sys.exit(f"[ERROR] No recognisable input files in {_p}")

# Fall back to scanning IN_DIR when no explicit input was given.
if not INPUT_TYPE:
    _in_dir = Path(IN_DIR)

    # 1. NIfTI files
    if INPUT_FORMAT in ("auto", "nifti"):
        _nii = list(_in_dir.rglob("*.nii.gz")) + list(_in_dir.rglob("*.nii"))
        if _nii:
            INPUT_TYPE = "nifti"
            INPUT_FILES["nii"] = str(_nii[0])

    # 2. RAW files
    if not INPUT_TYPE and INPUT_FORMAT in ("auto", "raw"):
        _raw = list(_in_dir.rglob("*.raw"))
        if _raw:
            _coords = list(_raw[0].parent.glob("coordinates.txt")) or list(
                _in_dir.rglob("coordinates.txt")
            )
            if not _coords:
                sys.exit(
                    f"[ERROR] RAW file found but coordinates.txt is missing for {_raw[0]}"
                )
            INPUT_TYPE = "raw"
            INPUT_FILES["raw"] = str(_raw[0])
            INPUT_FILES["coords"] = str(_coords[0])

    # 3. DICOM files
    if not INPUT_TYPE and INPUT_FORMAT in ("auto", "dicom"):
        _dcm = list(_in_dir.rglob("*.dcm"))
        if _dcm:
            INPUT_TYPE = "dicom"
            INPUT_FILES["dicom_dir"] = str(_dcm[0].parent)
        else:
            # DICOM files without an extension (exclude coordinates.txt)
            for _d in [_in_dir] + [s for s in _in_dir.iterdir() if s.is_dir()]:
                _has_dicom = any(
                    f.is_file()
                    and f.suffix == ""
                    and f.name.lower() != "coordinates.txt"
                    for f in _d.iterdir()
                )
                if _has_dicom:
                    INPUT_TYPE = "dicom"
                    INPUT_FILES["dicom_dir"] = str(_d)
                    break

if not INPUT_TYPE:
    sys.exit(
        f"[ERROR] No input files found for format '{INPUT_FORMAT}' in {IN_DIR}. "
        "Use --input to specify a file or directory explicitly."
    )

if INPUT_TYPE == "nifti":
    IMAGE_NAME = Path(INPUT_FILES["nii"]).name
elif INPUT_TYPE == "raw":
    _target_name = Path(INPUT_FILES["raw"]).name.replace(".raw", ".nii.gz")
    if _target_name == Path(INPUT_FILES["raw"]).name:
        _target_name += ".nii.gz"
    IMAGE_NAME = _target_name
elif INPUT_TYPE == "dicom":
    IMAGE_NAME = Path(INPUT_FILES["dicom_dir"]).name + ".nii.gz"
else:
    IMAGE_NAME = "ct.nii.gz"

NII_OUT = os.path.join(OUT_DIR, "image", IMAGE_NAME)

# ---------------------------------------------------------------------------
# Step 0: prepare the normalised input image
# ---------------------------------------------------------------------------

if INPUT_TYPE == "nifti":

    rule prepare_input_nifti:
        input:
            nii=INPUT_FILES["nii"],
        output:
            nii=temp(NII_OUT),
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "prepare_input_nifti.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        run:
            Path(output.nii).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input.nii, output.nii)

elif INPUT_TYPE == "raw":

    rule prepare_input_raw:
        input:
            raw=INPUT_FILES["raw"],
            coords=INPUT_FILES["coords"],
        output:
            nii=temp(NII_OUT),
        params:
            py_exe=get_py_exe("msk_base"),
            extra=lambda w: (
                "--shape " + _d
                if (_d :=
                    config.get("raw_input", {}).get("shape", "")
                    or config.get("raw_parameters", {})
                        .get(Path(INPUT_FILES["raw"]).name, {})
                        .get("dimensions", "")
                )
                else ""
            ),
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "prepare_input_raw.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        shell:
            """
            "{params.py_exe}" src/python/converting_formats/CT_raw_to_nifti.py \
                "{input.raw}" "{input.coords}" -o "{output.nii}" --allow-nonuniform {params.extra}
            """

elif INPUT_TYPE == "dicom":

    rule prepare_input_dicom:
        input:
            dcm_dir=INPUT_FILES["dicom_dir"],
        output:
            nii=temp(NII_OUT),
        params:
            py_exe=get_py_exe("msk_base"),
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "prepare_input_dicom.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        shell:
            """
            "{params.py_exe}" src/python/converting_formats/CT_dicom_to_nifti.py \
                "{input.dcm_dir}" -o "{output.nii}"
            """
