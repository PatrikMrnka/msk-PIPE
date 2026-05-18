"""
micromamba.py – All Micromamba / conda-environment logic.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from rich.prompt import Confirm

from .constants import (
    BIN_DIR, ENVS_DIR,
    MICROMAMBA_EXE, MICROMAMBA_WIN_URL, MICROMAMBA_WIN_URL_TEMPLATE, MICROMAMBA_DEFAULT_VERSION,
    BASE_ENVS, MUSCLEMAP_ENV_CPU, MUSCLEMAP_ENV_GPU,
    MUSCLEMAP_YAML_CPU, MUSCLEMAP_YAML_GPU,
)
from .constants import MAIN_CONFIG_PATH
import json
from .system import compute_file_hash
from .ui import print_check, print_error, print_info, print_step, print_subprocess_error, print_success, print_warning


# ── Internal helpers ──────────────────────────────────────────────────────────

def _env_map(has_gpu: bool) -> dict[str, Path]:
    """Return {env_name: yaml_path} dict for the current GPU configuration."""
    musclemap_name = MUSCLEMAP_ENV_GPU if has_gpu else MUSCLEMAP_ENV_CPU
    musclemap_yaml = MUSCLEMAP_YAML_GPU if has_gpu else MUSCLEMAP_YAML_CPU
    return {**BASE_ENVS, musclemap_name: musclemap_yaml}


def _python_exe(env_path: Path) -> Path:
    rel = "python.exe" if platform.system() == "Windows" else "bin/python"
    return env_path / rel


def _default_mamba_root_prefix() -> Path:
    return ENVS_DIR.resolve()


def make_mamba_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of ``os.environ`` with all variables required for
    micromamba to run correctly without crashing.

    Specifically:
    * ``MAMBA_ROOT_PREFIX`` – must point at the project-local envs dir so
      micromamba can locate its package cache.  Without it micromamba crashes
      on Windows with STATUS_STACK_BUFFER_OVERRUN (0xC0000409).
    * ``MAMBA_PKGS_DIRS`` / ``PIP_CACHE_DIR`` – project-local package caches
      to avoid permission errors when writing into the user AppData cache.

    All callers across the codebase (micromamba.py, musclemap.py, pipeline.py)
    import this single function instead of duplicating the logic.
    """
    env = os.environ.copy()

    # ── Mamba root prefix ────────────────────────────────────────────────────
    env.setdefault("MAMBA_ROOT_PREFIX", str(_default_mamba_root_prefix()))

    # ── Conda/mamba package cache ────────────────────────────────────────────
    if "MAMBA_PKGS_DIRS" not in env and "CONDA_PKGS_DIRS" not in env:
        env["MAMBA_PKGS_DIRS"] = str(Path(env["MAMBA_ROOT_PREFIX"]) / "pkgs")

    # ── pip cache ────────────────────────────────────────────────────────────
    pip_cache_path = Path(env["MAMBA_ROOT_PREFIX"]) / "pip_cache"
    try:
        pip_cache_path.mkdir(parents=True, exist_ok=True)
        env.setdefault("PIP_CACHE_DIR", str(pip_cache_path))
        env.setdefault("PIP_NO_CACHE_DIR", "0")
    except Exception:
        env["PIP_NO_CACHE_DIR"] = "1"  # fallback: disable cache on mkdir failure

    if extra:
        env.update(extra)
    return env


def _run_micromamba(*args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["micromamba", *args],
        capture_output=True, text=True,
        env=make_mamba_env(env_overrides),
    )


def _get_mamba_cache_dir() -> Path:
    """Get the Micromamba/Mamba package cache directory."""
    if "MAMBA_ROOT_PREFIX" in os.environ:
        return Path(os.environ["MAMBA_ROOT_PREFIX"]) / "pkgs"
    elif "CONDA_PKGS_DIRS" in os.environ:
        return Path(os.environ["CONDA_PKGS_DIRS"].split(os.pathsep)[0])
    else:
        # Default: ~/.mamba/pkgs or ~/.conda/pkgs
        home = Path.home()
        mamba_cache = home / ".mamba" / "pkgs"
        if mamba_cache.exists():
            return mamba_cache
        return home / ".conda" / "pkgs"


