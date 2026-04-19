# statistics.smk -- Post-processing comparison of PIPELINE vs LHDL .sto outputs.
#
# Step 11: Compare matching Lengths .sto files and generate summary plots/tables.

import os


KINEMATICS_ALGORITHM = str(
    config.get("muscle_wrapping", {}).get("kinematics_algorithm", "luca")
).strip().lower()
LHDL_REFERENCE_DIR = os.path.join(
    "data",
    "Experiments",
    "LHDL-HAVLICEK" if KINEMATICS_ALGORITHM == "havlicek" else "LHDL-LUCA",
)


rule statistics_compare:
    input:
        osim=os.path.join(OUT_DIR, "pipeline_model.osim"),
        pipeline_experiments=os.path.join(OUT_DIR, "Experiments"),
    output:
        done=touch(os.path.join(OUT_DIR, "statistics", ".done")),

        pdf_report=report(
            os.path.join(OUT_DIR, "statistics", "Kinematika_Report.pdf"),
            category="Statistics",
            subcategory="Plots",
        ),
        csv_stats=report(
            os.path.join(OUT_DIR, "statistics", "Celkove_Statistiky_s_Procenty.csv"),
            category="Statistics",
            subcategory="Tables"
        )
    params:
        py_exe=get_py_exe("msk_base"),
        pipeline_dir=os.path.join(OUT_DIR, "Experiments"),
        lhdl_dir=LHDL_REFERENCE_DIR,
        output_dir=os.path.join(OUT_DIR, "statistics"),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "statistics_compare.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
    shell:
        """

        "{params.py_exe}" src/python/generate_statistics.py \
            --pipeline-dir "{params.pipeline_dir}" \
            --lhdl-dir "{params.lhdl_dir}" \
            --output "{params.output_dir}"
        """

if config.get("user_settings", {}).get("enable_benchmarking", True):

    rule generate_benchmark_report:
        input:
            # Pravidlo počká, dokud nebudou hotové alespoň statistiky (nebo koncový .osim), 
            # abychom měli jistotu, že všechny benchmark .txt soubory už existují na disku
            wait_for=os.path.join(OUT_DIR, "statistics", ".done")
        output:
            # Díky funkci report() a category="Benchmarks" se vytvoří nová záložka v HTML!
            pdf=report(
                os.path.join(OUT_DIR, "statistics", "Benchmark_Report.pdf"),
                category="Benchmarks",
            )
        params:
            py_exe=get_py_exe("msk_base"),
            bench_dir=os.path.join(OUT_DIR, "benchmarks"),
            out_pdf=lambda w, output: output.pdf
        shell:
            """
            "{params.py_exe}" src/python/generate_benchmark_plots.py \
                --bench-dir "{params.bench_dir}" \
                --output "{params.out_pdf}"
            """

rule generate_summary_report:
    output:
        txt=report(
            os.path.join(OUT_DIR, "statistics", "summary_metadata.txt"),
            category="Metadata",
        )
    params:
        py_exe=get_py_exe("msk_base"),
        snakefile="workflow/Snakefile",
        run_id=RUN_ID
    shell:
        # Snakemake zavolá sám sebe, aby vygeneroval summary aktuálního běhu
        (
            '"{params.py_exe}" -m snakemake '
            '--snakefile "{params.snakefile}" '
            '--summary '
            '--config run_id={params.run_id} '
            '> "{output.txt}"'
        )