"""
process_staple.py
~~~~~~~~~~~~~~~~~
Python wrapper for invoking MSK-STAPLE via MATLAB batch mode.

Acts as a bridge between Snakemake and MATLAB, executing a user-supplied .m script and
reorganising the generated outputs into the paths expected by the pipeline:

    1. Start MATLAB in batch mode.
    2. Add the STAPLE toolbox and the script directory to the MATLAB path.
    3. Expose input/output paths as MATLAB workspace variables.
    4. Run the .m script (e.g. hip_model.m).
    5. Let the script write outputs into the target locations and exit MATLAB.

Usage
-----
    python process_staple.py \
        --input-dir data/temp/staple_in \
        --output-osim data/temp/bone_model.osim \
        --output-geom-dir data/temp/Geometry \
        --staple-path /path/to/STAPLE \
        --matlab-script hip_model.m
"""

import argparse
import sys
from pathlib import Path

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runner.ui import print_error, print_step

import subprocess
from runner.system import matlab_args

# ---------------------------------------------------------------------------
# Core processing logic
# ---------------------------------------------------------------------------


def run_staple(
    input_dir: Path,
    output_osim: Path,
    output_geom_dir: Path,
    staple_path: Path,
    matlab_script_path: Path,
) -> None:
    """Launch MATLAB in batch mode, execute the STAPLE script, and organise outputs.

    Parameters
    ----------
    input_dir:
        Directory containing the merged bone meshes passed to the .m script.
    output_osim:
        Destination path for the generated .osim file.
    output_geom_dir:
        Destination directory for the generated Geometry folder.
    staple_path:
        Root directory of the MSK-STAPLE toolbox (added to the MATLAB path recursively).
    matlab_script_path:
        Absolute path to the .m script to execute (e.g. hip_model.m).
    """

    script_dir = matlab_script_path.parent
    script_name = matlab_script_path.stem

    matlab_snippet = (
        f"try, "
        f"  addpath(genpath('{staple_path.as_posix()}')); "
        f"  addpath('{script_dir.as_posix()}'); "
        f"  output_models_folder_in = '{output_osim.parent.as_posix()}'; "
        f"  tri_folder_in = '{input_dir.as_posix()}'; "
        f"  eval('{script_name}'); "
        f"catch e, "
        f"  disp('STAPLE_FAILED'); disp(getReport(e)); exit(1); "
        f"end; "
        f"exit(0);"
    )

    print_step(f"Running MATLAB script '{script_name}' via subprocess...")
    cmd = matlab_args(matlab_snippet)

    try:
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print_error("MATLAB execution failed.")
            sys.exit(1)

    except Exception as exc:
        print_error(f"MATLAB execution failed:\n{exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run MSK-STAPLE via MATLAB batch mode and organise its outputs."
    )

    p.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing the merged bone meshes.",
    )
    p.add_argument(
        "--output-osim",
        required=True,
        help="Target path for the generated .osim file (e.g. bone_model.osim).",
    )
    p.add_argument(
        "--output-geom-dir",
        required=True,
        help="Target directory for the generated Geometry folder (e.g. Geometry).",
    )
    p.add_argument(
        "--staple-path",
        required=True,
        help="Root directory of the MSK-STAPLE toolbox.",
    )
    p.add_argument(
        "--matlab-script",
        required=True,
        help="Path to the .m script to execute (e.g. hip_model.m).",
    )

    return p


def main() -> None:
    args = _build_argparser().parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_osim = Path(args.output_osim).resolve()
    output_geom_dir = Path(args.output_geom_dir).resolve()
    staple_path = Path(args.staple_path).resolve()
    matlab_script_path = Path(args.matlab_script).resolve()

    if not input_dir.exists():
        print_error(f"Input directory does not exist: {input_dir}")
        sys.exit(1)
    if not matlab_script_path.exists():
        print_error(f"MATLAB script not found: {matlab_script_path}")
        sys.exit(1)

    run_staple(
        input_dir=input_dir,
        output_osim=output_osim,
        output_geom_dir=output_geom_dir,
        staple_path=staple_path,
        matlab_script_path=matlab_script_path,
    )


if __name__ == "__main__":
    main()
