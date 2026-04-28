"""
generate_statistics.py
~~~~~~~~~~~~~~~~~~~~~~
Compare fiber lengths between PIPELINE and LHDL .sto files.

Generates RMSE, correlation, and relative errors against ground-truth data,
and produces a PDF report with time evolution and violin plots.

Usage
-----
    python generate_statistics.py \
        --input data/temp/results \
        --output data/temp/results/plots
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import pearsonr
from sklearn.metrics import mean_squared_error

NAME_1 = "PIPELINE"
NAME_2 = "LHDL"

# Time points used for violin plots.
VIOLIN_TIMES = [0.0, 0.25, 0.5]

# muscle order for violin plots
VIOLIN_MUSCLE_ORDER = ["Iliacus", "GluteusMaximus", "GluteusMedius", "GluteusMinimus", "AdductorBrevis", "AdductorLongus", "AdductorMagnus", "Pectineus", "VastusLateralis", "VastusMedialis"]
VIOLIN_MUSCLES_PER_FIG = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare fiber lengths between PIPELINE and LHDL .sto files.")
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to a directory containing subfolders PIPELINE and LHDL.",
    )
    parser.add_argument(
        "--pipeline-dir",
        type=str,
        default=None,
        help="Path to PIPELINE .sto directory (alternative to --input).",
    )
    parser.add_argument(
        "--lhdl-dir",
        type=str,
        default=None,
        help="Path to LHDL .sto directory (alternative to --input).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for generated plots/statistics.",
    )
    return parser.parse_args()


def resolve_dirs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if args.input:
        root = Path(args.input)
        pipeline_dir = root / "PIPELINE"
        lhdl_dir = root / "LHDL"
        default_output = root / f"output_{root.name}"
    else:
        if not args.pipeline_dir or not args.lhdl_dir:
            raise ValueError("Use either --input, or the combination of --pipeline-dir and --lhdl-dir.")
        pipeline_dir = Path(args.pipeline_dir)
        lhdl_dir = Path(args.lhdl_dir)
        default_output = pipeline_dir.parent / f"output_{pipeline_dir.name}"

    output_dir = Path(args.output) if args.output else default_output
    return pipeline_dir, lhdl_dir, output_dir


def list_lengths_sto_files(directory: Path) -> set[str]:
    return {
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() == ".sto" and "lengths" in p.name.lower()
    }

def load_sto(filepath: Path) -> pd.DataFrame:
    """Load a .sto file without depending on a fixed header length."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    skip_lines = 0
    for i, line in enumerate(lines):
        if "endheader" in line.lower():
            skip_lines = i + 1
            break

    df = pd.read_csv(filepath, sep="\t", skiprows=skip_lines)
    df.columns = df.columns.str.strip()
    return df


def _find_fiber_columns(df: pd.DataFrame, muscle_name: str) -> list[str]:
    prefixes = (muscle_name, muscle_name.lower(), muscle_name.upper())
    cols = [c for c in df.columns if any(c.startswith(pref) for pref in prefixes)]
    if cols:
        return cols
    return [c for c in df.columns if c.lower().startswith(muscle_name.lower())]


