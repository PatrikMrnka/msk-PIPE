# preprocessing.smk -- Per-file mask cleaning rules.
#
# Step 4: Clean bone and muscle segmentation masks.
#
# Each mask is processed individually so that Snakemake can:
#   - track fine-grained dependencies (one output per input file),
#   - parallelise cleaning across cores automatically,
#   - resume from the exact file that failed (no full-directory reruns).


# ---------------------------------------------------------------------------
# Step 4a: Clean individual bone masks
# ---------------------------------------------------------------------------

rule clean_bone_mask:
    input:
        mask=os.path.join(OUT_DIR, "bone_segmentations", "raw", "{bone}.nii.gz"),
    output:
        mask=os.path.join(OUT_DIR, "bone_segmentations", "cleaned", "{bone}.nii.gz"),
    params:
        py_exe=lambda w: get_py_exe(totalseg_env_name()),
        keep_l=(
            "--keep-largest"
            if config.get("bone_preprocessing", {}).get("keep_largest", True)
            else "--no-keep-largest"
        ),
        holes=(
            "--fill-holes"
            if config.get("bone_preprocessing", {}).get("fill_holes", True)
            else ""
        ),
        min_v=config.get("bone_preprocessing", {}).get("min_voxels", 2000),
        open_k=config.get("bone_preprocessing", {}).get("opening_kernel", 1),
        clos_k=config.get("bone_preprocessing", {}).get("closing_kernel", 1),
    shell:
        """
        "{params.py_exe}" src/python/clean_masks.py \
            --input-file {input.mask} \
            --output-file {output.mask} \
            --min-voxels {params.min_v} \
            --opening {params.open_k} \
            --closing {params.clos_k} \
            {params.keep_l} \
            {params.holes}
        """


# Aggregate rule: ensures all bone masks are cleaned before downstream use.
rule all_cleaned_bone_masks:
    input:
        expand(
            os.path.join(OUT_DIR, "bone_segmentations", "cleaned", "{bone}.nii.gz"),
            bone=BONE_MASKS,
        ),
    output:
        touch(os.path.join(OUT_DIR, "bone_segmentations", "cleaned", ".done")),


# ---------------------------------------------------------------------------
# Step 4b: Clean individual muscle masks
# ---------------------------------------------------------------------------

rule clean_muscle_mask:
    input:
        mask=os.path.join(OUT_DIR, "muscle_segmentations", "extracted", "{muscle}.nii.gz"),
    output:
        mask=os.path.join(OUT_DIR, "muscle_segmentations", "cleaned", "{muscle}.nii.gz"),
    params:
        py_exe=lambda w: get_py_exe(totalseg_env_name()),
        min_v=config.get("muscle_preprocessing", {}).get("min_voxels", 100),
        open_k=config.get("muscle_preprocessing", {}).get("opening_kernel", 3),
        clos_k=config.get("muscle_preprocessing", {}).get("closing_kernel", 3),
        holes=(
            "--fill-holes"
            if config.get("muscle_preprocessing", {}).get("fill_holes", True)
            else ""
        ),
        keep_l=(
            "--keep-largest"
            if config.get("muscle_preprocessing", {}).get("keep_largest", True)
            else "--no-keep-largest"
        ),
    shell:
        """
        "{params.py_exe}" src/python/clean_masks.py \
            --input-file {input.mask} \
            --output-file {output.mask} \
            --iso 0.5 \
            --min-voxels {params.min_v} \
            --opening {params.open_k} \
            --closing {params.clos_k} \
            {params.holes} \
            {params.keep_l}
        """


# Aggregate rule: ensures all muscle masks are cleaned before downstream use.
rule all_cleaned_muscle_masks:
    input:
        expand(
            os.path.join(OUT_DIR, "muscle_segmentations", "cleaned", "{muscle}.nii.gz"),
            muscle=MUSCLE_LABELS,
        ),
    output:
        touch(os.path.join(OUT_DIR, "muscle_segmentations", "cleaned", ".done")),
