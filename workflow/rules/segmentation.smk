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


_ts_muscle_engine = config.get("user_settings", {}).get("muscle_segmentator", "musclemap") == "totalsegmentator"

_ts_all_rois = BONE_MASKS + (MUSCLE_MASKS_TOTALSEGMENTATOR if _ts_muscle_engine else [])

rule total_segmentator:
    input:
        nii=NII_OUT,
    output:
        masks=expand(
            os.path.join(OUT_DIR, "bone_segmentations", "raw", "{roi}.nii.gz"),
            roi=_ts_all_rois,
        ),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "total_segmentator.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
    params:
        py_exe=lambda w: get_py_exe(totalseg_env_name()),
        device=config.get("totalsegmentator", {}).get("device", "cpu"),
        model=config.get("totalsegmentator", {}).get("model", "ct"),
        fast="--fast" if config.get("totalsegmentator", {}).get("fast", False) else "",
        out_dir=os.path.join(OUT_DIR, "bone_segmentations", "raw"),
        rois=" ".join(_ts_all_rois),
    resources:
        segmentation_mutex=1,
    shell:
        """
        "{params.py_exe}" src/python/bones_segmentation/run_totalsegmentator.py \
            {input.nii} \
            --output-dir {params.out_dir} \
            --device {params.device} \
            --model {params.model} \
            --roi-subset {params.rois} \
            {params.fast}
        """

# ---------------------------------------------------------------------------
# Step 2: Muscle segmentation
# ---------------------------------------------------------------------------

_seg_engine = config.get("user_settings", {}).get("muscle_segmentator", "musclemap")

if _seg_engine == "totalsegmentator":

    checkpoint total_segmentator_muscle:
        input:
            masks=expand(
                os.path.join(OUT_DIR, "bone_segmentations", "raw", "{muscle}.nii.gz"),
                muscle=MUSCLE_MASKS_TOTALSEGMENTATOR,
            ),
        output:
            masks=expand(
                os.path.join(OUT_DIR, "muscle_segmentations_totalsegmentator", "raw", "{muscle}.nii.gz"),
                muscle=MUSCLE_MASKS_TOTALSEGMENTATOR,
            ),
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "total_segmentator_muscles.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        run:
            import shutil, os
            out_dir = os.path.join(OUT_DIR, "muscle_segmentations_totalsegmentator", "raw")
            os.makedirs(out_dir, exist_ok=True)
            for src in input.masks:
                dst = os.path.join(out_dir, os.path.basename(src))
                shutil.copy2(src, dst)

else:

    rule muscle_map:
        input:
            nii=NII_OUT,
        output:
            masks_dir=directory(os.path.join(OUT_DIR, "muscle_segmentations", "raw")),
            segmentation=os.path.join(
                OUT_DIR, "muscle_segmentations", "raw", "musclemap_segmentation.nii.gz"
            ),
        params:
            py_exe=lambda w: get_py_exe(musclemap_env_name()),
        resources:
            segmentation_mutex=1,
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "muscle_map.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        shell:
            """
            "{params.py_exe}" src/python/muscles_segmentation_extraction/run_musclemap.py \
                {input.nii} \
                --output-dir {output.masks_dir} \
                --chunk-size auto
            """


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
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "subtract_bone_from_raw_muscle_segmentation.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        shell:
            """
            "{params.py_exe}" src/python/subtract_bone_from_muscle.py \
                --muscle-mask {input.muscle_seg} \
                --bone-mask-dir {params.bone_dir} \
                --output-mask {output.muscle_seg} \
                --dilation-radius {params.dilation}
            """


    checkpoint extract_muscle_masks:
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
        benchmark:
            os.path.join(OUT_DIR, "benchmarks", "extract_muscle_masks.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
        shell:
            """
            "{params.py_exe}" src/python/muscles_segmentation_extraction/extract_muscle_masks.py \
                {input.segmentation} \
                --output-dir {params.out_dir} \
                --config config/config.json
            """