def _get_all_mamba_cache_dirs() -> list[Path]:
    """Get ALL potential Micromamba/Conda cache directories."""
    cache_dirs = []
    home = Path.home()
    
    # Check standard locations
    candidates = [
        home / ".mamba" / "pkgs",
        home / ".conda" / "pkgs",
        home / "AppData" / "Roaming" / "mamba" / "pkgs",
        home / "AppData" / "Local" / "mamba" / "pkgs",
    ]
    
    # Add environment variable locations
    if "MAMBA_PKGS_DIRS" in os.environ:
        for d in os.environ["MAMBA_PKGS_DIRS"].split(os.pathsep):
            candidates.append(Path(d))
    if "CONDA_PKGS_DIRS" in os.environ:
        for d in os.environ["CONDA_PKGS_DIRS"].split(os.pathsep):
            candidates.append(Path(d))
    if "MAMBA_ROOT_PREFIX" in os.environ:
        candidates.append(Path(os.environ["MAMBA_ROOT_PREFIX"]) / "pkgs")
    
    # Return only those that exist
    for cache_dir in candidates:
        if cache_dir.exists():
            cache_dirs.append(cache_dir)
    
    return cache_dirs


def _clear_conda_cache() -> bool:
    """Clear the Micromamba/Conda package cache, with fallback to manual removal of all cache locations."""
    print_info("Clearing Micromamba package cache...")
    
    # First attempt: use micromamba clean with force flag
    result = _run_micromamba("clean", "--all", "-y", "--force-pkgs-dirs")
    if result.returncode == 0:
        print_success("Package cache cleared.")
        return True
    
    print_warning("micromamba clean failed, attempting manual cache directory removal...")
    
    # Fallback: manually remove ALL cache directories if standard clean fails
    all_cache_dirs = _get_all_mamba_cache_dirs()
    
    if not all_cache_dirs:
        print_warning("No cache directories found")
        return False
    
    all_cleared = True
    for cache_dir in all_cache_dirs:
        try:
            print_info(f"Removing cache directory: {cache_dir}")
            if cache_dir.exists():
                def _handle_readonly(func, path, exc_info):
                    import stat
                    import time
                    try:
                        # Add \\?\ prefix to handle long paths on Windows
                        ext_path = f"\\\\?\\{os.path.abspath(path)}" if platform.system() == "Windows" else path
                        try:
                            os.chmod(ext_path, stat.S_IWRITE)
                            func(ext_path)
                        except Exception:
                            # Retry after a small delay to handle transient file locks
                            time.sleep(0.1)
                            os.chmod(ext_path, stat.S_IWRITE)
                            func(ext_path)
                    except Exception:
                        pass
                
                # Adding \\?\ prefix for long paths
                safe_cache_path = f"\\\\?\\{os.path.abspath(cache_dir)}" if platform.system() == "Windows" else str(cache_dir)
                shutil.rmtree(safe_cache_path, onerror=_handle_readonly)
                
                if cache_dir.exists():
                    # Fallback for Windows if shutil.rmtree completely fails
                    if platform.system() == "Windows":
                        empty_dir = str(cache_dir.parent / f"empty_{cache_dir.name}")
                        os.makedirs(empty_dir, exist_ok=True)
                        subprocess.run(["robocopy", empty_dir, str(cache_dir), "/MIR", "/R:1", "/W:1"], capture_output=True)
                        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(cache_dir)], capture_output=True)
                        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", empty_dir], capture_output=True)
                
                cache_dir.mkdir(parents=True, exist_ok=True)
                print_success(f"Cache cleared: {cache_dir}")
            else:
                print_info(f"Cache directory does not exist: {cache_dir}")
        except Exception as exc:
            print_warning(f"Failed to remove cache directory {cache_dir}: {exc}")
            all_cleared = False
    
    return all_cleared


