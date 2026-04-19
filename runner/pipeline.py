"""
pipeline.py -- Launch the Snakemake pipeline and (optionally) generate a report.

Responsibilities:
  - Compute the run ID (run_1, run_2, ...) *before* Snakemake starts so that
    the Snakefile never causes side-effects during its parse phase.
  - Ask the user once for missing settings (auto_run, cores, report flag).
  - Persist any newly collected settings before launching.
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
from .ui import (
    console,
    print_error,
    print_info,
    print_interrupt,
    print_launch,
    print_success,
)


# -- Run ID computation ----------------------------------------------------

def determine_run_id(base_out_dir: str) -> str:
    """Compute the next run ID based on the contents of *base_out_dir*.

    * If no runs exist, returns ``"run_1"``.
    * If the latest run has a ``pipeline_model.osim`` (i.e. completed),
      returns the next sequential ID.
    * Otherwise returns the latest (incomplete) run so Snakemake can resume.
    """
    out = Path(base_out_dir)
    if not out.exists():
        return "run_1"

    existing: list[int] = []
    for d in out.iterdir():
        if d.is_dir() and d.name.startswith("run_"):
            try:
                existing.append(int(d.name.split("_", 1)[1]))
            except ValueError:
                continue

    if not existing:
        return "run_1"

    latest = max(existing)
    final_target = out / f"run_{latest}" / "pipeline_model.osim"

    if final_target.exists():
        return f"run_{latest + 1}"
    return f"run_{latest}"


# -- Snakemake command builder ---------------------------------------------

def _base_cmd(cores: str, latency_wait: int) -> list[str]:
    env_base = str(Path("envs/msk_base").resolve())
    return [
        str(C.MICROMAMBA_EXE), "run", "-p", env_base,
        "snakemake", "--cores", str(cores),
        "--resources", "segmentation_mutex=1",
        "--latency-wait", str(latency_wait),
    ]


def _snakemake_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CONDA_EXE"] = str(C.MICROMAMBA_EXE)
    return env


def _dot_cmd() -> list[str]:
    env_base = str(Path("envs/msk_base").resolve())
    return [str(C.MICROMAMBA_EXE), "run", "-p", env_base, "dot"]


def _dot_available(snakemake_env: dict[str, str]) -> bool:
    result = subprocess.run(
        [*_dot_cmd(), "-V"],
        env=snakemake_env,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


# -- Settings collection ---------------------------------------------------

def _collect_run_settings(user_settings: dict) -> tuple[bool, str, bool]:
    """Return (auto_run, cores, generate_report), prompting only for values
    that are not already saved."""
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
    
    latency_wait: int = user_settings.get("snakemake_latency_wait", 30)
    if not latency_wait:
        latency_wait = Prompt.ask(
            "How many seconds should Snakemake wait for files to appear? (default: 30)",
            default="30",
        )
        user_settings["snakemake_latency_wait"] = int(latency_wait)

    generate_report = user_settings.get("generate_snakemake_report")
    if generate_report is None:
        generate_report = Confirm.ask(
            "Generate a Snakemake HTML report after the run?", default=True
        )
        user_settings["generate_snakemake_report"] = bool(generate_report)

    return bool(auto_run), str(cores), int(latency_wait), bool(generate_report)


# -- Report generation -----------------------------------------------------

def _generate_analyses(cores: str, run_id: str, snakemake_env: dict[str, str], latency_wait: int, user_settings: dict) -> None:
    run_reports_dir = C.REPORTS_DIR / run_id
    run_reports_dir.mkdir(parents=True, exist_ok=True)

    base_cmd = [*_base_cmd(cores, latency_wait), "--config", f"run_id={run_id}"]

    print_info(f"Ukládám reporty a analýzy do složky -> {run_reports_dir}")

    # 1. Interaktivní HTML Report
    if user_settings.get("generate_snakemake_report", True):
        report_path = run_reports_dir / f"snakemake_report.html"
        print_info(f"Generuji HTML report -> {report_path}")
        subprocess.run([*base_cmd, "--report", str(report_path)], env=snakemake_env, check=True)

    # 2. Detailní Summary
    if user_settings.get("generate_summary", True):
        summary_path = run_reports_dir / f"summary.txt"
        print_info(f"Generuji detailní summary -> {summary_path}")
        with open(summary_path, "w") as f:
            subprocess.run([*base_cmd, "--summary"], env=snakemake_env, stdout=f)

    # 3. Vizualizace (DAG a Rulegraph) - vyžaduje Graphviz (dot)
    if user_settings.get("generate_dag", True) or user_settings.get("generate_rulegraph", True):
        if not _dot_available(snakemake_env):
            print_error("Nástroj Graphviz (příkaz 'dot') není nainstalován. Přeskakuji generování grafů.")
        else:
            if user_settings.get("generate_dag", True):
                dag_path = run_reports_dir / f"dag.pdf"
                print_info(f"Generuji DAG strom -> {dag_path}")
                p1 = subprocess.Popen([*base_cmd, "--dag"], env=snakemake_env, stdout=subprocess.PIPE)
                p2 = subprocess.Popen([*_dot_cmd(), "-Tpdf"], env=snakemake_env, stdin=p1.stdout, stdout=open(dag_path, "wb"))
                p1.stdout.close()
                p2.communicate()

            if user_settings.get("generate_rulegraph", True):
                rg_path = run_reports_dir / f"rulegraph.pdf"
                print_info(f"Generuji Rulegraph -> {rg_path}")
                p1 = subprocess.Popen([*base_cmd, "--rulegraph"], env=snakemake_env, stdout=subprocess.PIPE)
                p2 = subprocess.Popen([*_dot_cmd(), "-Tpdf"], env=snakemake_env, stdin=p1.stdout, stdout=open(rg_path, "wb"))
                p1.stdout.close()
                p2.communicate()
    


# -- Public entry point ----------------------------------------------------

def run_pipeline(user_settings: dict, config: dict) -> None:
    """Prompt for missing pipeline settings, persist them, then run Snakemake.

    RUN_ID is computed here -- *before* Snakemake starts -- so the Snakefile
    never performs side-effects (directory creation, run numbering) during its
    parse phase.  The ID is passed to Snakemake via ``--config run_id=<value>``.
    """
    auto_run, cores, latency_wait, generate_report = _collect_run_settings(user_settings)

    # Persist pipeline-related user settings into config.json immediately.
    config["user_settings"] = user_settings
    save_config(config, C.MAIN_CONFIG_PATH)

    if not auto_run:
        print_info("Pipeline launch skipped.")
        return

    # Compute run ID and create the output directory ahead of Snakemake.
    base_out_dir = config.get("paths", {}).get("output_dir", "data/output")
    run_id = determine_run_id(base_out_dir)
    out_dir = Path(base_out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print_launch(f"Launching Snakemake (cores: {cores}, run: {run_id}, latency_wait: {latency_wait})...")

    snakemake_env = _snakemake_env()

    # Build the command with --config run_id=<value> so the Snakefile can
    # pick it up without computing anything itself.
    cmd = [*_base_cmd(cores, latency_wait), "--config", f"run_id={run_id}"]

    popen_kwargs: dict = {}
    if __import__("platform").system() == "Windows":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = __import__("os").setsid

    pipeline_proc: subprocess.Popen | None = None

    try:
        pipeline_proc = subprocess.Popen(cmd, env=snakemake_env, **popen_kwargs)
        return_code = pipeline_proc.wait()

        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd)

        print_success("Pipeline execution completed successfully!")

        if generate_report:
            _generate_analyses(cores, run_id, snakemake_env, latency_wait, user_settings)

    except KeyboardInterrupt:
        print_interrupt("Ctrl-C detected. Terminating pipeline...")
        if pipeline_proc is not None and pipeline_proc.poll() is None:
            terminate_process_tree(pipeline_proc.pid)
        print_interrupt("Pipeline interrupted -- all child processes terminated.")
        sys.exit(130)

    except subprocess.CalledProcessError as exc:
        print_error(f"Pipeline failed with return code {exc.returncode}.")
        sys.exit(exc.returncode)
