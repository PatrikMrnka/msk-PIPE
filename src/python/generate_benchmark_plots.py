import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from matplotlib.backends.backend_pdf import PdfPages

# List of known base rules for correct grouping
BASE_RULES = [
    "clean_bone_mask", "clean_muscle_mask", "clean_muscle_mesh", "clean_geometry_mesh",
    "bone_mask_to_stl", "muscle_mask_to_obj",
    "convert_to_vtk_bones", "convert_to_vtk_muscles", "extract_attachments_lhdl",
    "extract_attachments", "merge_bone_meshes", "split_meshes", "total_segmentator",
    "muscle_map", "extract_muscle_masks", "run_muscle_wrapping", "msk_staple",
    "prepare_muscle_wrapping", "statistics_compare", "subtract_bone_from_raw_muscle_segmentation",
    "prepare_experiments_dir", "prepare_input_nifti", "prepare_input_raw", "prepare_input_dicom"
]

def get_base_rule(task_name):
    """Remove wildcard suffixes and return a clean base rule name."""
    for rule in sorted(BASE_RULES, key=len, reverse=True):
        if task_name.startswith(rule):
            return rule
    return task_name

def parse_args():
    parser = argparse.ArgumentParser(description="Generate plots from Snakemake benchmark files.")
    parser.add_argument("--bench-dir", required=True, help="Directory with .txt benchmark files (OUT_DIR/benchmarks)")
    parser.add_argument("--output", required=True, help="Target PDF file for the report")
    return parser.parse_args()

