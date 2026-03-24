import os
import sys
import json
import yaml
import shutil
import subprocess
import platform
import hashlib
import signal
import tempfile
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

console = Console()


def terminate_process_tree(pid):
    """Terminate process tree for a given PID across platforms."""
    if pid is None:
        return

    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception as e:
        console.print(f"[yellow]! Failed to terminate process tree for PID {pid}: {e}[/yellow]")


def print_header():
    console.print(
        Panel.fit(
            "[bold cyan]MSK-PIPE Orchestrator[/bold cyan]\nPre-flight checks and system setup",
            border_style="cyan",
        )
    )


def compute_file_hash(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(4096), b""):
                sha256.update(block)
        return sha256.hexdigest()
    except Exception as e:
        console.print(f"[yellow]! Failed to compute hash for {filepath}: {e}[/yellow]")
        return None


def get_env_file_hashes(has_gpu=False):
    """Get current hashes of all environment YAML files."""
    muscle_env_name = "msk_musclemap_gpu" if has_gpu else "msk_musclemap_cpu"
    muscle_env_yaml = (
        "config/env_musclemap_gpu.yaml" if has_gpu else "config/env_musclemap_cpu.yaml"
    )

    envs = {
        "msk_base": "config/env_base.yaml",
        muscle_env_name: muscle_env_yaml,
        "msk_totalseg_cpu": "config/env_totalseg_cpu.yaml",
        "msk_totalseg_gpu": "config/env_totalseg_gpu.yaml",
    }
    hashes = {}
    for env_name, yaml_path in envs.items():
        if Path(yaml_path).exists():
            hashes[env_name] = compute_file_hash(yaml_path)
        else:
            hashes[env_name] = None
    return hashes


