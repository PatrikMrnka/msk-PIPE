"""
external_tools.py – Checks and builds external binary / library dependencies.

Contains three independent checks, each focused on a single third-party tool:
  - check_muscle_wrapping        → verifies Muscle Wrapping 2.0 DLL
  - find_staple                  → locates the MSK-STAPLE MATLAB toolbox
  - compile_mask_to_mesh         → ensures the mask_to_mesh C++ binary is compiled
  - compile_extract_attachments  → ensures the extract_attachments C++ binary is compiled
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
import tempfile

from rich.prompt import Confirm, Prompt

from . import constants as C
from .ui import (
    console,
    print_check,
    print_error,
    print_info,
    print_success,
    print_warning,
)

# ── Muscle Wrapping 2.0 ───────────────────────────────────────────────────────


def check_muscle_wrapping(paths: dict) -> str | None:
    """
    Verify that the Muscle Wrapping 2.0 build directory contains the expected
    DLL.  Returns the resolved build path string on success, None on failure.
    """
    print_check("Checking Muscle Wrapping 2.0")

    default_dir = Path(C.MUSCLE_WRAPPING_DEFAULT).resolve()
    saved = paths.get("muscle_wrapping_path")
    saved_dir = Path(saved).resolve() if saved else None

    def _check(path: Path) -> Path | None:
        dll_path = path / "Bin" / "OsimMuscleGeneratorTool.dll"
        return path if dll_path.is_file() else None

    for candidate in (default_dir, saved_dir):
        if candidate is not None:
            found = _check(candidate)
            if found:
                paths["muscle_wrapping_path"] = str(found)
                print_success(
                    f"Muscle Wrapping DLL found at {found/ 'Bin' / 'OsimMuscleGeneratorTool.dll'}."
                )
                return str(found)

    mw_dir = Path(
        Prompt.ask(
            "Enter path to Muscle Wrapping 2.0 build directory",
            default=str(default_dir),
        )
    ).resolve()
    dll_path = mw_dir / "Bin" / "OsimMuscleGeneratorTool.dll"

    if dll_path.is_file():
        paths["muscle_wrapping_path"] = str(mw_dir)
        print_success(f"Muscle Wrapping DLL found at {dll_path}.")
        return str(mw_dir.resolve())

    print_error(f"Muscle Wrapping DLL not found at {dll_path}.")
    return None


# ── MSK-STAPLE ────────────────────────────────────────────────────────────────


_STAPLE_PCREGIONGROWING_REL = (
    Path("GIBOC-core")
    / "SubFunctions"
    / "GeometricFun"
    / "PCRegionGrowing.m"
)
_STAPLE_OLD_COLON_EXPR = re.compile(
    r"Pts_Out\(end\+1:end\+size\(idx\),:\)\s*=\s*Pts\(idx,:\);"
)


def _apply_staple_colon_fix(staple_root: Path) -> bool:
    """
    Patch MSK-STAPLE for MATLAB R2023a+ compatibility.

    Newer MATLAB versions require scalar operands for the colon operator.
    Older STAPLE versions use ``size(idx)`` (1x2 vector) in PCRegionGrowing,
    which crashes during femoral condyle extraction.
    """
    pc_region_growing = staple_root / _STAPLE_PCREGIONGROWING_REL

    if not pc_region_growing.is_file():
        print_warning(
            f"{pc_region_growing} not found. Skipping STAPLE MATLAB compatibility patch."
        )
        return True

    try:
        source = pc_region_growing.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        print_error(f"Failed to read {pc_region_growing}: {exc}")
        return False

    patched, n_replacements = _STAPLE_OLD_COLON_EXPR.subn(
        "Pts_Out(end+1:end+length(idx),:) =  Pts(idx,:);",
        source,
    )

    if n_replacements == 0:
        print_info("STAPLE MATLAB compatibility fix already present.")
        return True

    try:
        pc_region_growing.write_text(patched, encoding="utf-8")
    except Exception as exc:
        print_error(f"Failed to write patched STAPLE file {pc_region_growing}: {exc}")
        return False

    print_success(
        f"Applied STAPLE MATLAB R2023a+ compatibility fix in {pc_region_growing}."
    )
    return True


def find_staple(paths: dict) -> bool:
    """
    Locate the MSK-STAPLE directory. Search order:
      1. Default location (src/STAPLE)
      2. STAPLE_PATH environment variable
      3. Automatic download
      4. User prompt fallback
    Writes result into paths["staple_path"].
    """
    print_check("Checking MSK-STAPLE location")

    def _accept(path: Path) -> bool:
        if path.is_dir():
            if not _apply_staple_colon_fix(path):
                return False
            paths["staple_path"] = str(path)
            print_success(f"MSK-STAPLE found at {path}.")
            return True
        return False

    # 1. Default location
    if _accept(C.STAPLE_DEFAULT_DIR):
        return True

    # 2. Environment variable
    env_val = os.environ.get("STAPLE_PATH", "")
    if env_val and _accept(Path(env_val)):
        return True

    # 3. Automatic download
    print_warning("MSK-STAPLE not found locally.")
    if Confirm.ask("Download MSK-STAPLE from GitHub automatically?", default=True):
        if _clone_staple(C.STAPLE_DEFAULT_DIR):
            if _accept(C.STAPLE_DEFAULT_DIR):
                return True

    # 4. User prompt fallback
    user_input = Prompt.ask(
        "[yellow]MSK-STAPLE path not configured. Provide absolute path[/yellow]",
        default=str(C.STAPLE_DEFAULT_DIR.resolve()),
    )
    if _accept(Path(user_input).resolve()):
        return True

    print_error(f"MSK-STAPLE path is invalid: {user_input}")
    return False


# ── mask_to_mesh (C++ binary) ─────────────────────────────────────────────────────


def compile_mask_to_mesh(paths: dict) -> bool:
    """
    Ensure the mask_to_mesh binary exists.  If not, run CMake configure + build.
    VTK is located automatically from known candidate paths, with a user
    fallback prompt if auto-detection fails.
    """
    print_check("Checking mask_to_mesh (C++) binaries")

    default_dir = Path(C.MASK_TO_MESH_DEFAULT_DIR).resolve()
    saved = paths.get("mask_to_mesh_path")
    saved_dir = Path(saved).resolve() if saved else None

    def _check(path: Path) -> Path | None:
        if _mask_to_mesh_exe(path / "Release").exists():
            return path
        build_dir = path / "build"
        if _mask_to_mesh_exe(build_dir).exists():
            return path
        return None

    for candidate in (default_dir, saved_dir):
        if candidate is not None:
            found = _check(candidate)
            if found:
                paths["mask_to_mesh_path"] = str(found)
                print_success(f"mask_to_mesh binary already compiled in {found}.")
                return True

    paths["mask_to_mesh_path"] = Prompt.ask(
        "Enter path to mask_to_mesh directory",
        default=str(default_dir),
    )

    mask_to_mesh_dir = Path(paths["mask_to_mesh_path"]).resolve()
    build_dir = mask_to_mesh_dir / "build"
    src_dir = mask_to_mesh_dir / "src"
    exe_path = _mask_to_mesh_exe(build_dir)

    if exe_path.exists():
        print_success("mask_to_mesh binary already compiled.")
        return True

    print_warning("mask_to_mesh not found – starting CMake compilation...")

    if not shutil.which("cmake"):
        print_error("CMake not found in PATH. Install CMake >= 3.10.")
        return False

    vtk_cmake_dir = _resolve_vtk(paths)
    if vtk_cmake_dir is None:
        return False

    paths["vtk_path"] = str(vtk_cmake_dir)

    build_dir.mkdir(parents=True, exist_ok=True)
    return _cmake_build(src_dir, build_dir, vtk_cmake_dir)


# ── extract_attachments (C++ binary) ─────────────────────────────────────────


def compile_extract_attachments(paths: dict) -> bool:
    """
    Ensure the extract_attachments binary exists.  If not, run CMake configure + build.
    VTK is resolved via the same helper used by compile_mask_to_mesh.
    """
    print_check("Checking extract_attachments (C++) binary")

    default_dir = Path(C.EXTRACT_ATTACHMENTS_DEFAULT_DIR).resolve()
    saved = paths.get("extract_attachments_path")
    saved_dir = Path(saved).resolve() if saved else None

    def _check(path: Path) -> Path | None:
        build_dir = path / "build"
        if _extract_attachments_exe(build_dir).exists():
            return path
        return None

    for candidate in (default_dir, saved_dir):
        if candidate is not None:
            found = _check(candidate)
            if found:
                paths["extract_attachments_path"] = str(found)
                print_success(
                    f"extract_attachments binary already compiled in {found}."
                )
                return True

    paths["extract_attachments_path"] = Prompt.ask(
        "Enter path to extract_attachments directory",
        default=str(default_dir),
    )

    ea_dir = Path(paths["extract_attachments_path"]).resolve()
    build_dir = ea_dir / "build"
    src_dir = ea_dir / "src"
    exe_path = _extract_attachments_exe(build_dir)

    if exe_path.exists():
        print_success("extract_attachments binary already compiled.")
        return True

    print_warning("extract_attachments not found – starting CMake compilation...")

    if not shutil.which("cmake"):
        print_error("CMake not found in PATH. Install CMake >= 3.10.")
        return False

    vtk_cmake_dir = _resolve_vtk(paths)
    if vtk_cmake_dir is None:
        return False

    paths["vtk_path"] = str(vtk_cmake_dir)

    build_dir.mkdir(parents=True, exist_ok=True)
    return _cmake_build(src_dir, build_dir, vtk_cmake_dir)


# ── Private helpers ───────────────────────────────────────────────────────────


def _mask_to_mesh_exe(build_dir: Path) -> Path:
    if platform.system() == "Windows":
        return build_dir / "Release" / "mask_to_mesh.exe"
    return build_dir / "mask_to_mesh"


def _extract_attachments_exe(build_dir: Path) -> Path:
    if platform.system() == "Windows":
        return build_dir / "Release" / "extract_attachments.exe"
    return build_dir / "extract_attachments"


def _vtk_cmake_dir(base: Path) -> Path | None:
    """
    Return the directory containing vtk-config.cmake inside *base*, or None.
    Searches both the root and lib/cmake/vtk-* subdirectories.
    """
    if (base / "vtk-config.cmake").exists():
        return base
    cmake_root = base / "lib" / "cmake"
    if cmake_root.exists():
        for vtk_dir in sorted(cmake_root.glob("vtk-*")):
            if (vtk_dir / "vtk-config.cmake").exists():
                return vtk_dir
    return None


def _resolve_vtk(paths: dict) -> Path | None:
    """
    Return the VTK CMake config directory, checking saved path and known
    candidates before asking the user.
    """
    mw_path = paths.get("muscle_wrapping_path")
    if not mw_path:
        print_error("muscle_wrapping_path is not set. Cannot locate VTK.")
        return None

    mw_build = Path(mw_path).resolve()
    candidates: list[Path] = []

    saved_vtk = paths.get("vtk_path")
    if saved_vtk:
        candidates.append(Path(saved_vtk).resolve())

    candidates += [
        mw_build / "ExternalLibs" / "VTK" / "Bin" / "lib" / "cmake" / "vtk-9.4",
        mw_build / "ExternalLibs" / "VTK" / "Bin",
        mw_build / "ExternalLibs" / "VTK",
    ]

    for candidate in candidates:
        found = _vtk_cmake_dir(candidate)
        if found:
            return found

    print_warning("VTK was not found automatically.")
    user_vtk = Prompt.ask(
        "Enter VTK path (folder containing VTKConfig.cmake or install root)",
        default="",
    ).strip()

    if not user_vtk:
        print_error("VTK path not provided.")
        return None

    found = _vtk_cmake_dir(Path(user_vtk).resolve())
    if not found:
        print_error("The provided path does not contain vtk-config.cmake.")
    return found


def _cmake_build(src_dir: Path, build_dir: Path, vtk_cmake_dir: Path) -> bool:
    """Run CMake configure then build. Returns True on success."""
    print_info(f"Running CMake with VTK_DIR={vtk_cmake_dir} ...")

    configure = subprocess.run(
        [
            "cmake",
            "-S",
            str(src_dir),
            "-B",
            str(build_dir),
            f"-DVTK_DIR={vtk_cmake_dir}",
        ],
        capture_output=True,
        text=True,
    )
    if configure.returncode != 0:
        print_error(f"CMake configuration failed:\n{configure.stderr}")
        return False

    print_success("CMake configuration successful.")
    print_info("Building mask_to_mesh...")

    build = subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release"],
        capture_output=True,
        text=True,
    )
    if build.returncode == 0:
        print_success("mask_to_mesh compiled successfully.")
        return True

    print_error("mask_to_mesh build step failed.")
    return False

def _clone_staple(dest: Path) -> bool:
    """
    Clones the MSK-STAPLE repository into a temporary directory
    and moves only the 'STAPLE' subfolder to the destination.
    """
    print_info("Cloning MSK-STAPLE repository from GitHub...")
    
    # Use TemporaryDirectory for automatic cleanup after download
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # 1. Clone the entire repository into the temporary directory
        result = subprocess.run(
            ["git", "clone", C.STAPLE_REPO_URL, str(tmp_path)],
            capture_output=True, text=True, timeout=300,
        )
        
        if result.returncode != 0:
            print_error(f"Failed to clone MSK-STAPLE:\n{result.stderr}")
            return False

        staple_subfolder = tmp_path / "STAPLE"
        if not staple_subfolder.is_dir():
            print_error("STAPLE subfolder not found in the cloned repository.")
            return False

        # 2. Safe move: if destination exists (e.g., empty), remove it first
        try:
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Move the STAPLE folder from temp to src/STAPLE
            shutil.move(str(staple_subfolder), str(dest))
            print_success(f"MSK-STAPLE successfully downloaded to {dest}.")
            return True
        except Exception as e:
            print_error(f"Failed to move STAPLE folder: {e}")
            return False
