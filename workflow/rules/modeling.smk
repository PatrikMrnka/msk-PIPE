# modeling.smk -- OpenSim model generation, attachment extraction, muscle wrapping.
#
# Step 7:  Generate the bone model via MSK-STAPLE (MATLAB).
# Step 8:  Extract muscle-to-bone attachment areas (C++).
# Step 9:  Generate the MuscleGeneratorTool XML configuration.
# Step 10: Run Muscle Wrapping 2.0 to produce the final model.


# ---------------------------------------------------------------------------
# Step 7: OpenSim bone model via MSK-STAPLE
# ---------------------------------------------------------------------------


rule msk_staple:
    input:
        staple_meshes=[
            os.path.join(BONE_STAPLE_DIR, "pelvis_no_sacrum.stl"),
            os.path.join(BONE_STAPLE_DIR, "femur_r.stl"),
            os.path.join(BONE_STAPLE_DIR, "tibia_r.stl"),
        ],
        matlab_script="src/python/staple_processing/hip_model.m",
        sacrum_mesh=os.path.join(OUT_DIR, "bone_models", "sacrum.stl"),
    output:
        osim=os.path.join(OUT_DIR, "bone_model.osim"),
        geom_dir=directory(os.path.join(OUT_DIR, "Geometry")),
    params:
        py_exe=get_py_exe("msk_base"),
        mesh_dir=BONE_STAPLE_DIR,
        staple_path=config.get("paths", {}).get("staple_path", "src/STAPLE"),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "msk_staple.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
    shell:
        """
        "{params.py_exe}" src/python/staple_processing/process_staple.py \
            --input-dir "{params.mesh_dir}" \
            --output-osim "{output.osim}" \
            --output-geom-dir "{output.geom_dir}" \
            --staple-path "{params.staple_path}" \
            --matlab-script "{input.matlab_script}" \
        && "{params.py_exe}" src/python/staple_processing/add_sacrum_mesh.py \
            --osim "{output.osim}" \
            --mesh-file "bone_models/sacrum.stl"
        """

# rule convert_to_vtk_bones:
#     input:
#         bones_dir=os.path.join(OUT_DIR, "bone_models", "{bone}.stl"),
#     output:
#         vtks_dir=os.path.join(OUT_DIR, "VTK", "{bone}.vtk"),
#     wildcard_constraints:
#         bone="|".join(BONE_MASKS),
#     params:
#         py_exe=get_py_exe("msk_base"),
#     benchmark:
#         os.path.join(OUT_DIR, "benchmarks", "convert_to_vtk_bones_{bone}.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
#     shell:
#         """
#         "{params.py_exe}" src/python/CONVERTOVTK_DELETEAFTER.py \
#             --input {input.bones_dir} \
#             --output {output.vtks_dir}
#         """

MUSCLES = list(MUSCLE_LABELS)

# rule convert_to_vtk_muscles:
#     input:
#         muscles_path=os.path.join(OUT_DIR, "muscle_models", "{muscle}.obj")
#     output:
#         vtks_dir=os.path.join(OUT_DIR, "VTK", "{muscle}.vtk"),
#     wildcard_constraints:
#         muscle="|".join(MUSCLE_LABELS),
#     params:
#         py_exe=get_py_exe("msk_base"),
#     benchmark:
#         os.path.join(OUT_DIR, "benchmarks", "convert_to_vtk_muscles_{muscle}.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
#     shell:
#         """
#         "{params.py_exe}" src/python/CONVERTOVTK_DELETEAFTER.py \
#             --input {input.muscles_path} \
#             --output {output.vtks_dir}
#         """
# ---------------------------------------------------------------------------
# Step 8: Extract muscle-to-bone attachment points
# ---------------------------------------------------------------------------
METHOD = config.get("attachment_extraction", {}).get("method", "atlas_registration")
LHDL_BONES = config.get("attachment_extraction", {}).get("lhdl_bones_dir", "")
LHDL_MUSCLES = config.get("attachment_extraction", {}).get("lhdl_muscles_dir", "")