def calculate_statistics(df1: pd.DataFrame, df2: pd.DataFrame, muscle_name: str) -> dict:
    """Compute RMSE, correlation, and relative errors against ground-truth (LHDL) data."""
    fibers1 = _find_fiber_columns(df1, muscle_name)
    fibers2 = _find_fiber_columns(df2, muscle_name)
    if not fibers1 or not fibers2:
        raise ValueError(f"No fibers found for muscle '{muscle_name}'.")

    mean1 = df1[fibers1].mean(axis=1)
    mean2 = df2[fibers2].mean(axis=1)

    min_len = min(len(mean1), len(mean2))
    if min_len < 2:
        raise ValueError(f"Not enough data to compute statistics for muscle '{muscle_name}'.")
    m1, m2 = mean1.iloc[:min_len], mean2.iloc[:min_len]

    rmse = float(np.sqrt(mean_squared_error(m1, m2)))
    corr, _ = pearsonr(m1, m2)
    
    # Ground-truth (LHDL) statistics from df2
    gt_values = df2[fibers2].values
    gt_mean = float(gt_values.mean())
    gt_min = float(gt_values.min())
    gt_max = float(gt_values.max())
    gt_range = gt_max - gt_min
    
    # Compute relative errors (in %)
    rel_rmse_mean_pct = (rmse / gt_mean) * 100 if gt_mean != 0 else 0.0
    rel_rmse_range_pct = (rmse / gt_range) * 100 if gt_range != 0 else 0.0

    return {
        "rmse": rmse,
        "corr": float(corr),
        "gt_mean": gt_mean,
        "gt_range": gt_range,
        "rel_rmse_mean_pct": rel_rmse_mean_pct,
        "rel_rmse_range_pct": rel_rmse_range_pct
    }