def update_conda_envs(user_settings, has_gpu=False):
    """Create or update Micromamba environments with change detection."""
    console.print(
        "\n[yellow]Checking and updating necessary Micromamba environments...[/yellow]"
    )

    muscle_env_name = "msk_musclemap_gpu" if has_gpu else "msk_musclemap_cpu"
    muscle_env_yaml = (
        "config/env_musclemap_gpu.yaml" if has_gpu else "config/env_musclemap_cpu.yaml"
    )

    envs = {
        "msk_base": "config/env_base.yaml",
        muscle_env_name: muscle_env_yaml,
        "msk_totalseg_cpu": "config/env_totalseg_cpu.yaml",
        "msk_totalseg_gpu": "config/env_totalseg_gpu.yaml",
    }

    # Load previous hashes from user_settings
    previous_hashes = user_settings.get("env_file_hashes", {})
    current_hashes = get_env_file_hashes(has_gpu=has_gpu)

    all_ok = True

    for env_name, yaml_path in envs.items():
        env_path = Path(f"./envs/{env_name}").resolve()
        python_exe = env_path / (
            "python.exe" if platform.system() == "Windows" else "bin/python"
        )

        if not Path(yaml_path).exists():
            console.print(f"[red]Missing environment recipe: {yaml_path}[/red]")
            all_ok = False
            continue

        prev_hash = previous_hashes.get(env_name)
        curr_hash = current_hashes.get(env_name)

        # Check if environment exists
        env_exists = python_exe.exists()

        if not env_exists:
            # Environment doesn't exist - create it
            console.print(
                f"[cyan]Creating new environment '{env_name}' from {yaml_path}...[/cyan]"
            )
            result = subprocess.run(
                ["micromamba", "create", "-p", str(env_path), "-f", yaml_path, "-y"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print(
                    f"[green]✓ Environment '{env_name}' was created successfully.[/green]"
                )
            else:
                console.print(
                    f"[red]✗ Error while creating '{env_name}' (return code: {result.returncode}):[/red]"
                )
                console.print(f"[red]{result.stderr}[/red]")
                all_ok = False

        elif prev_hash and curr_hash and prev_hash != curr_hash:
            # Environment exists but YAML changed - update it
            console.print(
                f"[cyan]Detected changes in {yaml_path} for '{env_name}'. Updating environment...[/cyan]"
            )
            result = subprocess.run(
                ["micromamba", "env", "update", "-p", str(env_path), "-f", yaml_path, "-y"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print(
                    f"[green]✓ Environment '{env_name}' was updated successfully.[/green]"
                )
            else:
                console.print(
                    f"[red]✗ Error while updating '{env_name}' (return code: {result.returncode}):[/red]"
                )
                console.print(f"[red]{result.stderr}[/red]")
                all_ok = False

        else:
            # Environment exists and YAML unchanged
            console.print(
                f"[green]✓ Environment '{env_name}' is already up-to-date.[/green]"
            )

    # Save current hashes for future comparison
    user_settings["env_file_hashes"] = current_hashes
    return all_ok, user_settings


def check_gpu():
    console.print("[yellow]Checking for NVIDIA GPU (RTX)...[/yellow]")
    has_gpu = False
    try:
        result = subprocess.run(
            ["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode == 0:
            console.print("[green]✓ NVIDIA GPU detected.[/green]")
            has_gpu = True
        else:
            console.print(
                "[yellow]! nvidia-smi returned non-zero code. GPU execution might not be available.[/yellow]"
            )
    except FileNotFoundError:
        console.print(
            "[yellow]! nvidia-smi not found. Assuming CPU only environment for TotalSegmentator.[/yellow]"
        )
    return has_gpu


def install_micromamba():
    console.print("\n[yellow]Attempting automatic Micromamba installation...[/yellow]")
    import urllib.request
    import tarfile
    import zipfile

    mamba_dir = Path("bin").resolve()
    mamba_bin = (
        mamba_dir / "micromamba.exe"
        if platform.system() == "Windows"
        else mamba_dir / "micromamba"
    )

    try:
        if platform.system() == "Windows":
            mamba_dir.mkdir(exist_ok=True, parents=True)
            url = "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64.tar.bz2"
            tmp_file = mamba_dir / "micromamba.tar.bz2"
            urllib.request.urlretrieve(url, str(tmp_file))

            with tarfile.open(tmp_file, "r:bz2") as tar:
                tar.extractall(path=mamba_dir)
            tmp_file.unlink()

            # The executable is inside Library/bin on windows tarballs from conda-forge
            extracted_bin = mamba_dir / "Library" / "bin" / "micromamba.exe"
            if extracted_bin.exists():
                shutil.copy2(extracted_bin, mamba_bin)

            console.print(f"[green]✓ Micromamba installed to {mamba_bin}[/green]")

        else:
            # Linux / Mac logic mostly
            # For simplicity on Windows host right now
            pass

    except Exception as e:
        console.print(f"[red]✗ Failed to install Micromamba automatically: {e}[/red]")
        return False

    os.environ["PATH"] = str(mamba_bin.parent) + os.pathsep + os.environ["PATH"]
    return True




def check_micromamba(user_settings, has_gpu=False):
    console.print("\n[yellow]Checking for Micromamba...[/yellow]")
    mamba_path = shutil.which("micromamba")

    if mamba_path:
        console.print(f"[green]✓ Micromamba found at {mamba_path}.[/green]")
    else:
        # Check custom bin directory path just in case
        custom_path = Path("bin").resolve() / (
            "micromamba.exe" if platform.system() == "Windows" else "micromamba"
        )
        if custom_path.exists():
            console.print(
                f"[green]✓ Micromamba found locally at {custom_path}. Adding to PATH.[/green]"
            )
            os.environ["PATH"] = (
                str(custom_path.parent) + os.pathsep + os.environ["PATH"]
            )

        else:
            console.print(
                "[yellow]! Micromamba is not installed or not in PATH.[/yellow]"
            )
            if Confirm.ask(
                "Do you want to automatically install Micromamba tools?", default=True
            ):
                if not install_micromamba():
                    return False, user_settings
            else:
                return False, user_settings

    env_ok, user_settings = update_conda_envs(user_settings, has_gpu=has_gpu)
    if not env_ok:
        console.print("[red]✗ One or more environment checks/updates failed.[/red]")
        return False, user_settings

    return True, user_settings


def check_matlab(mw_path):
    console.print("\n[yellow]Checking MATLAB Installation...[/yellow]")
    if not shutil.which("matlab"):
        console.print("[red]✗ MATLAB executable not found in PATH.[/red]")
        console.print(
            "Make sure MATLAB >R2018b is installed and added to your system PATH."
        )
        return False

    console.print("[green]✓ MATLAB executable found.[/green]")
    console.print(
        "Validating required Toolboxes (Curve Fitting, Statistics and ML) and OpenSim API..."
    )

    matlab_cmd = (
        "try, "
        "ver_info = ver; "
        "has_curve = any(strcmp({ver_info.Name}, 'Curve Fitting Toolbox')); "
        "has_stat = any(strcmp({ver_info.Name}, 'Statistics and Machine Learning Toolbox')); "
        "if has_curve && has_stat, disp('TOOLBOXES_OK'); else, disp('TOOLBOXES_MISSING'); end; "
        "catch, disp('ERROR_TOOLBOX'); end; "
        "quit;"
    )

    opensim_check_cmd = (
        "try, "
        "v = org.opensim.modeling.opensimCommon.GetVersion(); "
        "w = which('org-opensim-modeling.jar'); "
        "fprintf('OPENSIM_READY|%s|%s\\n', char(v), char(w)); "
        "catch, fprintf('OPENSIM_NOT_CONFIGURED\\n'); end; "
        "quit;"
    )

    try:
        # `-wait` is useful on Windows to block until MATLAB finishes
        args = ["matlab", "-wait", "-batch", matlab_cmd]
        os_args = ["matlab", "-wait", "-batch", opensim_check_cmd]

        if platform.system() != "Windows":
            args.remove("-wait")
            os_args.remove("-wait")

        result = subprocess.run(args, capture_output=True, text=True)
        if "TOOLBOXES_OK" in result.stdout:
            console.print("[green]✓ Required MATLAB Toolboxes found.[/green]")
        else:
            console.print("[red]✗ Required MATLAB Toolboxes are missing.[/red]")
            return False

        os_result = subprocess.run(os_args, capture_output=True, text=True)
        is_opensim_ready = False

        for line in os_result.stdout.splitlines():
            if "OPENSIM_READY" in line:
                is_opensim_ready = True
                try:
                    _, version, jar_path = line.split("|", 2)
                    console.print(
                        f"[green]✓ OpenSim API version {version.strip()} is configured and ready.[/green]"
                    )
                    console.print(f"  [cyan]JAR path: {jar_path.strip()}[/cyan]")
                except ValueError:
                    console.print(
                        "[green]✓ OpenSim API is configured (custom format).[/green]"
                    )
                break

        if not is_opensim_ready:
            console.print(
                "[yellow]! OpenSim API is not yet configured in MATLAB. Running setup script...[/yellow]"
            )
            if not setup_opensim_matlab(mw_path):
                return False

    except Exception as e:
        console.print(f"[red]✗ Failed to execute MATLAB checks: {e}[/red]")
        return False

    return True


def setup_opensim_matlab(mw_build_path):
    if not mw_build_path:
        console.print(
            "[yellow]! Muscle Wrapping path was not provided; skipping OpenSim configuration.[/yellow]"
        )
        return False

    # Definice cest na základě tvého upřesnění
    # mw_build_path obvykle míří na build složku
    mw_build_dir = Path(mw_build_path)
    install_dir = mw_build_dir / "ExternalLibs" / "OpenSim" / "Bin"

    # PŘESNÁ CESTA PODLE TVÉHO NÁLEZU:
    script_dir = install_dir / "Resources" / "Code" / "Matlab"
    bin_dir = install_dir / "bin"

    if not (script_dir / "configureOpenSim.m").exists():
        console.print(
            f"[red]✗ Critical error: configureOpenSim.m not found in {script_dir}[/red]"
        )
        return False

    # Přidání bin do PATH pro aktuální relaci (klíčové pro načtení .dll knihoven)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

    console.print(f"[cyan]Configuring OpenSim from: {script_dir}[/cyan]")

    # Sestavení příkazu pro MATLAB:
    # 1. Přidáme složku se skriptem do path
    # 2. Definujeme proměnnou OPENSIM_INSTALL_DIR, kterou skript interně hledá
    # 3. Spustíme skript pomocí příkazu run()
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

    # Spuštění MATLABu v batch režimu
    args = (
        ["matlab", "-wait", "-batch", setup_cmd]
        if platform.system() == "Windows"
        else ["matlab", "-batch", setup_cmd]
    )

    try:
        console.print(
            "[yellow]Starting MATLAB to run configureOpenSim script...[/yellow]"
        )
        res = subprocess.run(args, capture_output=True, text=True)

        if "SETUP_SCRIPT_COMPLETED" not in res.stdout:
            console.print(
                "[red]✗ OpenSim configuration in MATLAB failed while running the script.[/red]"
            )
            console.print(f"[white]MATLAB output:[/white]\n{res.stdout}")
            return False
    except Exception as e:
        console.print(f"[red]✗ Unexpected error while communicating with MATLAB: {e}[/red]")
        return False

    # Druhé volání pro ověření API
    console.print(
        "[yellow]Verifying API in a new MATLAB instance...[/yellow]"
    )
    test_cmd_2 = (
        "try, "
        "v = org.opensim.modeling.opensimCommon.GetVersion(); "
        "disp(['SETUP_SUCCESS_VER:', char(v)]); "
        "catch e, disp('SETUP_FINAL_FAILED'); disp(e.message); end; "
        "quit;"
    )

    args_2 = (
        ["matlab", "-wait", "-batch", test_cmd_2]
        if platform.system() == "Windows"
        else ["matlab", "-batch", test_cmd_2]
    )

    try:
        res2 = subprocess.run(args_2, capture_output=True, text=True)

        if "SETUP_SUCCESS_VER" in res2.stdout:
            version = "neznámá"
            for line in res2.stdout.splitlines():
                if "SETUP_SUCCESS_VER:" in line:
                    version = line.split(":", 1)[1].strip()
            console.print(
                f"[green]✓ OpenSim API version {version} was configured successfully in MATLAB.[/green]"
            )
            return True
        else:
            console.print(
                "[red]✗ OpenSim verification in MATLAB failed after configuration.[/red]"
            )
            console.print(f"[white]MATLAB output:[/white]\n{res2.stdout}")
            return False
    except Exception as e:
        console.print(f"[red]✗ Unexpected error while communicating with MATLAB: {e}[/red]")
        return False


def check_and_setup_musclemap(musclemap_env_name):
    """Check for MuscleMap repository and ensure it is installed in selected msk_musclemap_* env."""
    console.print("\n[yellow]Checking MuscleMap repository...[/yellow]")

    musclemap_path = Path("src/MuscleMap")

    def install_musclemap_in_env(repo_path: Path) -> bool:
        env_path = Path(f"envs/{musclemap_env_name}").resolve()
        python_exe = env_path / (
            "python.exe" if platform.system() == "Windows" else "bin/python"
        )
        is_gpu_env = musclemap_env_name.endswith("_gpu")

        if not python_exe.exists():
            console.print(
                f"[red]✗ Python executable not found for {musclemap_env_name} at {python_exe}[/red]"
            )
            return False

        console.print(
            f"[cyan]Installing MuscleMap into {musclemap_env_name} environment...[/cyan]"
        )

        if is_gpu_env:
            req_file = repo_path / "requirements.txt"
            if not req_file.exists():
                console.print(
                    f"[red]✗ requirements.txt not found at {req_file}[/red]"
                )
                return False

            console.print(
                "[cyan]GPU env detected: installing MuscleMap deps without torch/torchvision to preserve pytorch-cuda.[/cyan]"
            )

            tmp_req_path = None
            try:
                filtered_lines = []
                with open(req_file, "r", encoding="utf-8") as f:
                    for line in f:
                        raw = line.strip()
                        if not raw or raw.startswith("#"):
                            continue
                        pkg = raw.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0]
                        pkg = pkg.strip().lower()
                        if pkg in {"torch", "torchvision", "torchaudio"}:
                            continue
                        filtered_lines.append(raw)

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix="_musclemap_no_torch.txt", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write("\n".join(filtered_lines) + "\n")
                    tmp_req_path = tf.name

                deps_result = subprocess.run(
                    [
                        "micromamba",
                        "run",
                        "-p",
                        str(env_path),
                        "python",
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        str(tmp_req_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                )

                if deps_result.returncode != 0:
                    console.print("[red]✗ MuscleMap dependency install failed.[/red]")
                    if deps_result.stderr:
                        console.print(f"[white]{deps_result.stderr}[/white]")
                    return False

            finally:
                if tmp_req_path and Path(tmp_req_path).exists():
                    try:
                        Path(tmp_req_path).unlink()
                    except Exception:
                        pass

            install_cmd = [
                "micromamba",
                "run",
                "-p",
                str(env_path),
                "python",
                "-m",
                "pip",
                "install",
                "-e",
                str(repo_path.resolve()),
                "--no-deps",
            ]
        else:
            install_cmd = [
                "micromamba",
                "run",
                "-p",
                str(env_path),
                "python",
                "-m",
                "pip",
                "install",
                "-e",
                str(repo_path.resolve()),
            ]

        install_result = subprocess.run(
            install_cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )

        if install_result.returncode != 0:
            console.print("[red]✗ MuscleMap pip install failed.[/red]")
            if install_result.stderr:
                console.print(f"[white]{install_result.stderr}[/white]")
            return False

        verify_result = subprocess.run(
            [
                "micromamba",
                "run",
                "-p",
                str(env_path),
                "mm_segment",
                "-h",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if verify_result.returncode != 0:
            console.print(
                "[yellow]! MuscleMap installation finished, but mm_segment verification failed.[/yellow]"
            )
            if verify_result.stderr:
                console.print(f"[white]{verify_result.stderr}[/white]")
            return False

        console.print("[green]✓ MuscleMap installed and mm_segment is available.[/green]")
        return True

    # Check if MuscleMap exists
    if musclemap_path.exists() and musclemap_path.is_dir():
        console.print(
            "[green]✓ MuscleMap found in default location (src/MuscleMap).[/green]"
        )
        return install_musclemap_in_env(musclemap_path)

    # If not, offer to auto-download
    console.print(
        "[yellow]! MuscleMap repository not found at src/MuscleMap.[/yellow]"
    )
    auto_download = Confirm.ask(
        "Would you like to automatically clone MuscleMap from GitHub?", default=True
    )

    if not auto_download:
        console.print(
            "[yellow]MuscleMap is optional. Pipeline may work without it for muscle segmentation.[/yellow]"
        )
        return False

    # Create src directory if needed
    src_dir = Path("src")
    src_dir.mkdir(exist_ok=True)

    # Clone MuscleMap
    try:
        console.print("[cyan]Cloning MuscleMap repository...[/cyan]")
        result = subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/MuscleMap/MuscleMap.git",
                str(musclemap_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            console.print("[green]✓ MuscleMap successfully cloned.[/green]")
            return install_musclemap_in_env(musclemap_path)
        else:
            console.print(
                f"[red]Failed to clone MuscleMap: {result.stderr}[/red]"
            )
            return False
    except Exception as e:
        console.print(f"[red]Error cloning MuscleMap: {e}[/red]")
        return False


def find_staple_and_opensim(user_settings):
    console.print("\n[yellow]Checking MSK-STAPLE location...[/yellow]")

    staple_path = Path("src/STAPLE")
    if staple_path.exists() and staple_path.is_dir():
        console.print(
            "[green]✓ MSK-STAPLE found in default location (src/STAPLE).[/green]"
        )
        user_settings["staple_path"] = str(staple_path.resolve())
        return True
    else:
        staple_env = os.environ.get("STAPLE_PATH")
        if staple_env and Path(staple_env).exists():
            console.print(
                f"[green]✓ MSK-STAPLE found from PATH at {staple_env}[/green]"
            )
            user_settings["staple_path"] = staple_env
            return True
        else:
            path_input = Prompt.ask(
                "[yellow]MSK-STAPLE not found. Please provide absolute path to STAPLE[/yellow]",
                default=str(Path("src/STAPLE").resolve()),
            )
            resolved = Path(path_input).resolve()
            if resolved.exists() and resolved.is_dir():
                user_settings["staple_path"] = str(resolved)
                console.print(f"[green]✓ MSK-STAPLE found at {resolved}.[/green]")
                return True

            console.print(f"[red]✗ MSK-STAPLE path is invalid: {resolved}[/red]")
            return False


def compile_mask2stl(user_settings):
    console.print("\n[yellow]Checking mask2stl (C++) binaries...[/yellow]")

    if "mask2stl_path" not in user_settings:
        default_path = str(Path("src/cpp/3_mask2stl").resolve())
        path_input = Prompt.ask(
            "Enter path to mask2stl directory", default=default_path
        )
        user_settings["mask2stl_path"] = path_input

    mask2stl_dir = Path(user_settings["mask2stl_path"]).resolve()
    build_dir = mask2stl_dir / "build"
    src_dir = mask2stl_dir / "src"

    exe_name = "mask2stl.exe" if platform.system() == "Windows" else "mask2stl"
    exe_path = (
        build_dir / "Release" / exe_name
        if platform.system() == "Windows"
        else build_dir / exe_name
    )

    if exe_path.exists():
        console.print("[green]✓ mask2stl binary is already compiled and ready.[/green]")
        return True

    console.print(
        "[yellow]mask2stl binary not found. Initiating CMake compilation...[/yellow]"
    )

    # Check CMake existance
    if not shutil.which("cmake"):
        console.print(
            "[red]✗ CMake not found in PATH. Please install CMake >= 3.10 to compile C++ helpers.[/red]"
        )
        return False

    mw_path_str = user_settings.get("muscle_wrapping_path")
    if not mw_path_str:
        console.print(
            "[red]✗ muscle_wrapping_path is not defined in user_settings. Cannot find VTK.[/red]"
        )
        return False

    mw_build_dir = Path(mw_path_str).resolve()
    auto_candidates = []

    saved_vtk_path = user_settings.get("vtk_path")
    if saved_vtk_path:
        auto_candidates.append(Path(saved_vtk_path).resolve())

    auto_candidates.extend([
        mw_build_dir / "ExternalLibs" / "VTK" / "Bin" / "lib" / "cmake" / "vtk-9.4",
        mw_build_dir / "ExternalLibs" / "VTK" / "Bin",
        mw_build_dir / "ExternalLibs" / "VTK",
    ])

    def resolve_vtk_cmake_dir(base_path):
        if (base_path / "vtk-config.cmake").exists():
            return base_path

        cmake_root = base_path / "lib" / "cmake"
        if cmake_root.exists():
            for vtk_dir in sorted(cmake_root.glob("vtk-*")):
                if (vtk_dir / "vtk-config.cmake").exists():
                    return vtk_dir

        return None

    vtk_cmake_dir = None
    for candidate in auto_candidates:
        vtk_cmake_dir = resolve_vtk_cmake_dir(candidate)
        if vtk_cmake_dir:
            break

    if not vtk_cmake_dir:
        console.print("[yellow]! VTK was not found automatically.[/yellow]")
        user_vtk = Prompt.ask(
            "Enter VTK path (folder with VTKConfig.cmake or installation root)",
            default="",
        ).strip()

        if not user_vtk:
            console.print("[red]✗ VTK path was not provided. Exiting.[/red]")
            return False

        vtk_cmake_dir = resolve_vtk_cmake_dir(Path(user_vtk).resolve())
        if not vtk_cmake_dir:
            console.print(
                "[red]✗ The provided path does not contain VTKConfig.cmake. Exiting.[/red]"
            )
            return False

    user_settings["vtk_path"] = str(vtk_cmake_dir)

    console.print(f"Running CMake with VTK_DIR from {vtk_cmake_dir} ...")
    cmake_cmd = [
        "cmake",
        "-S",
        str(src_dir),
        "-B",
        str(build_dir),
        f"-DVTK_DIR={str(vtk_cmake_dir)}",
    ]

    build_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(cmake_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]CMake configuration failed:\n{result.stderr}[/red]")
        return False

    console.print("[green]✓ CMake configuration successful.[/green]")
    console.print("Building mask2stl project...")
    build_result = subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release"]
    )

    if build_result.returncode == 0:
        console.print("[green]✓ mask2stl compiled successfully.[/green]")
        return True
    else:
        console.print("[red]✗ mask2stl build step failed.[/red]")
        return False


def check_muscle_wrapping(user_settings):
    console.print("\n[yellow]Checking Muscle Wrapping 2.0...[/yellow]")

    saved_path = user_settings.get("muscle_wrapping_path")
    if saved_path:
        default_mw_dir = str(Path(saved_path).resolve())
    else:
        default_mw_dir = str(Path("C:/muscle-wrapping-2.0/build").resolve())

    mw_dir_str = Prompt.ask(
        "Enter path to Muscle Wrapping 2.0 build directory", default=default_mw_dir
    )
    mw_build_dir = Path(mw_dir_str)

    dll_path = mw_build_dir / "Bin" / "OsimMuscleGeneratorTool.dll"

    if dll_path.exists() and dll_path.is_file():
        console.print(f"[green]✓ Muscle Wrapping DLL found at {dll_path}.[/green]")
        return str(mw_build_dir.resolve())
    else:
        console.print(f"[red]✗ Muscle Wrapping DLL not found at {dll_path}.[/red]")
        return None


def main():
    print_header()

    # Default objects
    config = {"snakemake_env": {}}
    user_settings = {}

    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    user_settings_path = config_dir / "user_settings.yaml"
    main_config_path = config_dir / "config.json"

    # Load user_settings.yaml
    if user_settings_path.exists():
        try:
            with open(user_settings_path, "r", encoding="utf-8") as f:
                loaded_settings = yaml.safe_load(f)
                if isinstance(loaded_settings, dict):
                    user_settings = loaded_settings
                    console.print(
                        "[green]✓ Existing user_settings.yaml loaded.[/green]"
                    )
        except Exception as e:
            console.print(
                f"[yellow]! Failed to load existing user_settings.yaml: {e}[/yellow]"
            )

    # Load config.json
    if main_config_path.exists():
        try:
            with open(main_config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                if isinstance(loaded_config, dict):
                    config = loaded_config
                    console.print("[green]✓ Existing config.json loaded.[/green]")
        except Exception as e:
            console.print(
                f"[yellow]! Failed to load existing config.json: {e}[/yellow]"
            )

    if user_settings.get("skip_preflight_checks", False):
        console.print(
            "[yellow]! 'skip_preflight_checks' is ignored: all pre-flight checks are mandatory.[/yellow]"
        )

    has_gpu = check_gpu()
    user_settings["has_gpu"] = has_gpu
    config["snakemake_env"] = config.get("snakemake_env", {})
    config["snakemake_env"]["totalseg"] = (
        "env_totalseg_gpu.yaml" if has_gpu else "env_totalseg_cpu.yaml"
    )
    config["snakemake_env"]["musclemap"] = (
        "env_musclemap_gpu.yaml" if has_gpu else "env_musclemap_cpu.yaml"
    )

    success, user_settings = check_micromamba(user_settings, has_gpu=has_gpu)
    if not success:
        console.print("[bold red]❌ Pre-flight failed: Micromamba/environment setup failed.[/bold red]")
        sys.exit(1)

    mw_path = check_muscle_wrapping(user_settings)
    if not mw_path:
        console.print("[bold red]❌ Pre-flight failed: Muscle Wrapping is not available.[/bold red]")
        sys.exit(1)

    user_settings["muscle_wrapping_path"] = mw_path
    bin_dir = Path(mw_path) / "ExternalLibs" / "OpenSim" / "Bin" / "bin"
    if bin_dir.exists():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

    if not check_matlab(mw_path):
        console.print("[bold red]❌ Pre-flight failed: MATLAB/OpenSim check failed.[/bold red]")
        sys.exit(1)

    if not find_staple_and_opensim(user_settings):
        console.print("[bold red]❌ Pre-flight failed: MSK-STAPLE path check failed.[/bold red]")
        sys.exit(1)

    musclemap_env_name = (
        config["snakemake_env"]["musclemap"]
        .replace("env_", "msk_")
        .replace(".yaml", "")
    )
    if not check_and_setup_musclemap(musclemap_env_name):
        console.print("[bold red]❌ Pre-flight failed: MuscleMap setup/check failed.[/bold red]")
        sys.exit(1)

    if not compile_mask2stl(user_settings):
        console.print(
            "[bold red]❌ Pre-flight failed: mask2stl is not available. Pipeline will not start.[/bold red]"
        )
        sys.exit(1)

    input_format = user_settings.get("input_format")
    if not input_format:
        console.print("\n[yellow]Select input data format to process:[/yellow]")
        console.print("1) auto (detect automatically)")
        console.print("2) nifti (.nii or .nii.gz)")
        console.print("3) dicom (folder with .dcm files)")
        console.print("4) raw (.raw file with coordinates.txt)")
        val = Prompt.ask(
            "Enter choice (1-4)", choices=["1", "2", "3", "4"], default="1"
        )
        mapping = {"1": "auto", "2": "nifti", "3": "dicom", "4": "raw"}
        user_settings["input_format"] = mapping[val]

    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    with open(user_settings_path, "w", encoding="utf-8") as f:
        yaml.dump(user_settings, f, default_flow_style=False)
    console.print(
        f"\n[bold green]✓ user_settings.yaml successfully written to {user_settings_path}.[/bold green]"
    )

    main_config_path = config_dir / "config.json"
    with open(main_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    console.print(
        f"[bold green]✓ config.json successfully written to {main_config_path}.[/bold green]"
    )

    console.print(
        Panel.fit(
            "[bold cyan]MSK-PIPE Pre-flight checks / Initialization completed.[/bold cyan]",
            border_style="cyan",
        )
    )

    # Auto run Snakemake logic
    auto_run = user_settings.get("auto_run_pipeline")
    if auto_run is None:
        auto_run_str = Prompt.ask(
            "Do you want to start the Snakemake pipeline now? (y/n)", default="y"
        )
        auto_run = auto_run_str.strip().lower() in ["y", "yes", "true", "1"]

    if auto_run:
        cores_setting = user_settings.get("snakemake_cores")
        if not cores_setting:
            cores_setting = Prompt.ask(
                "How many CPU cores should Snakemake use? (e.g. 1, 4, or 'all')",
                default="1",
            )
            user_settings["snakemake_cores"] = cores_setting
            # Save the cores setting so it doesn't ask next time if skip_preflight is enabled
            with open(user_settings_path, "w", encoding="utf-8") as f:
                yaml.dump(user_settings, f, default_flow_style=False)

        generate_report = user_settings.get("generate_snakemake_report")
        if generate_report is None:
            generate_report = Confirm.ask(
                "Do you want to generate a Snakemake HTML report after the run?",
                default=True,
            )
            user_settings["generate_snakemake_report"] = bool(generate_report)
            with open(user_settings_path, "w", encoding="utf-8") as f:
                yaml.dump(user_settings, f, default_flow_style=False)

        console.print(
            f"\n[bold green]🚀 Launching Snakemake pipeline (cores: {cores_setting})...[/bold green]"
        )

        env_base_path = str(Path("envs/msk_base").resolve())

        micromamba_exe = "./bin/micromamba.exe"

        current_env = os.environ.copy()
        current_env["CONDA_EXE"] = micromamba_exe

        cmd = [
            micromamba_exe,
            "run",
            "-p",
            env_base_path,
            "snakemake",
            "--cores",
            str(cores_setting),
        ]

        pipeline_proc = None
        try:
            popen_kwargs = {}
            if platform.system() == "Windows":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["preexec_fn"] = os.setsid

            pipeline_proc = subprocess.Popen(cmd, env=current_env, **popen_kwargs)
            pipeline_return = pipeline_proc.wait()
            if pipeline_return != 0:
                raise subprocess.CalledProcessError(pipeline_return, cmd)

            console.print(
                "\n[bold green]✅ Pipeline execution completed successfully![/bold green]"
            )

            if generate_report:
                reports_dir = Path("data/output/reports")
                reports_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_path = reports_dir / f"snakemake_report_{timestamp}.html"

                report_cmd = [
                    micromamba_exe,
                    "run",
                    "-p",
                    env_base_path,
                    "snakemake",
                    "--cores",
                    str(cores_setting),
                    "--report",
                    str(report_path),
                ]

                console.print(
                    f"[cyan]Generating Snakemake report to: {report_path}[/cyan]"
                )
                subprocess.run(report_cmd, env=current_env, check=True)
                console.print(
                    f"[bold green]✓ Snakemake report generated: {report_path}[/bold green]"
                )
        except KeyboardInterrupt:
            console.print("\n[bold yellow]⛔ Ctrl+C detected. Terminating entire pipeline process tree...[/bold yellow]")
            if pipeline_proc is not None and pipeline_proc.poll() is None:
                terminate_process_tree(pipeline_proc.pid)
            console.print("[bold yellow]Pipeline was interrupted and all child processes were terminated.[/bold yellow]")
            sys.exit(130)
        except subprocess.CalledProcessError as e:
            console.print(
                f"\n[bold red]❌ Pipeline execution failed with return code {e.returncode}.[/bold red]"
            )


if __name__ == "__main__":
    main()