def _is_cache_error(stderr: str) -> bool:
    """Detect if the error is related to package cache corruption."""
    return (
        "Invalid package cache" in stderr
        or "Cannot find a valid extracted directory cache" in stderr
        or "Package cache error" in stderr
        or "file is missing" in stderr
        or "Error when extracting package" in stderr
        or "Adresář není prázdný" in stderr 
        or "remove_all:" in stderr
    )


def _remove_env(env_path: Path) -> None:
    """Remove a partially created environment directory."""
    if not env_path.exists():
        return

    print_info(f"Removing partially created environment at {env_path}...")
    try:
        def _handle_readonly(func, path, exc_info):
            import stat
            import time
            try:
                ext_path = f"\\\\?\\{os.path.abspath(path)}" if platform.system() == "Windows" else path
                try:
                    os.chmod(ext_path, stat.S_IWRITE)
                    func(ext_path)
                except Exception:
                    time.sleep(0.1)
                    os.chmod(ext_path, stat.S_IWRITE)
                    func(ext_path)
            except Exception:
                pass

        safe_env_path = f"\\\\?\\{os.path.abspath(env_path)}" if platform.system() == "Windows" else str(env_path)
        shutil.rmtree(safe_env_path, onerror=_handle_readonly)

        if env_path.exists() and platform.system() == "Windows":
            empty_dir = str(env_path.parent / f"empty_{env_path.name}")
            os.makedirs(empty_dir, exist_ok=True)
            subprocess.run(["robocopy", empty_dir, str(env_path), "/MIR", "/R:1", "/W:1"], capture_output=True)
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(env_path)], capture_output=True)
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", empty_dir], capture_output=True)

        if not env_path.exists():
            print_success("Environment directory removed.")
        else:
            print_warning("Environment directory still exists; remove it manually.")
    except Exception as exc:
        print_warning(f"Could not remove environment directory: {exc}")


# ── TotalSegmentator licence ─────────────────────────────────────────────────

TOTALSEG_LICENSE_KEY = "aca_3CHUIP91FYK5LV"


def _set_totalseg_license(env_path: Path) -> None:
    """Run ``totalseg_set_license`` inside *env_path* to activate the licence.

    Called automatically after every successful create/update of an
    ``msk_totalseg_*`` environment so the pipeline can run without a manual
    activation step.
    """
    print_step(f"Activating TotalSegmentator licence in {env_path.name}...")
    result = subprocess.run(
        [str(MICROMAMBA_EXE), "run", "-p", str(env_path),
         "totalseg_set_license", "-l", TOTALSEG_LICENSE_KEY],
        capture_output=True,
        text=True,
        env=make_mamba_env(),
    )
    if result.returncode == 0:
        print_success(f"TotalSegmentator licence activated in {env_path.name}.")
    else:
        print_warning(
            f"Could not activate TotalSegmentator licence in {env_path.name}: "
            + (result.stderr or result.stdout).strip()
        )


# ── Public API ────────────────────────────────────────────────────────────────

def get_env_file_hashes(has_gpu: bool = False) -> dict[str, str | None]:
    """Return SHA-256 hashes for every environment YAML."""
    return {
        name: compute_file_hash(yaml_path)
        for name, yaml_path in _env_map(has_gpu).items()
        if yaml_path.exists()
    }


