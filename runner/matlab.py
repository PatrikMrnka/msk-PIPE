"""
matlab.py – MATLAB installation checks and OpenSim API configuration.

Two public functions:
  check_matlab        – verifies MATLAB is in PATH, required toolboxes are
                        present, and the OpenSim Java API is configured.
  setup_opensim_matlab – runs configureOpenSim.m in batch mode and verifies
                        the API is reachable in a second MATLAB instance.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .system import matlab_args
from .ui import print_check, print_error, print_info, print_step, print_subprocess_error, print_success, print_warning


# ── MATLAB batch snippets ─────────────────────────────────────────────────────

_TOOLBOX_CHECK = (
    "try, "
    "  v = ver; "
    "  has_curve = any(strcmp({v.Name}, 'Curve Fitting Toolbox')); "
    "  has_stat  = any(strcmp({v.Name}, 'Statistics and Machine Learning Toolbox')); "
    "  if has_curve && has_stat, disp('TOOLBOXES_OK'); "
    "  else, disp('TOOLBOXES_MISSING'); end; "
    "catch, disp('ERROR_TOOLBOX'); end; "
    "quit;"
)

_OPENSIM_CHECK = (
    "try, "
    "  v = org.opensim.modeling.opensimCommon.GetVersion(); "
    "  w = which('org-opensim-modeling.jar'); "
    "  fprintf('OPENSIM_READY|%s|%s\\n', char(v), char(w)); "
    "catch, fprintf('OPENSIM_NOT_CONFIGURED\\n'); end; "
    "quit;"
)

_OPENSIM_VERIFY = (
    "try, "
    "  v = org.opensim.modeling.opensimCommon.GetVersion(); "
    "  disp(['SETUP_SUCCESS_VER:', char(v)]); "
    "catch e, disp('SETUP_FINAL_FAILED'); disp(e.message); end; "
    "quit;"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_matlab(snippet: str) -> subprocess.CompletedProcess:
    return subprocess.run(matlab_args(snippet), capture_output=True, text=True)


def _check_toolboxes() -> bool:
    result = _run_matlab(_TOOLBOX_CHECK)
    if "TOOLBOXES_OK" in result.stdout:
        print_success("Required MATLAB toolboxes found.")
        return True
    print_error("Required MATLAB toolboxes missing (Curve Fitting, Statistics & ML).")
    return False


def _check_opensim_api(mw_path: str) -> bool:
    """Return True if the OpenSim API is already configured; run setup otherwise."""
    result = _run_matlab(_OPENSIM_CHECK)

    for line in result.stdout.splitlines():
        if "OPENSIM_READY" in line:
            try:
                _, version, jar_path = line.split("|", 2)
                print_success(f"OpenSim API {version.strip()} ready.")
            except ValueError:
                print_success("OpenSim API is configured.")
            return True

    print_warning("OpenSim API not yet configured. Running setup script...")
    return setup_opensim_matlab(mw_path)


# ── Public API ────────────────────────────────────────────────────────────────

def check_matlab(mw_path: str) -> bool:
    """
    Verify MATLAB is available, toolboxes are installed, and the OpenSim
    Java API is configured.  Returns True only when all three pass.
    """
    print_check("Checking MATLAB installation")

    if not shutil.which("matlab"):
        print_error("MATLAB executable not found in PATH. Install MATLAB > R2018b.")
        return False

    print_success("MATLAB executable found.")
    print_step("Validating toolboxes and OpenSim API...")

    try:
        return _check_toolboxes() and _check_opensim_api(mw_path)
    except Exception as exc:
        print_error(f"Failed to execute MATLAB checks: {exc}")
        return False


def setup_opensim_matlab(mw_build_path: str) -> bool:
    """
    Run configureOpenSim.m inside MATLAB (batch mode) then verify the API
    is reachable in a fresh MATLAB instance.  Returns True on success.
    """
    if not mw_build_path:
        print_warning("Muscle Wrapping path not provided; skipping OpenSim configuration.")
        return False

    install_dir = Path(mw_build_path) / "ExternalLibs" / "OpenSim" / "Bin"
    script_dir  = install_dir / "Resources" / "Code" / "Matlab"
    bin_dir     = install_dir / "bin"

    if not (script_dir / "configureOpenSim.m").exists():
        print_error(f"configureOpenSim.m not found in {script_dir}")
        return False

    # Expose OpenSim DLLs for the MATLAB session
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

    setup_cmd = (
        f"try, "
        f"  addpath('{script_dir.as_posix()}'); "
        f"  OPENSIM_INSTALL_DIR = '{install_dir.as_posix()}'; "
        f"  run('configureOpenSim.m'); "
        f"  disp('SETUP_SCRIPT_COMPLETED'); "
        f"catch e, "
        f"  disp('SETUP_FAILED'); disp(e.message); "
        f"end; "
        f"quit;"
    )

    try:
        print_info("Starting MATLAB to run configureOpenSim.m...")
        res = _run_matlab(setup_cmd)

        if "SETUP_SCRIPT_COMPLETED" not in res.stdout:
            print_error("OpenSim configuration script failed.")
            print_subprocess_error(res.stdout)
            return False
    except Exception as exc:
        print_error(f"Unexpected error communicating with MATLAB: {exc}")
        return False

    # Verify the API in a fresh MATLAB instance
    print_info("Verifying API in a new MATLAB instance...")
    try:
        res2 = _run_matlab(_OPENSIM_VERIFY)

        if "SETUP_SUCCESS_VER:" in res2.stdout:
            version = "unknown"
            for line in res2.stdout.splitlines():
                if "SETUP_SUCCESS_VER:" in line:
                    version = line.split(":", 1)[1].strip()
            print_success(f"OpenSim API version {version} configured successfully.")
            return True

        print_error("OpenSim verification failed after configuration.")
        print_subprocess_error(res2.stdout)
        return False

    except Exception as exc:
        print_error(f"Unexpected error communicating with MATLAB: {exc}")
        return False