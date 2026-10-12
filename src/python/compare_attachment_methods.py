"""
compare_attachment_methods.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Compare two (or more) pipeline runs that differ only in the attachment
extraction method (e.g. atlas_based/CPD vs fast_rnrr) against the LHDL
ground truth.

Inputs are the per-run outputs the pipeline already produces:
  <run>/statistics/Celkove_Statistiky_s_Procenty.csv   (fibre lengths vs LHDL)
  <run>/attachments/*.vtk                              (mapped attachment points)

Outputs (in --output):
  fiber_length_comparison.csv   per-muscle metrics side by side + winner
  attachment_differences.csv    geometric distance between methods' attachments
  rmse_per_muscle.png           grouped bar chart of RMSE per muscle
  summary.md                    short human-readable summary

Usage
-----
    python src/python/compare_attachment_methods.py \
        --run CPD=data/output/run_1 \
        --run RNRR=data/output/run_2 \
        --output data/output/compare_cpd_vs_rnrr
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

STATS_REL = Path("statistics") / "Celkove_Statistiky_s_Procenty.csv"
METRICS = ["RMSE_mm", "Pearson_Correlation", "Relative_Error_vs_Length_%", "Relative_Error_vs_Range_%"]


def parse_runs(items: list[str]) -> dict[str, Path]:
    runs = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"--run expects LABEL=PATH, got: {it}")
        label, path = it.split("=", 1)
        runs[label.strip()] = Path(path.strip())
    if len(runs) < 2:
        raise SystemExit("Need at least two --run entries.")
    return runs


def load_vtk_points(path: Path) -> np.ndarray:
    pts, n, inside = [], 0, False
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s.startswith("POINTS"):
                n, inside = int(s.split()[1]), True
                continue
            if inside:
                vals = s.split()
                for i in range(0, len(vals) - 2, 3):
                    pts.append([float(vals[i]), float(vals[i + 1]), float(vals[i + 2])])
                if len(pts) >= n:
                    break
    return np.asarray(pts[:n])


def fiber_length_table(runs: dict[str, Path]) -> pd.DataFrame:
    merged = None
    for label, run in runs.items():
        csv = run / STATS_REL
        if not csv.exists():
            raise SystemExit(f"[{label}] missing {csv} - did the run finish incl. statistics?")
        df = pd.read_csv(csv)[["Muscle", "File", *METRICS]]
        df = df.rename(columns={m: f"{m}__{label}" for m in METRICS})
        merged = df if merged is None else merged.merge(df, on=["Muscle", "File"], how="inner")
    labels = list(runs)
    rmse_cols = [f"RMSE_mm__{l}" for l in labels]
    merged["Best_RMSE"] = merged[rmse_cols].idxmin(axis=1).str.replace("RMSE_mm__", "", regex=False)
    if len(labels) == 2:
        a, b = labels
        merged[f"Delta_RMSE_mm_({b}-{a})"] = merged[f"RMSE_mm__{b}"] - merged[f"RMSE_mm__{a}"]
    return merged.sort_values("Muscle").reset_index(drop=True)


def attachment_table(runs: dict[str, Path]) -> pd.DataFrame:
    labels = list(runs)
    ref_label, ref_run = labels[0], runs[labels[0]]
    rows = []
    for vtk in sorted((ref_run / "attachments").glob("*.vtk")):
        p_ref = load_vtk_points(vtk)
        if len(p_ref) == 0:
            continue
        for other in labels[1:]:
            o = runs[other] / "attachments" / vtk.name
            if not o.exists():
                continue
            p_o = load_vtk_points(o)
            if len(p_o) == 0:
                continue
            d1, _ = cKDTree(p_o).query(p_ref)
            d2, _ = cKDTree(p_ref).query(p_o)
            rows.append({
                "Attachment": vtk.stem,
                "Pair": f"{ref_label} vs {other}",
                "Centroid_distance_mm": float(np.linalg.norm(p_ref.mean(0) - p_o.mean(0))),
                "Chamfer_mean_mm": float((d1.mean() + d2.mean()) / 2),
                "Hausdorff_mm": float(max(d1.max(), d2.max())),
            })
    return pd.DataFrame(rows)


def plot_rmse(df: pd.DataFrame, labels: list[str], out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.arange(len(df))
    w = 0.8 / len(labels)
    fig, ax = plt.subplots(figsize=(max(6, 1.1 * len(df)), 4.5))
    for i, l in enumerate(labels):
        ax.bar(x + (i - (len(labels) - 1) / 2) * w, df[f"RMSE_mm__{l}"], w, label=l)
    ax.set_xticks(x)
    ax.set_xticklabels(df["Muscle"], rotation=35, ha="right")
    ax.set_ylabel("RMSE vs LHDL fibre length [mm] (lower = better)")
    ax.set_title("Attachment method comparison")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def summary_md(df: pd.DataFrame, att: pd.DataFrame, labels: list[str]) -> str:
    lines = ["# Attachment method comparison vs LHDL ground truth", ""]
    lines.append(f"Muscles compared: {len(df)}")
    lines.append("")
    lines.append("| Method | mean RMSE [mm] | median RMSE [mm] | mean Pearson r | mean rel. err. vs length [%] | wins |")
    lines.append("|---|---|---|---|---|---|")
    for l in labels:
        lines.append(
            f"| {l} | {df[f'RMSE_mm__{l}'].mean():.2f} | {df[f'RMSE_mm__{l}'].median():.2f} | "
            f"{df[f'Pearson_Correlation__{l}'].mean():.3f} | {df[f'Relative_Error_vs_Length_%__{l}'].mean():.2f} | "
            f"{int((df['Best_RMSE'] == l).sum())} |"
        )
    if len(labels) == 2 and len(df) >= 5:
        from scipy.stats import wilcoxon
        a, b = labels
        try:
            stat, p = wilcoxon(df[f"RMSE_mm__{a}"], df[f"RMSE_mm__{b}"])
            lines += ["", f"Wilcoxon signed-rank test on per-muscle RMSE ({a} vs {b}): W={stat:.1f}, p={p:.4f}",
                      "(p < 0.05 -> difference unlikely to be chance; with few muscles treat as indicative only)"]
        except ValueError as exc:
            lines += ["", f"Wilcoxon test not computed: {exc}"]
    if not att.empty:
        lines += ["", "## How far apart are the attachments of the two methods",
                  f"mean centroid distance: {att['Centroid_distance_mm'].mean():.2f} mm, "
                  f"max: {att['Centroid_distance_mm'].max():.2f} mm "
                  f"({att.loc[att['Centroid_distance_mm'].idxmax(), 'Attachment']})"]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", required=True, help="LABEL=path/to/run_dir (repeat)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    runs = parse_runs(args.run)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    df = fiber_length_table(runs)
    df.to_csv(out / "fiber_length_comparison.csv", index=False)
    att = attachment_table(runs)
    att.to_csv(out / "attachment_differences.csv", index=False)
    plot_rmse(df, list(runs), out / "rmse_per_muscle.png")
    md = summary_md(df, att, list(runs))
    (out / "summary.md").write_text(md, encoding="utf-8")

    print(md)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(df[["Muscle", *[f"RMSE_mm__{l}" for l in runs], "Best_RMSE"]].to_string(index=False))
    print(f"\nResults written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