def muscle_name_from_file(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("_Lengths", "").replace("Lengths", "").strip("_- ") or stem


def run_statistics(pipeline_dir: Path, lhdl_dir: Path, output_dir: Path) -> int:
    if not pipeline_dir.exists():
        print(f"Error: PIPELINE directory does not exist: {pipeline_dir}")
        return 1
    if not lhdl_dir.exists():
        print(f"Error: LHDL directory does not exist: {lhdl_dir}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    files_1 = list_lengths_sto_files(pipeline_dir)
    files_2 = list_lengths_sto_files(lhdl_dir)

    common_files = files_1.intersection(files_2)
    order_map = {f"{name}_Lengths.sto": i for i, name in enumerate(VIOLIN_MUSCLE_ORDER)}
    common_files = sorted(common_files, key=lambda f: (order_map.get(f, len(VIOLIN_MUSCLE_ORDER)), f.lower()))

    print(f"Found common Lengths .sto files: {len(common_files)}")
    if not common_files:
        print("No files found for comparison (same filename + contains 'Lengths').")
        return 0

    all_data: list[pd.DataFrame] = []
    stats_records: list[dict[str, object]] = []

    pdf_path = output_dir / "Kinematika_Report.pdf"
    with PdfPages(pdf_path) as pdf:

        for file in common_files:
            muscle_name = muscle_name_from_file(file)
            print(f"Processing: {muscle_name}")

            path_1 = pipeline_dir / file
            path_2 = lhdl_dir / file

            try:
                df1 = load_sto(path_1)
                df2 = load_sto(path_2)
            except Exception as exc:
                print(f"Skipping {file}: unable to load data ({exc})")
                continue

            try:
                stats = calculate_statistics(df1, df2, muscle_name)
                rmse = stats["rmse"]
                corr = stats["corr"]
                gt_mean = stats["gt_mean"]
                gt_range = stats["gt_range"]
                rel_rmse_mean_pct = stats["rel_rmse_mean_pct"]
                rel_rmse_range_pct = stats["rel_rmse_range_pct"]
            except Exception as exc:
                print(f"Skipping {file}: unable to compute statistics ({exc})")
                continue

            stats_records.append({
                "Muscle": muscle_name,
                "File": file,
                "RMSE_mm": rmse * 1000, 
                "Pearson_Correlation": corr,
                "LHDL_Mean_Length_mm": gt_mean * 1000,
                "LHDL_Range_of_Motion_mm": gt_range * 1000,
                "Relative_Error_vs_Length_%": rel_rmse_mean_pct,
                "Relative_Error_vs_Range_%": rel_rmse_range_pct
            })

            muscle_dfs = []
            for df, cond_name in ((df1, NAME_1), (df2, NAME_2)):
                fibers = _find_fiber_columns(df, muscle_name)
                if not fibers or "time" not in df.columns:
                    continue
                melted = df.melt(id_vars=["time"], value_vars=fibers, var_name="fiber", value_name="length")
                melted["muscle"] = muscle_name
                melted["condition"] = cond_name
                all_data.append(melted)
                muscle_dfs.append(melted)

            muscle_full_df = pd.concat(muscle_dfs, ignore_index=True) if muscle_dfs else pd.DataFrame()
            if not muscle_full_df.empty:
                muscle_full_df["time"] = muscle_full_df["time"].round(3)

            num_times = len(VIOLIN_TIMES)
            
            # Create a figure with GridSpec:
            # Top (row 0): one large plot across all columns for the time plot.
            # Bottom (row 1): num_times smaller plots for violin charts.
            fig = plt.figure(figsize=(12, 10))
            gs = fig.add_gridspec(2, num_times, height_ratios=[1.2, 1])

            ax_time = fig.add_subplot(gs[0, :])

            # PLOT 1: Time evolution (Mean +- STD) for the current muscle.
            for d, color, name in ((df1, "#1f77b4", NAME_1), (df2, "#ff7f0e", NAME_2)):
                fibs = _find_fiber_columns(d, muscle_name)
                if not fibs or "time" not in d.columns:
                    continue
                m = d[fibs].mean(axis=1)
                s = d[fibs].std(axis=1)
                t = d["time"]
                ax_time.plot(t, m, label=f"{name} (Mean)", color=color, linewidth=2)
                ax_time.fill_between(t, m - s, m + s, color=color, alpha=0.2)

            ax_time.set_title(
                f"Sval: {muscle_name}\n"
                f"RMSE: {rmse * 1000:.2f} mm | Korelace: {corr:.3f}\n"
                f"Chyba k průměrné délce: {rel_rmse_mean_pct:.2f} % | Chyba k rozsahu pohybu: {rel_rmse_range_pct:.2f} %"
            )
            ax_time.set_xlabel("Čas (s)")
            ax_time.set_ylabel("Délka vláken (m)")
            ax_time.grid(True, linestyle="--", alpha=0.6)
            ax_time.legend(loc="upper left")

            # PLOT 2: Violin plots for the current muscle at selected time points.
            if not muscle_full_df.empty:
                violin_data = muscle_full_df[muscle_full_df["time"].isin(VIOLIN_TIMES)]
                if not violin_data.empty:
                    axes_violin = []
                    for i, time_val in enumerate(VIOLIN_TIMES):
                        ax_v = fig.add_subplot(gs[1, i], sharey=axes_violin[0] if axes_violin else None)
                        axes_violin.append(ax_v)
                        
                        subset = violin_data[violin_data["time"] == time_val]
                        if subset.empty:
                            ax_v.set_title(f"Time: {time_val} s (no data)")
                            continue

                        sns.violinplot(
                            data=subset,
                            x="muscle",
                            y="length",
                            hue="condition",
                            split=True,
                            inner="quart",
                            palette={NAME_1: "#1f77b4", NAME_2: "#ff7f0e"},
                            ax=ax_v,
                        )
                        ax_v.set_title(f"Čas: {time_val} s")
                        ax_v.set_xlabel("")
                        ax_v.set_xticks([]) # Hide the repeated muscle label.
                        if i == 0:
                            ax_v.set_ylabel("Délka vláken (m)")
                        else:
                            ax_v.set_ylabel("")

                        if ax_v.get_legend() is not None:
                            ax_v.get_legend().remove()

                    if axes_violin and len(axes_violin) > 0 and axes_violin[-1].collections:
                        handles, labels = axes_violin[-1].get_legend_handles_labels()
                        if handles:
                            axes_violin[-1].legend(handles, labels, loc='upper left', bbox_to_anchor=(1.05, 1))

            plt.tight_layout()
            plt.savefig(output_dir / f"{muscle_name}_Combined_Plot.png", dpi=300, bbox_inches="tight")
            pdf.savefig(fig)
            plt.close()

        if not stats_records:
            print("No statistics were generated. All files were skipped.")
            return 1

        stats_df = pd.DataFrame(stats_records)
        # Save with the current output filename.
        stats_df.to_csv(output_dir / "Celkove_Statistiky_s_Procenty.csv", index=False)

        # PLOT 2: Violin plots by muscle groups (max. 2 muscles per figure).
        if all_data:
            print("Generating violin plots...")
            full_df = pd.concat(all_data, ignore_index=True)
            full_df["time"] = full_df["time"].round(3)

            # Determine which muscles are available in the data.
            available_muscles = set(full_df["muscle"].unique())
            
            # Keep the preferred order but remove muscles that are missing.
            filtered_muscle_order = [m for m in VIOLIN_MUSCLE_ORDER if m in available_muscles]
            
            # Append remaining muscles not listed in the preferred order.
            extra_muscles = sorted(m for m in available_muscles if m not in VIOLIN_MUSCLE_ORDER)
            
            # Final plotting order.
            plot_muscle_order = filtered_muscle_order + extra_muscles
            full_df["muscle"] = pd.Categorical(full_df["muscle"], categories=plot_muscle_order, ordered=True)

            violin_data = full_df[full_df["time"].isin(VIOLIN_TIMES)]
            if not violin_data.empty:
                num_times = len(VIOLIN_TIMES)

                muscle_groups = [
                    plot_muscle_order[i : i + VIOLIN_MUSCLES_PER_FIG]
                    for i in range(0, len(plot_muscle_order), VIOLIN_MUSCLES_PER_FIG)
                ]

                for group_idx, muscle_group in enumerate(muscle_groups, start=1):
                    group_df = violin_data[violin_data["muscle"].isin(muscle_group)]
                    if group_df.empty:
                        continue

                    fig, axes = plt.subplots(1, num_times, figsize=(8 * num_times, 8), sharey=True)
                    if num_times == 1:
                        axes = [axes]

                    for i, t in enumerate(VIOLIN_TIMES):
                        ax = axes[i]
                        subset = group_df[group_df["time"] == t]
                        if subset.empty:
                            ax.set_title(f"Time: {t} s (no data)")
                            continue

                        sns.violinplot(
                            data=subset,
                            x="muscle",
                            y="length",
                            hue="condition",
                            split=True,
                            inner="quart",
                            palette={NAME_1: "#1f77b4", NAME_2: "#ff7f0e"},
                            order=muscle_group,
                            ax=ax,
                        )
                        ax.set_title(f"Time: {t} s")
                        ax.set_xlabel("Muscle")
                        ax.set_ylabel("Fiber length (m)" if i == 0 else "")
                        ax.tick_params(axis="x", rotation=20)

                        if i != num_times - 1:
                            if ax.get_legend() is not None:
                                ax.get_legend().remove()
                        else:
                            sns.move_legend(ax, "upper left", bbox_to_anchor=(1.02, 1))

                    muscles_label = ", ".join(muscle_group)
                    plt.suptitle(
                        f"Fiber length distribution (Violin Plot) - group {group_idx}: {muscles_label}",
                        fontsize=16,
                        y=1.03,
                    )
                    plt.tight_layout()
                    plt.savefig(output_dir / f"All_Muscles_Violin_Group_{group_idx:02d}.png", bbox_inches="tight", dpi=300)
                    pdf.savefig(fig)
                    plt.close()

    print(f"Done! All plots and tables were saved to '{output_dir}'.")
    return 0


def main() -> int:
    args = parse_args()
    try:
        pipeline_dir, lhdl_dir, output_dir = resolve_dirs(args)
    except ValueError as exc:
        print(f"Argument error: {exc}")
        return 2
    return run_statistics(pipeline_dir=pipeline_dir, lhdl_dir=lhdl_dir, output_dir=output_dir)


if __name__ == "__main__":
    raise SystemExit(main())