def install_micromamba() -> bool:
    """Download and install Micromamba into ./bin/ (Windows-only for now)."""
    print_check("Attempting automatic Micromamba installation")

    if platform.system() != "Windows":
        raise NotImplementedError(
            "Automatic Micromamba install is only implemented for Windows. "
            "Please install Micromamba manually: https://mamba.readthedocs.io"
        )

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = BIN_DIR / "micromamba.tar.bz2"
    # Determine which version/tag to download. The user can configure the
    # desired micromamba version via `config/config.json` using either
    # `{ "micromamba": { "version": "2.6.0-0" } }` or the top-level
    # key `"micromamba_version": "2.6.0-0"`. If not present, fall back to
    # the project default `MICROMAMBA_DEFAULT_VERSION`.
    version_to_use = None
    try:
        if MAIN_CONFIG_PATH.exists():
            cfg = json.loads(MAIN_CONFIG_PATH.read_text(encoding="utf-8"))
            version_to_use = (
                cfg.get("micromamba", {}).get("version")
                or cfg.get("micromamba_version")
            )
    except Exception:
        version_to_use = None

    if not version_to_use:
        version_to_use = MICROMAMBA_DEFAULT_VERSION

    # Try multiple tag formats: first the plain version (e.g. "2.6.0-0"),
    # then the `v`-prefixed tag (e.g. "v2.6.0-0"), and finally `latest`.
    candidates = [version_to_use, f"v{version_to_use}", "latest"]

    last_exc = None
    for tag in candidates:
        try:
            if tag == "latest":
                url = MICROMAMBA_WIN_URL
            else:
                url = MICROMAMBA_WIN_URL_TEMPLATE.format(tag=tag)
            print_info(f"Downloading micromamba from: {url}")
            urllib.request.urlretrieve(url, str(tmp_file))
            with tarfile.open(tmp_file, "r:bz2") as tar:
                tar.extractall(path=BIN_DIR)
            tmp_file.unlink(missing_ok=True)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            print_warning(f"Failed to download micromamba from {tag}: {exc}")

    if last_exc is not None:
        print_error(f"Failed to install Micromamba: {last_exc}")
        return False
    # Locate the extracted micromamba binary somewhere under BIN_DIR and
    # copy it to the expected MICROMAMBA_EXE path.
    micromamba_name = "micromamba.exe" if platform.system() == "Windows" else "micromamba"
    found = None
    for p in BIN_DIR.rglob(micromamba_name):
        if p.is_file():
            found = p
            break

    if not found:
        print_error("Micromamba binary not found after extraction.")
        return False

    try:
        # Ensure bin dir exists and copy
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        import shutil as _shutil
        _shutil.copy2(found, MICROMAMBA_EXE)
        # Make executable on non-Windows
        if platform.system() != "Windows":
            MICROMAMBA_EXE.chmod(MICROMAMBA_EXE.stat().st_mode | 0o111)
        print_success(f"Micromamba installed to {MICROMAMBA_EXE}")
    except Exception as exc:
        print_error(f"Failed to place Micromamba binary: {exc}")
        return False

    os.environ["PATH"] = str(MICROMAMBA_EXE.parent) + os.pathsep + os.environ.get("PATH", "")
    return True