def main():
    args = parse_args()
    bench_dir = Path(args.bench_dir)
    out_pdf_path = Path(args.output)

    if not bench_dir.exists():
        print(f"Directory {bench_dir} does not exist. No benchmarks to analyze.")
        return

    # 1. Load all benchmark data
    records = []
    for txt_file in bench_dir.glob("*.txt"):
        try:
            df = pd.read_csv(txt_file, sep="\t")
            if not df.empty:
                row = df.iloc[0]
                records.append({
                    "Task": txt_file.stem,
                    "Time_s": row.get("s", 0),
                    "Max_RSS_MB": row.get("max_rss", 0),
                    "Mean_Load": row.get("mean_load", 0),
                    "IO_Out_MB": row.get("io_out", 0)
                })
        except Exception as e:
            print(f"Cannot load {txt_file}: {e}")

    if not records:
        print("No valid benchmark data found.")
        return

    df_bench = pd.DataFrame(records)
    
    # Clean NA values
    df_bench["Time_s"] = pd.to_numeric(df_bench["Time_s"], errors='coerce').fillna(0)
    df_bench["Max_RSS_MB"] = pd.to_numeric(df_bench["Max_RSS_MB"], errors='coerce').fillna(0)
    df_bench["Mean_Load"] = pd.to_numeric(df_bench["Mean_Load"], errors='coerce').fillna(0)
    df_bench["IO_Out_MB"] = pd.to_numeric(df_bench["IO_Out_MB"], errors='coerce').fillna(0)

    # Assign base rule
    df_bench["Base_Rule"] = df_bench["Task"].apply(get_base_rule)
    
    # Aggregate data for main plots
    grouped = df_bench.groupby("Base_Rule").agg(
        Count=("Task", "count"),
        Time_s_mean=("Time_s", "mean"),
        Max_RSS_MB_max=("Max_RSS_MB", "max"),
        Mean_Load_mean=("Mean_Load", "mean"),
        IO_Out_MB_sum=("IO_Out_MB", "sum")
    ).reset_index()

    grouped["Display_Task"] = grouped.apply(
        lambda x: f"{x['Base_Rule']} (n={x['Count']})" if x['Count'] > 1 else x['Base_Rule'], 
        axis=1
    )

    # Compute global maxima only from rules that appear in detail plots.
    # Rules with more than one task are shown in detail plots.
    detail_rules = grouped[grouped["Count"] > 1]["Base_Rule"].tolist()
    
    # Filter only detail-eligible tasks to derive axes maxima.
    df_detail = df_bench[df_bench["Base_Rule"].isin(detail_rules)]
    
    if not df_detail.empty:
        detail_max_time = df_detail["Time_s"].max() * 1.05
        detail_max_ram = df_detail["Max_RSS_MB"].max() * 1.05
        detail_max_load = df_detail["Mean_Load"].max() * 1.05
        detail_max_io = df_detail["IO_Out_MB"].max() * 1.05
    else:
        # Fallback in case no detail plots are generated.
        detail_max_time = detail_max_ram = detail_max_load = detail_max_io = 1

    # 2. Render plots into PDF
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_pdf_path) as pdf:
        sns.set_theme(style="whitegrid")
        
        # Helper for the 4 summary charts to avoid duplicated code.
        def plot_summary(data_df, title_prefix):
            if data_df.empty: return
            fig_height = max(6, len(data_df) * 0.4)

            # Time
            df_time = data_df.sort_values(by="Time_s_mean", ascending=False)
            fig, ax = plt.subplots(figsize=(10, fig_height))
            sns.barplot(data=df_time, x="Time_s_mean", y="Display_Task", color="skyblue", ax=ax)
            ax.set_title(f"{title_prefix}: Average runtime (s)")
            ax.set_xlabel("Seconds")
            ax.set_ylabel("")
            plt.tight_layout(); pdf.savefig(fig); plt.close()

            # RAM
            df_ram = data_df.sort_values(by="Max_RSS_MB_max", ascending=False)
            fig, ax = plt.subplots(figsize=(10, fig_height))
            sns.barplot(data=df_ram, x="Max_RSS_MB_max", y="Display_Task", color="salmon", ax=ax)
            ax.set_title(f"{title_prefix}: Maximum RAM usage (MB)")
            ax.set_xlabel("MB")
            ax.set_ylabel("")
            plt.tight_layout(); pdf.savefig(fig); plt.close()

            # CPU
            df_load = data_df.sort_values(by="Mean_Load_mean", ascending=False)
            fig, ax = plt.subplots(figsize=(10, fig_height))
            sns.barplot(data=df_load, x="Mean_Load_mean", y="Display_Task", color="mediumseagreen", ax=ax)
            ax.set_title(f"{title_prefix}: Average CPU utilization")
            ax.set_xlabel("Mean Load (~100 = 1 core)")
            ax.set_ylabel("")
            plt.tight_layout(); pdf.savefig(fig); plt.close()

            # Disk
            df_io = data_df.sort_values(by="IO_Out_MB_sum", ascending=False)
            fig, ax = plt.subplots(figsize=(10, fig_height))
            sns.barplot(data=df_io, x="IO_Out_MB_sum", y="Display_Task", color="orange", ax=ax)
            ax.set_title(f"{title_prefix}: Total file size (written MB)")
            ax.set_xlabel("MB")
            ax.set_ylabel("")
            plt.tight_layout(); pdf.savefig(fig); plt.close()

        # ==========================================
        # PART 1A: OVERALL AGGREGATED PLOTS (ALL TASKS)
        # ==========================================
        plot_summary(grouped, "SUMMARY (All tasks)")

        # ==========================================
        # PART 1B: SUMMARY WITHOUT EXTREME TASKS (DETAIL VIEW)
        # ==========================================
        # Define tasks to exclude from the filtered detail summary.
        heavy_tasks = ["total_segmentator", "muscle_map"]
        grouped_filtered = grouped[~grouped["Base_Rule"].isin(heavy_tasks)]
        
        plot_summary(grouped_filtered, "SUMMARY (Without ML segmentations)")

        # ==========================================
        # PART 2: DETAILED PLOTS FOR INDIVIDUAL RULES
        # ==========================================
        for base_rule in sorted(df_bench["Base_Rule"].unique()):
            df_subset = df_bench[df_bench["Base_Rule"] == base_rule].copy()
            
            if len(df_subset) <= 1:
                continue

            df_subset = df_subset.sort_values(by="Time_s", ascending=False)
            
            fig_height_det = max(6, len(df_subset) * 0.3)
            fig, axes = plt.subplots(1, 4, figsize=(24, fig_height_det), sharey=True)
            fig.suptitle(f"DETAIL: {base_rule}", fontsize=18, y=1.02)

            # Detail - Time
            sns.barplot(data=df_subset, x="Time_s", y="Task", color="skyblue", ax=axes[0])
            axes[0].set_title("Runtime (s)")
            axes[0].set_xlabel("Seconds")
            axes[0].set_ylabel("Specific task (muscle/bone)")
            axes[0].set_xlim(0, detail_max_time) # Use max derived only from detail data.

            # Detail - RAM
            sns.barplot(data=df_subset, x="Max_RSS_MB", y="Task", color="salmon", ax=axes[1])
            axes[1].set_title("RAM usage (MB)")
            axes[1].set_xlabel("MB")
            axes[1].set_ylabel("")
            axes[1].set_xlim(0, detail_max_ram) # Use max derived only from detail data.

            # Detail - CPU
            sns.barplot(data=df_subset, x="Mean_Load", y="Task", color="mediumseagreen", ax=axes[2])
            axes[2].set_title("CPU utilization")
            axes[2].set_xlabel("Mean Load")
            axes[2].set_ylabel("")
            axes[2].set_xlim(0, detail_max_load) # Use max derived only from detail data.

            # Detail - Disk write
            sns.barplot(data=df_subset, x="IO_Out_MB", y="Task", color="orange", ax=axes[3])
            axes[3].set_title("Generated file size")
            axes[3].set_xlabel("Write (MB)")
            axes[3].set_ylabel("")
            axes[3].set_xlim(0, detail_max_io) # Use max derived only from detail data.

            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close()

    print(f"Comprehensive benchmark plots were saved to {out_pdf_path}")

if __name__ == "__main__":
    main()