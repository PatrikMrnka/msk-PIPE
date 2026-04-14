# meshing.smk -- Mask-to-mesh conversion, STAPLE renaming, and mesh merging.
#
# Step 5a: Convert cleaned bone masks to STL meshes (per file).
# Step 5b: Convert cleaned muscle masks to OBJ meshes (per file).
# Step 6a: Rename bone meshes to STAPLE-compatible names.
# Step 6b: Merge bone mesh pairs for STAPLE input.


# ---------------------------------------------------------------------------
# Step 5a: Bone mask -> STL (per file)
# ---------------------------------------------------------------------------

rule bone_mask_to_stl:
    input:
        mask=os.path.join(OUT_DIR, "bone_segmentations", "cleaned", "{bone}.nii.gz"),
    output:
        mesh=os.path.join(OUT_DIR, "bone_models", "{bone}.stl"),
    params:
        cpp_bin=mask_to_mesh_bin(),
        out_dir=os.path.join(OUT_DIR, "bone_models"),
        smooth=config.get("bone_to_mesh", {}).get("smooth_iterations", 30),
        passband=config.get("bone_to_mesh", {}).get("passband", 0.01),
    shell:
        """
        "{params.cpp_bin}" \
            --input-dir  {input.mask} \
            --output-dir {params.out_dir} \
            --smooth_iters {params.smooth} \
            --passband {params.passband} \
            --format stl
        """


# Aggregate: all bone meshes ready.
rule all_bone_meshes:
    input:
        expand(
            os.path.join(OUT_DIR, "bone_models", "{bone}.stl"),
            bone=BONE_MASKS,
        ),
    output:
        touch(os.path.join(OUT_DIR, "bone_models", ".done")),


# ---------------------------------------------------------------------------
# Step 5b: Muscle mask -> OBJ (per file)
# ---------------------------------------------------------------------------

rule muscle_mask_to_obj:
    input:
        mask=os.path.join(OUT_DIR, "muscle_segmentations", "cleaned", "{muscle}.nii.gz"),
    output:
        mesh=os.path.join(OUT_DIR, "muscle_models", "{muscle}.obj"),
    params:
        cpp_bin=mask_to_mesh_bin(),
        out_dir=os.path.join(OUT_DIR, "muscle_models"),
        smooth=config.get("muscle_to_mesh", {}).get("smooth_iterations", 30),
        passband=config.get("muscle_to_mesh", {}).get("passband", 0.005),
    shell:
        """
        "{params.cpp_bin}" \
            --input-dir  {input.mask} \
            --output-dir {params.out_dir} \
            --smooth_iters {params.smooth} \
            --passband {params.passband} \
            --format obj
        """


# Aggregate: all muscle meshes ready.
rule all_muscle_meshes:
    input:
        expand(
            os.path.join(OUT_DIR, "muscle_models", "{muscle}.obj"),
            muscle=MUSCLE_LABELS,
        ),
    output:
        touch(os.path.join(OUT_DIR, "muscle_models", ".done")),


# ---------------------------------------------------------------------------
# Step 6a: Rename bone STLs to STAPLE-compatible names
# ---------------------------------------------------------------------------

rule rename_bones_for_staple:
    input:
        done=os.path.join(OUT_DIR, "bone_models", ".done"),
        models_dir=os.path.join(OUT_DIR, "bone_models"),
    output:
        renamed_dir=directory(os.path.join(OUT_DIR, "bone_models_renamed")),
    params:
        py_exe=get_py_exe("msk_base"),
    shell:
        """
        "{params.py_exe}" src/python/rename_bones.py \
            --input-dir  {input.models_dir} \
            --output-dir {output.renamed_dir}
        """


# ---------------------------------------------------------------------------
# Step 6b: Merge bone mesh pairs for STAPLE
# ---------------------------------------------------------------------------

rule merge_meshes:
    input:
        models_dir=os.path.join(OUT_DIR, "bone_models_renamed"),
    output:
        meshes_dir=directory(os.path.join(OUT_DIR, "bone_models_merged")),
    params:
        py_exe=get_py_exe("msk_base"),
    shell:
        """
        "{params.py_exe}" src/python/merge_meshes.py \
            --input-dir  {input.models_dir} \
            --output-dir {output.meshes_dir}
        """