BONE_MUSCLE_MAP = {}
for muscle_name, roles in TOPOLOGY.items():
    if METHOD == "user_provided" and not roles.get("include_in_xml", True):
        continue
    for role in ("origin", "insertion"):
        bone_name = roles[role]
        if bone_name not in BONE_MUSCLE_MAP:
            BONE_MUSCLE_MAP[bone_name] = {"inputs": [], "outputs": []}

        suffix = "Ori" if role == "origin" else "Ins"
        out_vtk = os.path.join(OUT_DIR, "attachments", f"{muscle_name}_{suffix}.vtk")
        
        if METHOD == "segmentation_proximity":
            in_data = os.path.join(OUT_DIR, "muscle_models", f"{roles['label']}.obj")
        elif METHOD == "atlas_registration":
            muscle_label = roles["label"]
            in_data = os.path.join(LHDL_MUSCLES, muscle_label, f"{muscle_name}_{suffix}.vtk")
        elif METHOD == "user_provided":
            in_data = os.path.join("data", "input", "landmarks", f"{muscle_name}_{suffix}.vtk")
            
        BONE_MUSCLE_MAP[bone_name]["inputs"].append(in_data)
        BONE_MUSCLE_MAP[bone_name]["outputs"].append(out_vtk)


if METHOD == "segmentation_proximity":
    for bone, mappings in BONE_MUSCLE_MAP.items():
        rule:
            name:
                f"extract_attachments_{bone}"
            input:
                geom_dir=os.path.join(OUT_DIR, "Geometry"),
                pelvis=os.path.join(BONE_STAPLE_DIR, "pelvis_with_sacrum.obj") if bone == "pelvis_with_sacrum" else [],
                muscles_done=os.path.join(OUT_DIR, "muscle_models", ".done")
            output:
                done=touch(os.path.join(OUT_DIR, "attachments", f".done_{bone}"))
            params:
                cpp_bin=extract_attachments_bin(),
                bone_mesh=lambda w, b=bone: os.path.join(OUT_DIR, "Geometry", f"{b}.obj") if b != "pelvis_with_sacrum" else os.path.join(BONE_STAPLE_DIR, "pelvis_with_sacrum.obj"),
                threshold=config.get("attachment_extraction", {}).get("threshold_mm", 1.0),
                clip_fraction=config.get("attachment_extraction", {}).get("clip_fraction", 0.25),
                muscle_args=" ".join([f'"{i}" "{o}"' for i, o in zip(mappings["inputs"], mappings["outputs"])])
            benchmark:
                os.path.join(OUT_DIR, "benchmarks", f"extract_attachments_proximity_{bone}.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
            shell:
                """
                "{params.cpp_bin}" "{params.bone_mesh}" {params.threshold} {params.clip_fraction} {params.muscle_args}
                """

elif METHOD == "atlas_registration":
    for bone, mappings in BONE_MUSCLE_MAP.items():
        rule:
            name:
                f"extract_attachments_lhdl_{bone}"
            input:
                geom_dir=os.path.join(OUT_DIR, "Geometry"),
                pelvis=os.path.join(BONE_STAPLE_DIR, "pelvis_with_sacrum.stl") if bone == "pelvis_with_sacrum" else [],
                # Načítáme dynamicky všechny LHDL úpony jako závislost tohoto pravidla
                lhdl_att=mappings["inputs"]
            output:
                # Očekávané VTK soubory
                vtks=mappings["outputs"],
                done=touch(os.path.join(OUT_DIR, "attachments", f".done_{bone}"))
            params:
                py_exe=get_py_exe("msk_base"),
                # Předzpracované LHDL kosti
                lhdl_bone=os.path.join(LHDL_BONES, f"{bone}.obj"),
                # Target STAPLE kosti
                target_bone=lambda w, b=bone: os.path.join(BONE_STAPLE_DIR, f"{b}.stl") if b != "pelvis_with_sacrum" else os.path.join(BONE_STAPLE_DIR, "pelvis_with_sacrum.stl")
            
            benchmark:
                os.path.join(OUT_DIR, "benchmarks", f"extract_attachments_atlas_{bone}.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""

            shell:
                """
                "{params.py_exe}" src/python/extract_attachments_runner/map_lhdl_attachments.py \
                    --lhdl-bone "{params.lhdl_bone}" \
                    --target-bone "{params.target_bone}" \
                    --lhdl-attachments {input.lhdl_att} \
                    --outputs {output.vtks}
                """

elif METHOD == "user_provided":
    for bone, mappings in BONE_MUSCLE_MAP.items():
        rule:
            name:
                f"extract_attachments_user_{bone}"
            input:
                user_att=mappings["inputs"]
            output:
                vtks=mappings["outputs"],
                done=touch(os.path.join(OUT_DIR, "attachments", f".done_{bone}"))
            benchmark:
                os.path.join(OUT_DIR, "benchmarks", f"extract_attachments_user_{bone}.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
            run:
                import shutil
                for in_f, out_f in zip(input.user_att, output.vtks):
                    shutil.copy2(in_f, out_f)
else:
    raise ValueError(f"Unsupported attachment extraction method: {METHOD}")

rule all_attachments:
    input:
        [os.path.join(OUT_DIR, "attachments", f".done_{bone}") for bone in BONE_MUSCLE_MAP.keys()]
    output:
        done=touch(os.path.join(OUT_DIR, "attachments", ".done"))


# ---------------------------------------------------------------------------
# Step 9: Generate MuscleGeneratorTool XML
# ---------------------------------------------------------------------------


rule prepare_muscle_wrapping:
    input:
        osim=os.path.join(OUT_DIR, "bone_model.osim"),
        muscles_done=os.path.join(OUT_DIR, "muscle_models", ".done"),
        vtks_dir=os.path.join(OUT_DIR, "attachments", ".done"),
    output:
        xml=os.path.join(OUT_DIR, "setup_MuscleGeneratorTool.xml"),
    params:
        py_exe=get_py_exe("msk_base"),
        muscles_dir=os.path.join(OUT_DIR, "muscle_models"),
        vtks_dir=os.path.join(OUT_DIR, "attachments"),
        kinematics_algorithm=config.get("muscle_wrapping", {}).get(
            "kinematics_algorithm", "luca"
        ),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "prepare_muscle_wrapping.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
    shell:
        """

        "{params.py_exe}" src/python/extract_attachments_runner/generate_attachment_xml.py \
            --osim      {input.osim} \
            --muscles   {params.muscles_dir} \
            --vtks      {params.vtks_dir} \
            --topology  config/muscle_topology.json \
            --out-xml   {output.xml} \
            --kinematics-algorithm {params.kinematics_algorithm} \
            --num-lines 100
        """


# ---------------------------------------------------------------------------
# Step 10: Run Muscle Wrapping 2.0
# ---------------------------------------------------------------------------


rule prepare_experiments_dir:
    output:
        experiments_dir=directory(os.path.join(OUT_DIR, "Experiments")),
    params:
        py_exe=get_py_exe("msk_base"),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "prepare_experiments_dir.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
    run:
        os.makedirs(output.experiments_dir, exist_ok=True)


rule run_muscle_wrapping:
    input:
        xml=os.path.join(OUT_DIR, "setup_MuscleGeneratorTool.xml"),
        experiments_dir=os.path.join(OUT_DIR, "Experiments"),
    output:
        osim=os.path.join(OUT_DIR, "pipeline_model.osim"),
    params:
        workdir=OUT_DIR,
        opensim=str(Path(MW_PATH_DIR, "Bin", "opensim-cmd.exe").resolve()),
        dll=str(Path(MW_PATH_DIR, "Bin", "OsimMuscleGeneratorTool.dll").resolve()),
    benchmark:
        os.path.join(OUT_DIR, "benchmarks", "run_muscle_wrapping.txt") if config.get("user_settings", {}).get("enable_benchmarking", True) else ""
    shell:
        r"""
        "{params.opensim}" -L "{params.dll}" run-tool "{input.xml}"
        """
