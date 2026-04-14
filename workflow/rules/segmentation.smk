# segmentation.smk -- Bone and muscle segmentation rules.
#
# Step 1: Bone segmentation via TotalSegmentator (CT or MR model).
# Step 2: Muscle segmentation via MuscleMap.
# Step 3: Extract individual muscle masks from the multi-label output.
#
# Both segmentation tools produce entire directories of masks, so these
# rules use directory() outputs -- this is the correct abstraction for
# tools whose output set is determined internally.


# ---------------------------------------------------------------------------
# Step 1: Bone segmentation (TotalSegmentator)
# ---------------------------------------------------------------------------

rule total_segmentator:
    input:
        nii=os.path.join(OUT_DIR, "image", "ct.nii.gz"),
    output:
        seg_dir=directory(os.path.join(OUT_DIR, "bone_segmentations", "raw")),
    params:
        py_exe=lambda w: get_py_exe(totalseg_env_name()),
        device=config.get("totalsegmentator", {}).get("device", "cpu"),
        model=config.get("totalsegmentator", {}).get("model", "ct"),
        fast="--fast" if config.get("totalsegmentator", {}).get("fast", False) else "",
    shell:
        """
        "{params.py_exe}" src/python/bones_segmentation/run_totalsegmentator.py \
            {input.nii} \
            --output-dir {output.seg_dir} \
            --device {params.device} \
            --model {params.model} \
            {params.fast}
        """


# ---------------------------------------------------------------------------
# Step 2: Muscle segmentation (MuscleMap)
# ---------------------------------------------------------------------------

rule muscle_map:
    input:
        nii=os.path.join(OUT_DIR, "image", "ct.nii.gz"),
    output:
        seg_dir=directory(os.path.join(OUT_DIR, "muscle_segmentations", "raw")),
    params:
        py_exe=lambda w: get_py_exe(musclemap_env_name()),
    shell:
        """
        "{params.py_exe}" src/python/muscles_segmentation_extraction/run_musclemap.py \
            {input.nii} \
            --output-dir {output.seg_dir}
        """


# ---------------------------------------------------------------------------
# Step 3: Extract individual muscle masks from multi-label segmentation
# ---------------------------------------------------------------------------

rule extract_muscle_masks:
    input:
        seg_dir=os.path.join(OUT_DIR, "muscle_segmentations", "raw"),
    output:
        seg_dir=directory(os.path.join(OUT_DIR, "muscle_segmentations", "extracted")),
    params:
        py_exe=lambda w: get_py_exe(musclemap_env_name()),
    shell:
        """
        "{params.py_exe}" src/python/muscles_segmentation_extraction/extract_muscle_masks.py \
            {input.seg_dir}/musclemap_segmentation.nii.gz \
            --output-dir {output.seg_dir} \
            --config config/config.json
        """
