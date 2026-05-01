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
    benchmark:
            os.path.join(OUT_DIR, "benchmarks", "bone_mask_to_stl_{bone}.txt")
            if config.get("user_settings", {}).get("enable_benchmarking", True)
            else ""

    params:
        cpp_bin=mask_to_mesh_bin(),
        out_dir=os.path.join(OUT_DIR, "bone_models"),
        smooth=config.get("bone_to_mesh", {}).get("smooth_iterations", 30),
        passband=config.get("bone_to_mesh", {}).get("passband", 0.01),
        decimate=config.get("bone_to_mesh", {}).get("target_reduction", 0.0),
    shell:
        """
        "{params.cpp_bin}" \
            --input-dir  {input.mask} \
            --output-dir {params.out_dir} \
            --smooth_iters {params.smooth} \
            --passband {params.passband} \
            --decimate_target {params.decimate} \
            --format stl
        """

# Aggregate: all bone meshes ready.
rule all_bone_meshes:
    input:
            expand(
                os.path.join(OUT_DIR, "bone_models", "{bone}.stl"),
                bone=BONE_MASKS,
            )
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
    benchmark:
            os.path.join(OUT_DIR, "benchmarks", "muscle_mask_to_obj_{muscle}.txt")
            if config.get("user_settings", {}).get("enable_benchmarking", True)
            else ""

    params:
        cpp_bin=mask_to_mesh_bin(),
        out_dir=os.path.join(OUT_DIR, "muscle_models"),
        smooth=config.get("muscle_to_mesh", {}).get("smooth_iterations", 30),
        passband=config.get("muscle_to_mesh", {}).get("passband", 0.005),
        decimate=config.get("bone_to_mesh", {}).get("target_reduction", 0.0),
    shell:
        """
        "{params.cpp_bin}" \
            --input-dir  {input.mask} \
            --output-dir {params.out_dir} \
            --smooth_iters {params.smooth} \
            --passband {params.passband} \
            --decimate_target {params.decimate} \
            --format obj
        """

rule all_muscle_meshes:
    input:
        expand(
            os.path.join(OUT_DIR, "muscle_models", "{muscle}.obj"),
            muscle=MUSCLE_LABELS,
        )
    output:
        touch(os.path.join(OUT_DIR, "muscle_models", ".done")),


# ---------------------------------------------------------------------------
# Step 6
# ---------------------------------------------------------------------------


ruleorder: copy_femur_r_to_staple > split_meshes > merge_bone_meshes

rule copy_femur_r_to_staple:
    input:
        mesh=os.path.join(OUT_DIR, "bone_models", "femur_right.stl"),
    output:
        mesh=os.path.join(BONE_STAPLE_DIR, "femur_r.stl"),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "copy_femur_r_to_staple.txt")
        if config.get("user_settings", {}).get("enable_benchmarking", True)
        else ""
    run:
        shutil.copy2(input.mesh, output.mesh)


# ---------------------------------------------------------------------------
# Mappings & Input Functions
# ---------------------------------------------------------------------------

# Slovník definující, z jakých souborů se skládají jednotlivé sloučené modely
MERGE_SOURCES = {
    "pelvis_no_sacrum": ["hip_left.stl", "hip_right.stl"],
    "pelvis_with_sacrum": ["hip_left.stl", "hip_right.stl", "sacrum.stl"],
    "tibia_fibula_temp": ["tibia.stl", "fibula.stl"],
}


def get_merge_inputs(wildcards):
    """Dynamicky načte seznam vstupních meshů pro slučování."""
    files = MERGE_SOURCES.get(wildcards.merged_bone, [])
    # Use posix paths to avoid Snakemake matching errors on Windows
    return [f"{OUT_DIR}/bone_models/{f}".replace("\\", "/") for f in files]


def get_split_input(wildcards):
    """Dynamicky určí vstupní soubor na základě jména kosti."""
    if wildcards.bone == "tibia":
        # Tibia se štípe ze sloučeného temp souboru
        return os.path.join(BONE_STAPLE_DIR, "tibia_fibula_temp.stl").replace("\\", "/")
    else:
        # Ostatní (např. patella) se berou přímo z bone_models
        return os.path.join(OUT_DIR, "bone_models", f"{wildcards.bone}.stl").replace(
            "\\", "/"
        )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

MERGE_BONE_PATTERN = "|".join(MERGE_SOURCES.keys())

rule merge_bone_meshes:
    input:
        meshes=get_merge_inputs,
    output:
        mesh=os.path.join(
            BONE_STAPLE_DIR, f"{{merged_bone,{MERGE_BONE_PATTERN}}}.{{ext,stl|obj}}"
        )
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "merge_bone_meshes_{merged_bone}_{ext}.txt")
        if config.get("user_settings", {}).get("enable_benchmarking", True)
        else ""

    params:
        py_exe=get_py_exe("msk_base"),
    shell:
        """
        "{params.py_exe}" src/python/merge_mesh.py \
            --input-meshes {input.meshes} \
            --output-mesh {output.mesh}
        """

rule split_meshes:
    input:
        mesh=get_split_input,
    output:
        left=os.path.join(BONE_STAPLE_DIR, "{bone}_l.stl"),
        right=os.path.join(BONE_STAPLE_DIR, "{bone}_r.stl"),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "split_meshes_{bone}.txt")
        if config.get("user_settings", {}).get("enable_benchmarking", True)
        else ""
    params:
        py_exe=get_py_exe("msk_base"),
    shell:
        """
        "{params.py_exe}" src/python/split_mesh.py \
            --input-mesh {input.mesh} \
            --left-output {output.left} \
            --right-output {output.right}
        """
