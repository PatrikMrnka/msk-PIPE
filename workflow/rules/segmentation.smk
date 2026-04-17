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
        masks=expand(
            os.path.join(OUT_DIR, "bone_segmentations", "raw", "{bone}.nii.gz"),
            bone=BONE_MASKS,
        ),
    params:
        py_exe=lambda w: get_py_exe(totalseg_env_name()),
        device=config.get("totalsegmentator", {}).get("device", "cpu"),
        model=config.get("totalsegmentator", {}).get("model", "ct"),
        fast="--fast" if config.get("totalsegmentator", {}).get("fast", False) else "",
        out_dir=os.path.join(OUT_DIR, "bone_segmentations", "raw"),
    shell:
        """
        "{params.py_exe}" src/python/bones_segmentation/run_totalsegmentator.py \
            {input.nii} \
            --output-dir {params.out_dir} \
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
        masks_dir=directory(os.path.join(OUT_DIR, "muscle_segmentations", "raw")),
        segmentation=os.path.join(
            OUT_DIR, "muscle_segmentations", "raw", "musclemap_segmentation.nii.gz"
        ),
    params:
        py_exe=lambda w: get_py_exe(musclemap_env_name()),
    shell:
        """
        "{params.py_exe}" src/python/muscles_segmentation_extraction/run_musclemap.py \
            {input.nii} \
            --output-dir {output.masks_dir} \
            --chunk-size auto
        """


# ---------------------------------------------------------------------------
# Step 3: Extract individual muscle masks from multi-label segmentation
# ---------------------------------------------------------------------------


rule extract_muscle_masks:
    input:
        segmentation=os.path.join(
            OUT_DIR,
            "muscle_segmentations",
            "raw",
            "musclemap_segmentation_bone_subtracted.nii.gz",
        ),
    output:
        masks=expand(
            os.path.join(
                OUT_DIR, "muscle_segmentations", "extracted", "{muscle}.nii.gz"
            ),
            muscle=MUSCLE_LABELS,
        ),
    params:
        py_exe=lambda w: get_py_exe(musclemap_env_name()),
        out_dir=os.path.join(OUT_DIR, "muscle_segmentations", "extracted"),
    shell:
        """
        "{params.py_exe}" src/python/muscles_segmentation_extraction/extract_muscle_masks.py \
            {input.segmentation} \
            --output-dir {params.out_dir} \
            --config config/config.json
        """


# ---------------------------------------------------------------------------
# Step 2b: Subtract combined raw bone masks from raw MuscleMap segmentation
# ---------------------------------------------------------------------------


rule subtract_bone_from_raw_muscle_segmentation:
    input:
        muscle_seg=os.path.join(
            OUT_DIR, "muscle_segmentations", "raw", "musclemap_segmentation.nii.gz"
        ),
        bone_masks=expand(
            os.path.join(OUT_DIR, "bone_segmentations", "raw", "{bone}.nii.gz"),
            bone=BONE_MASKS,
        ),
    output:
        muscle_seg=os.path.join(
            OUT_DIR,
            "muscle_segmentations",
            "raw",
            "musclemap_segmentation_bone_subtracted.nii.gz",
        ),
    params:
        py_exe=lambda w: get_py_exe(totalseg_env_name()),
        bone_dir=os.path.join(OUT_DIR, "bone_segmentations", "raw"),
        dilation=config.get("muscle_preprocessing", {}).get(
            "bone_subtraction_dilation_radius", 0
        ),
    shell:
        """
        "{params.py_exe}" src/python/subtract_bone_from_muscle.py \
            --muscle-mask {input.muscle_seg} \
            --bone-mask-dir {params.bone_dir} \
            --output-mask {output.muscle_seg} \
            --dilation-radius {params.dilation}
        """
