"""
pipeline.py – Launch the Snakemake pipeline and (optionally) generate a report.

Responsibilities:
  - Ask the user once for missing settings (auto_run, cores, report flag).
  - Persist any newly collected settings before launching (so a Ctrl-C
    restart does not ask again).
  - Run Snakemake inside the msk_base micromamba environment.
  - Handle Ctrl-C by terminating the entire process tree cleanly.
  - Generate a timestamped HTML report if the user opted in.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.prompt import Confirm, Prompt

from . import constants as C
from .config_io import save_config
from .system import terminate_process_tree
from .ui import console, print_error, print_info, print_interrupt, print_launch, print_success


# ── Snakemake command builder ─────────────────────────────────────────────────

def _base_cmd(cores: str) -> list[str]:
    env_base = str(Path("envs/msk_base").resolve())
    return [
        str(C.MICROMAMBA_EXE), "run", "-p", env_base,
        "snakemake", "--cores", str(cores),
    ]


def _snakemake_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CONDA_EXE"] = str(C.MICROMAMBA_EXE)
    return env


# ── Settings collection ───────────────────────────────────────────────────────

def _collect_run_settings(user_settings: dict) -> tuple[bool, str, bool]:
    """
    Return (auto_run, cores, generate_report), prompting only for values
    that are not already saved.
    """
    auto_run = user_settings.get("auto_run_pipeline")
    if auto_run is None:
        raw = Prompt.ask("Start the Snakemake pipeline now? (y/n)", default="y")
        auto_run = raw.strip().lower() in ("y", "yes", "true", "1")
        user_settings["auto_run_pipeline"] = auto_run

    cores: str = user_settings.get("snakemake_cores", "")
    if not cores:
        cores = Prompt.ask(
            "How many CPU cores should Snakemake use? (e.g. 1, 4, or 'all')",
            default="1",
        )
        user_settings["snakemake_cores"] = cores

    generate_report = user_settings.get("generate_snakemake_report")
    if generate_report is None:
        generate_report = Confirm.ask(
            "Generate a Snakemake HTML report after the run?", default=True
        )
        user_settings["generate_snakemake_report"] = bool(generate_report)

    return bool(auto_run), str(cores), bool(generate_report)


# ── Report generation ─────────────────────────────────────────────────────────

def _generate_report(cores: str, snakemake_env: dict[str, str]) -> None:
    C.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = C.REPORTS_DIR / f"snakemake_report_{timestamp}.html"

    print_info(f"Generating Snakemake report → {report_path}")
    subprocess.run(
        [*_base_cmd(cores), "--report", str(report_path)],
        env=snakemake_env, check=True,
    )
    print_success(f"Snakemake report saved: {report_path}")


# ── Public entry point ────────────────────────────────────────────────────────

def run_pipeline(user_settings: dict, config: dict) -> None:  # noqa: ARG001
    """
    Prompt for missing pipeline settings, persist them, then run Snakemake.
    Handles Ctrl-C by killing the entire process group before exiting.
    """
    auto_run, cores, generate_report = _collect_run_settings(user_settings)

    # Persist pipeline-related user settings into config.json immediately.
    config["user_settings"] = user_settings
    save_config(config, C.MAIN_CONFIG_PATH)


    if not auto_run:
        print_info("Pipeline launch skipped.")
        return

    print_launch(f"Launching Snakemake (cores: {cores})...")

    snakemake_env = _snakemake_env()
    cmd           = _base_cmd(cores)

    popen_kwargs: dict = {}
    if __import__("platform").system() == "Windows":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = __import__("os").setsid

    pipeline_proc: subprocess.Popen | None = None

    try:
        pipeline_proc  = subprocess.Popen(cmd, env=snakemake_env, **popen_kwargs)
        return_code    = pipeline_proc.wait()

        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd)

        print_success("Pipeline execution completed successfully!")

        if generate_report:
            _generate_report(cores, snakemake_env)

    except KeyboardInterrupt:
        print_interrupt("Ctrl-C detected. Terminating pipeline...")
        if pipeline_proc is not None and pipeline_proc.poll() is None:
            terminate_process_tree(pipeline_proc.pid)
        print_interrupt("Pipeline interrupted – all child processes terminated.")
        sys.exit(130)

    except subprocess.CalledProcessError as exc:
        print_error(f"Pipeline failed with return code {exc.returncode}.")
        sys.exit(exc.returncode)