def update_conda_envs(config: dict, has_gpu: bool = False) -> tuple[bool, dict]:
    """Create or update all required Micromamba environments (with change detection)."""
    print_check("Checking Micromamba environments")

    envs = _env_map(has_gpu)
    previous_hashes: dict = config.get("env_file_hashes", {})
    current_hashes = get_env_file_hashes(has_gpu)
    all_ok = True
    cache_cleared = False

    for env_name, yaml_path in envs.items():
        if not yaml_path.exists():
            print_error(f"Missing environment recipe: {yaml_path}")
            all_ok = False
            continue

        env_path  = (ENVS_DIR / env_name).resolve()
        env_exists = _python_exe(env_path).exists()
        prev_hash  = previous_hashes.get(env_name)
        curr_hash  = current_hashes.get(env_name)

        if not env_exists:
            print_step(f"Creating '{env_name}' from {yaml_path}...")
            result = _run_micromamba("create", "-p", str(env_path), "-f", str(yaml_path), "-y")
            action = "created"
        elif prev_hash and curr_hash and prev_hash != curr_hash:
            print_step(f"Updating '{env_name}' (YAML changed)...")
            result = _run_micromamba("env", "update", "-p", str(env_path), "-f", str(yaml_path), "-y")
            action = "updated"
        else:
            print_success(f"'{env_name}' is up-to-date.")
            if env_name == "msk_base":
                patch_snakemake_benchmark(env_path)
            continue

        if result.returncode == 0:
            print_success(f"'{env_name}' {action} successfully.")
            if env_name == "msk_base":
                patch_snakemake_benchmark(env_path)
            if env_name.startswith("msk_totalseg_"):
                _set_totalseg_license(env_path)
        else:
            # Check if this is a cache error
            error_output = result.stderr or result.stdout
            if _is_cache_error(error_output):
                print_warning(f"Package cache error detected during {action} of '{env_name}'.")
                
                if not cache_cleared:
                    if Confirm.ask("Clear package cache and retry?", default=True):
                        _remove_env(env_path)
                        if _clear_conda_cache():
                            cache_cleared = True
                            print_step(f"Retrying '{env_name}' creation...")
                            if not env_exists:
                                result = _run_micromamba("create", "-p", str(env_path), "-f", str(yaml_path), "-y")
                            else:
                                result = _run_micromamba("env", "update", "-p", str(env_path), "-f", str(yaml_path), "-y")

                            if result.returncode == 0:
                                print_success(f"'{env_name}' {action} successfully after cache clear.")
                                if env_name == "msk_base":
                                    patch_snakemake_benchmark(env_path)
                                if env_name.startswith("msk_totalseg_"):
                                    _set_totalseg_license(env_path)
                            else:
                                print_error(f"Error ({action}) '{env_name}' after cache clear (code {result.returncode}):")
                                if result.stderr:
                                    print_subprocess_error(result)
                                all_ok = False
                        else:
                            all_ok = False
                    else:
                        all_ok = False
                else:
                    print_error(f"Error ({action}) '{env_name}' persists after cache clear (code {result.returncode}):")
                    if result.stderr:
                        print_subprocess_error(result)
                    all_ok = False
            else:
                print_error(f"Error ({action}) '{env_name}' (code {result.returncode}):")
                if result.stderr:
                    print_subprocess_error(result)
                all_ok = False

    config["env_file_hashes"] = current_hashes
    return all_ok, config


def patch_snakemake_benchmark(env_path: Path):
    """
    Automatically patch Snakemake benchmark.py on Windows to fix missing `pss` attribute.
    CHECK: https://github.com/snakemake/snakemake/issues/4159
    """
    if platform.system() != "Windows":
        return
    site_packages = env_path / "Lib" / "site-packages"
    benchmark_py = site_packages / "snakemake" / "benchmark.py"
    if not benchmark_py.exists():
        return
    
    content = benchmark_py.read_text(encoding="utf-8")
    # Patch `pss += meminfo.pss` -> `pss += getattr(meminfo, "pss", 0)`
    if 'pss += meminfo.pss' in content and 'getattr(meminfo, "pss", 0)' not in content:
        content = content.replace('pss += meminfo.pss', 'pss += getattr(meminfo, "pss", 0)')
        benchmark_py.write_text(content, encoding="utf-8")
        print_success("Patched snakemake/benchmark.py (missing `pss` on Windows fix)")


def check_micromamba(config: dict, has_gpu: bool = False) -> tuple[bool, dict]:
    """Ensure Micromamba is available and all envs are up-to-date."""
    print_check("Checking for Micromamba")

    if shutil.which("micromamba"):
        print_success("Micromamba found in PATH.")
    elif MICROMAMBA_EXE.exists():
        print_success(f"Micromamba found locally at {MICROMAMBA_EXE}.")
        os.environ["PATH"] = str(MICROMAMBA_EXE.parent) + os.pathsep + os.environ["PATH"]
    else:
        print_warning("Micromamba not found.")
        if not Confirm.ask("Install Micromamba automatically?", default=True):
            return False, config
        try:
            if not install_micromamba():
                return False, config
        except NotImplementedError as exc:
            print_error(str(exc))
            return False, config

    env_ok, config = update_conda_envs(config, has_gpu=has_gpu)
    if not env_ok:
        print_error("One or more environment checks failed.")
        return False, config

    return True, config