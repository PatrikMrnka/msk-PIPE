import sys
import argparse
import shutil
from pathlib import Path

try:
    import matlab.engine
except ImportError:
    print(
        "Warning: matlab.engine not found. Make sure you are running this in Python 3.12 with MATLAB Engine API installed."
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Glue script to run MSK-STAPLE via MATLAB Engine"
    )
    parser.add_argument(
        "--input-meshes",
        required=True,
        help="Directory containing processed bone meshes",
    )
    parser.add_argument(
        "--output-osim", required=True, help="Path for the output bone model (.osim)"
    )
    parser.add_argument(
        "--staple-path", required=True, help="Path to the MSK-STAPLE source directory"
    )
    args = parser.parse_args()

    input_dir = Path(args.input_meshes).resolve()
    output_osim = Path(args.output_osim).resolve()
    staple_path = Path(args.staple_path).resolve()

    if not input_dir.exists():
        print(f"Error: Input directory {input_dir} does not exist.")
        sys.exit(1)

    print(f"Starting MATLAB Engine...")
    try:
        eng = matlab.engine.start_matlab()

        # Add STAPLE path and subfolders
        print(f"Adding STAPLE to MATLAB path: {staple_path}")
        eng.addpath(eng.genpath(str(staple_path)), nargout=0)

        # Root dir of MSK-PIPE (assuming this script is in workflow/scripts)
        root_dir = Path(__file__).resolve().parent.parent.parent
        script_dir = root_dir / "src" / "python" / "05_staple"

        if not (script_dir / "hip_model.m").exists():
            print(f"Error: hip_model.m not found at {script_dir}")
            eng.quit()
            sys.exit(1)

        print(f"Adding script directory to MATLAB path: {script_dir}")
        eng.addpath(str(script_dir), nargout=0)

        print(f"Running STAPLE hip_model.m with meshes from {input_dir}...")

        output_parent = output_osim.parent
        output_parent.mkdir(parents=True, exist_ok=True)

        # Set workspace variables used by hip_model.m
        eng.workspace["tri_folder_in"] = str(input_dir)
        eng.workspace["output_models_folder_in"] = str(output_parent)

        eng.eval("hip_model", nargout=0)

        # Find the generated standard STAPLE output (e.g. auto2020_hip_R.osim)
        generated_osims = [
            f for f in output_parent.glob("*.osim") if f.name != output_osim.name
        ]

        if not generated_osims and not output_osim.exists():
            print("Error: MATLAB script completed but no .osim file was found.")
            eng.quit()
            sys.exit(1)

        if generated_osims:
            gen_osim = generated_osims[0]
            print(f"Moving generated OSIM {gen_osim.name} to target {output_osim.name}")
            shutil.move(str(gen_osim), str(output_osim))
        else:
            print(f"Output OSIM target {output_osim.name} already satisfied.")

        eng.quit()
        print("✅ STAPLE execution completed successfully.")

    except Exception as e:
        print(f"Error executing MATLAB engine: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
