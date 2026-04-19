# common.smk -- Shared constants, helpers, and configuration for the pipeline.
#
# Every other .smk file that is included by the top-level Snakefile has access
# to the symbols defined here because Snakemake `include` shares the namespace.

import os
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

IN_DIR = config.get("paths", {}).get("input_dir", "data/input")
BASE_OUT_DIR = config.get("paths", {}).get("output_dir", "data/output")
MW_PATH_DIR = config.get("paths", {}).get("muscle_wrapping_path", "src/MW2/Build")
STAPLE_PATH_DIR = config.get("paths", {}).get("staple_path", "src/STAPLE")

# RUN_ID is computed by runner/pipeline.py *before* Snakemake is invoked and
# passed via `--config run_id=run_N`.  This avoids side-effects (directory
# creation, sequence number detection) during the parse phase, which would
# break --dry-run and cause inconsistencies after partial failures.
RUN_ID = config.get("run_id", "run_1")
OUT_DIR = os.path.join(BASE_OUT_DIR, RUN_ID)
BONE_STAPLE_DIR = os.path.join(OUT_DIR, "bones_STAPLE")

# ---------------------------------------------------------------------------
# Known output labels
# ---------------------------------------------------------------------------

# Bone masks expected from TotalSegmentator (after internal renaming).
BONE_MASKS = [
    "hip_left",
    "hip_right",
    "sacrum",
    "femur_left",
    "femur_right",
    "tibia",
    "fibula",
]

MUSCLE_MASKS_TOTALSEGMENTATOR = [
    "gluteus_maximus_left",
    "gluteus_maximus_right",
    "gluteus_medius_left",
    "gluteus_medius_right",
    "gluteus_minimus_left",
    "gluteus_minimus_right",
    "iliopsoas_left",
    "iliopsoas_right",
]


# Muscle topology and labels from config/muscle_topology.json.
with open("config/muscle_topology.json", encoding="utf-8") as f:
    TOPOLOGY = json.load(f)

_seg_engine = config.get("user_settings", {}).get("muscle_segmentator", "musclemap")
if _seg_engine == "totalsegmentator":
    MUSCLE_LABELS = [
        "gluteus_maximus_l", "gluteus_maximus_r",
        "gluteus_medius_l", "gluteus_medius_r",
        "gluteus_minimus_l", "gluteus_minimus_r",
        "iliacus_l", "iliacus_r"
    ]
else:
    MUSCLE_LABELS = list(config.get("muscle_map", {}).get("labels", {}).keys())

# ---------------------------------------------------------------------------
# STAPLE name mapping
# ---------------------------------------------------------------------------

# Key: substring that must appear in the filename (lowercase).
# Value: STAPLE base name (side suffix _l/_r is appended automatically).
STAPLE_NAME_MAP = {
    "pelvis": "pelvis_no_sacrum",
    "femur": "femur",
    "tibia": "tibia",
    "fibula": "fibula",
    "talus": "talus",
    "calcaneus": "calcn",
    "calcn": "calcn",
    "toes": "toes",
    "metatarsals": "toes",
}
STAPLE_SIDELESS = {"pelvis_no_sacrum"}


# ---------------------------------------------------------------------------
# Helper: resolve the Python executable inside a conda environment
# ---------------------------------------------------------------------------


def get_py_exe(env_name):
    """Return the path to the Python binary inside a named conda env."""
    exe = (
        f"envs/{env_name}/python.exe"
        if os.name == "nt"
        else f"envs/{env_name}/bin/python"
    )
    return os.path.normpath(exe)


def totalseg_env_name():
    """Derive the conda env name from the totalseg YAML filename in config."""
    return (
        config["snakemake_env"]["totalseg"].replace("env_", "msk_").replace(".yaml", "")
    )


def musclemap_env_name():
    """Derive the conda env name from the musclemap YAML filename in config."""
    return (
        config["snakemake_env"]["musclemap"]
        .replace("env_", "msk_")
        .replace(".yaml", "")
    )


def mask_to_mesh_bin():
    """Return the platform-appropriate path to the mask_to_mesh binary."""
    if os.name == "nt":
        return "src/cpp/mask_to_mesh/build/Release/mask_to_mesh.exe"
    return "src/cpp/mask_to_mesh/build/mask_to_mesh"


def extract_attachments_bin():
    """Return the platform-appropriate path to the extract_attachments binary."""
    if os.name == "nt":
        return "src/cpp/extract_attachments/build/Release/extract_attachments.exe"
    return "src/cpp/extract_attachments/build/extract_attachments"

# ---------- Benchmark PSS fix for Windows ----------
import platform
if platform.system() == "Windows":
    try:
        import snakemake.benchmark as _bm
        _original_update = _bm.BenchmarkTimer._update_record

        def _patched_update(self):
            import psutil, time
            from itertools import chain

            rss, vms, uss, pss = 0, 0, 0, 0
            io_in, io_out = 0, 0
            check_io = True
            cpu_usage = 0
            cpu_time = 0
            data_collected = False

            try:
                this_time = time.time()
                for proc in chain((self.main,), self.main.children(recursive=True)):
                    proc = self.procs.setdefault(proc.pid, proc)
                    with proc.oneshot():
                        if self.bench_record.prev_time:
                            cpu_usage += proc.cpu_percent() * (
                                this_time - self.bench_record.prev_time
                            )
                        try:
                            meminfo = proc.memory_full_info()
                        except psutil.Error:
                            self.bench_record.skipped_procs.add((proc.pid, proc.name()))
                            continue
                        rss += meminfo.rss
                        vms += meminfo.vms
                        uss += meminfo.uss
                        pss += getattr(meminfo, "pss", 0)  # <-- FIX
                        if check_io:
                            try:
                                ioinfo = proc.io_counters()
                                io_in += ioinfo.read_bytes
                                io_out += ioinfo.write_bytes
                            except NotImplementedError:
                                check_io = False
                        cpu_times = proc.cpu_times()
                        self.bench_record.processed_procs[(proc.pid, proc.name())] = (
                            cpu_times.user + cpu_times.system
                        )
                cpu_time = sum(self.bench_record.processed_procs.values())
                self.bench_record.prev_time = this_time
                if not self.bench_record.first_time:
                    self.bench_record.prev_time = this_time
                rss /= 1024 * 1024
                vms /= 1024 * 1024
                uss /= 1024 * 1024
                pss /= 1024 * 1024
                if check_io:
                    io_in /= 1024 * 1024
                    io_out /= 1024 * 1024
                else:
                    io_in = None
                    io_out = None
                data_collected = True
            except (OSError, psutil.Error) as e:
                self.bench_record.errors.append(str(e))
                return

            if data_collected:
                self.bench_record.data_collected = True
                self.bench_record.max_rss = max(self.bench_record.max_rss or 0, rss)
                self.bench_record.max_vms = max(self.bench_record.max_vms or 0, vms)
                self.bench_record.max_uss = max(self.bench_record.max_uss or 0, uss)
                self.bench_record.max_pss = max(self.bench_record.max_pss or 0, pss)
                self.bench_record.io_in = io_in
                self.bench_record.io_out = io_out
                self.bench_record.cpu_usage += cpu_usage
                self.bench_record.cpu_time = cpu_time

        _bm.BenchmarkTimer._update_record = _patched_update
    except Exception:
        pass