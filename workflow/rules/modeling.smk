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
        repaired_done=os.path.join(OUT_DIR, "bone_models_merged_repaired", ".done"),
        matlab_script="src/python/staple_processing/hip_model.m",
    output:
        osim=os.path.join(OUT_DIR, "bone_model.osim"),
        geom_dir=directory(os.path.join(OUT_DIR, "Geometry")),
    params:
        py_exe=get_py_exe("msk_base"),
        mesh_dir=os.path.join(OUT_DIR, "bone_models_merged_repaired"),
        staple_path=config.get("paths", {}).get("staple_path", "src/STAPLE"),
    shell:
        """

        "{params.py_exe}" src/python/staple_processing/process_staple.py \
            --input-dir "{params.mesh_dir}" \
            --output-osim "{output.osim}" \
            --output-geom-dir "{output.geom_dir}" \
            --staple-path "{params.staple_path}" \
            --matlab-script "{input.matlab_script}"
        """

rule convert_to_vtk_bones:
    input:
        bones_dir=os.path.join(OUT_DIR, "bone_models", "{bone}.stl"),
    output:
        vtks_dir=os.path.join(OUT_DIR, "VTK", "{bone}.vtk"),
    params:
        py_exe=get_py_exe("msk_base"),
    shell:
        """ 

        "{params.py_exe}" src/python/CONVERTOVTK_DELETEAFTER.py \
            --input {input.bones_dir} \
            --output {output.vtks_dir}
        """

MUSCLES = [
    "iliacus_r",
    "gluteus_maximus_r",
    "gluteus_medius_r",
    "gluteus_minimus_r",
]

rule convert_to_vtk_muscles:
    input:
        # pouze iliacus_r, gluteus_maximus_r, gluteus_medius_r, gluteus_minimus_r z muscle_models
        muscles_path=os.path.join(OUT_DIR, "muscle_models", "{muscle}.obj")
    output:
        vtks_dir=os.path.join(OUT_DIR, "VTK", "{muscle}.vtk"),
    params:
        py_exe=get_py_exe("msk_base"),
    wildcard_constraints:
        muscle="iliacus_r|gluteus_maximus_r|gluteus_medius_r|gluteus_minimus_r"
    shell:
        """

        "{params.py_exe}" src/python/CONVERTOVTK_DELETEAFTER.py \
            --input {input.muscles_path} \
            --output {output.vtks_dir}
        """

# ---------------------------------------------------------------------------
# Step 8: Extract muscle-to-bone attachment points
# ---------------------------------------------------------------------------


rule extract_attachments:
    input:
        bones_dir=os.path.join(OUT_DIR, "Geometry"),
        muscles_done=os.path.join(OUT_DIR, "muscle_models", ".done"),
    output:
        vtks_dir=directory(os.path.join(OUT_DIR, "attachments")),
    params:
        py_exe=get_py_exe("msk_base"),
        cpp_bin=extract_attachments_bin(),
        threshold=config.get("attachment_extraction", {}).get("threshold_mm", 1.0),
        clip_fraction=config.get("attachment_extraction", {}).get("clip_fraction", 0.25),
        muscles_dir=os.path.join(OUT_DIR, "muscle_models")
    shell:
        """

        "{params.py_exe}" src/python/extract_attachments_runner/run_extraction.py \
            --bones     {input.bones_dir} \
            --muscles   {params.muscles_dir} \
            --topology  config/muscle_topology.json \
            --out-dir   {output.vtks_dir} \
            --threshold {params.threshold} \
            --clip-fraction {params.clip_fraction} \
            --cpp-bin   "{params.cpp_bin}"
        """


# ---------------------------------------------------------------------------
# Step 9: Generate MuscleGeneratorTool XML
# ---------------------------------------------------------------------------


rule prepare_muscle_wrapping:
    input:
        osim=os.path.join(OUT_DIR, "bone_model.osim"),
        muscles_done=os.path.join(OUT_DIR, "muscle_models", ".done"),
        vtks_dir=os.path.join(OUT_DIR, "attachments"),
    output:
        xml=os.path.join(OUT_DIR, "setup_MuscleGeneratorTool.xml"),
    params:
        py_exe=get_py_exe("msk_base"),
        muscles_dir=os.path.join(OUT_DIR, "muscle_models"),
        kinematics_algorithm=config.get("muscle_wrapping", {}).get(
            "kinematics_algorithm", "luca"
        ),
    shell:
        """

        "{params.py_exe}" src/python/extract_attachments_runner/generate_attachment_xml.py \
            --osim      {input.osim} \
            --muscles   {params.muscles_dir} \
            --vtks      {input.vtks_dir} \
            --topology  config/muscle_topology.json \
            --out-xml   {output.xml} \
            --kinematics-algorithm {params.kinematics_algorithm} \
            --num-lines 100
        """


# ---------------------------------------------------------------------------
# Step 10: Run Muscle Wrapping 2.0
# ---------------------------------------------------------------------------


rule run_muscle_wrapping:
    input:
        xml=os.path.join(OUT_DIR, "setup_MuscleGeneratorTool.xml"),
    output:
        osim=os.path.join(OUT_DIR, "pipeline_model.osim"),
    params:
        workdir=OUT_DIR,
        opensim=str(Path(MW_PATH_DIR, "Bin", "opensim-cmd.exe").resolve()),
        dll=str(Path(MW_PATH_DIR, "Bin", "OsimMuscleGeneratorTool.dll").resolve()),
    shell:
        r"""
        "{params.opensim}" -L "{params.dll}" run-tool "{input.xml}"
        """
