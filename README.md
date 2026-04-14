# MSK Pipeline

Automated pipeline for musculoskeletal model generation from medical images.
Converts CT/MRI scans into fully parameterised OpenSim biomechanical models
through segmentation, meshing, and muscle wrapping.

## Architecture

The pipeline is orchestrated by [Snakemake](https://snakemake.readthedocs.io/)
and managed by a Python runner that handles environment setup, dependency
checks, and pipeline execution.

```
python -m runner [--input <file_or_dir>]
        |
        v
  Pre-flight checks (runner/)
    - GPU detection
    - Conda environment setup (Micromamba)
    - External tool verification (MW2, STAPLE, MATLAB, VTK)
    - C++ binary compilation (mask_to_mesh, extract_attachments)
        |
        v
  Snakemake DAG execution (workflow/)
    Step 0:  Input preparation (NIfTI / RAW / DICOM)
    Step 1:  Bone segmentation (TotalSegmentator)
    Step 2:  Muscle segmentation (MuscleMap)
    Step 3:  Muscle mask extraction (multi-label -> individual)
    Step 4:  Mask cleaning (binarize, filter, morphology) -- per file
    Step 5:  Mesh generation (NIfTI -> STL/OBJ via VTK) -- per file
    Step 6:  Mesh renaming and merging for STAPLE
    Step 7:  OpenSim bone model generation (MSK-STAPLE via MATLAB)
    Step 8:  Muscle attachment extraction (C++ proximity search)
    Step 9:  MuscleGeneratorTool XML configuration
    Step 10: Muscle Wrapping 2.0 execution
        |
        v
  Output: pipeline_model.osim
```

## Project Structure

```
msk-pipeline/
├── config/
│   ├── config.json              # Main configuration (paths, parameters, labels)
│   ├── muscle_topology.json     # Muscle-to-bone attachment definitions
│   ├── env_base.yaml            # Conda env: Snakemake + core Python packages
│   ├── env_totalseg_cpu.yaml    # Conda env: TotalSegmentator (CPU)
│   ├── env_totalseg_gpu.yaml    # Conda env: TotalSegmentator (GPU)
│   ├── env_musclemap_cpu.yaml   # Conda env: MuscleMap (CPU)
│   └── env_musclemap_gpu.yaml   # Conda env: MuscleMap (GPU)
├── runner/                      # Pipeline orchestration & pre-flight checks
│   ├── __main__.py              # CLI entry point (python -m runner)
│   ├── preflight.py             # Pre-flight check orchestrator
│   ├── pipeline.py              # Snakemake launcher, run ID management
│   ├── config_io.py             # JSON config load/save
│   ├── constants.py             # Path constants and defaults
│   ├── system.py                # GPU detection, process management
│   ├── ui.py                    # Rich console output helpers
│   ├── micromamba.py            # Conda environment management
│   ├── external_tools.py        # External dependency checks & compilation
│   ├── matlab.py                # MATLAB + OpenSim API setup
│   └── musclemap.py             # MuscleMap repository setup
├── workflow/
│   ├── Snakefile                # Top-level orchestrator (includes rule modules)
│   └── rules/
│       ├── common.smk           # Shared constants, helpers, config derivation
│       ├── input.smk            # Input format detection & normalisation
│       ├── segmentation.smk     # TotalSegmentator + MuscleMap rules
│       ├── preprocessing.smk    # Per-file mask cleaning rules
│       ├── meshing.smk          # Per-file meshing, renaming, merging
│       └── modeling.smk         # STAPLE, attachments, muscle wrapping
├── src/
│   ├── python/
│   │   ├── validate_inputs.py
│   │   ├── load_image.py
│   │   ├── clean_masks.py                          # Mask post-processing
│   │   ├── merge_meshes.py                         # Mesh merging & splitting
│   │   ├── rename_bones.py                         # STAPLE name mapping
│   │   ├── muscle_names.py                         # Shared muscle name mapping
│   │   ├── converting_formats/
│   │   │   ├── CT_dicom_to_nifti.py
│   │   │   └── CT_raw_to_nifti.py
│   │   ├── bones_segmentation/
│   │   │   └── run_totalsegmentator.py
│   │   ├── muscles_segmentation_extraction/
│   │   │   ├── run_musclemap.py
│   │   │   └── extract_muscle_masks.py
│   │   ├── staple_processing/
│   │   │   ├── process_staple.py
│   │   │   └── hip_model.m
│   │   └── extract_attachments_runner/
│   │       ├── run_extraction.py
│   │       └── generate_attachment_xml.py
│   └── cpp/
│       ├── mask_to_mesh/                           # NIfTI -> STL/OBJ (VTK)
│       │   └── src/
│       │       ├── main.cpp
│       │       └── CMakeLists.txt
│       └── extract_attachments/                    # Muscle-bone proximity
│           └── src/
│               ├── main.cpp
│               ├── AttachmentExtractor.h
│               ├── AttachmentExtractor.cpp
│               └── CMakeLists.txt
├── requirements.txt
└── README.md
```

## Prerequisites

| Dependency | Purpose | Notes |
|---|---|---|
| **Python** 3.11+ | Runner and scripts | 3.12 for base env, 3.11.8 for MuscleMap |
| **Micromamba** | Conda environment management | Auto-installed on Windows |
| **Snakemake** | Workflow orchestration | Installed via conda |
| **MATLAB** R2018b+ | MSK-STAPLE model generation | Requires Curve Fitting and Statistics & ML toolboxes |
| **CMake** >= 3.10 | C++ binary compilation | |
| **VTK** 9.0+ | 3D mesh processing | Shipped with Muscle Wrapping 2.0 |
| **Muscle Wrapping 2.0** (MW2) | Final muscle wrapping | Provides `opensim-cmd` and `OsimMuscleGeneratorTool.dll` |
| **MSK-STAPLE** | OpenSim bone model generation | MATLAB toolbox |
| **MuscleMap** | Muscle segmentation | Cloned from GitHub automatically |
| **OpenSim** API | Biomechanical modelling | Configured via MW2's bundled OpenSim |

## Input

The pipeline accepts three input formats:

- **NIfTI** (`.nii` / `.nii.gz`) -- a single CT or MRI volume.
- **DICOM** -- a directory of `.dcm` files (or extension-less DICOM files).
- **RAW** -- a flat binary volume (`.raw`) with an accompanying `coordinates.txt`
  file containing per-slice Z coordinates.

By default the pipeline scans `data/input/` for files. You can also specify an
explicit input:

```bash
# Process a specific NIfTI file:
python -m runner --input /path/to/scan.nii.gz

# Process a DICOM directory:
python -m runner --input /path/to/dicom_folder/

# Auto-detect from the default input directory:
python -m runner
```

## Output

Each run produces a numbered directory under `data/output/`:

```
data/output/run_1/
├── image/ct.nii.gz                     # Normalised input
├── bone_segmentations/
│   ├── raw/                            # TotalSegmentator output
│   └── cleaned/                        # Post-processed bone masks
├── muscle_segmentations/
│   ├── raw/                            # MuscleMap output
│   ├── extracted/                      # Individual muscle masks
│   └── cleaned/                        # Post-processed muscle masks
├── bone_models/                        # STL meshes
├── bone_models_renamed/                # STAPLE-compatible names
├── bone_models_merged/                 # Merged pairs
├── muscle_models/                      # OBJ meshes
├── Geometry/                           # OpenSim visualisation geometry
├── attachments/                        # VTK attachment point clouds
├── bone_model.osim                     # OpenSim bone model (STAPLE)
├── setup_MuscleGeneratorTool.xml       # MW2 configuration
└── pipeline_model.osim                 # Final OpenSim model
```

## Pipeline Steps

### Step 0: Input Preparation
Detects the input format and converts it to a normalised NIfTI volume
(`ct.nii.gz`). DICOM conversion uses SimpleITK (GDCM), RAW conversion uses
nibabel with Z-coordinate handling.

### Step 1: Bone Segmentation
Runs [TotalSegmentator](https://github.com/wasserth/TotalSegmentator) to
segment bone structures: pelvis (hip_left, hip_right), sacrum, femur (L/R),
tibia, and fibula. Supports both CT and MR models, GPU or CPU.

### Step 2: Muscle Segmentation
Runs [MuscleMap](https://github.com/MuscleMap/MuscleMap) to produce a
multi-label segmentation of 17 lower-limb muscle groups (34 individual muscles,
left and right).

### Step 3: Muscle Mask Extraction
Splits the multi-label MuscleMap output into individual binary masks using the
label mapping defined in `config/config.json`.

### Step 4: Mask Cleaning
Per-file post-processing of segmentation masks:
- Binarisation with configurable threshold
- Connected-component analysis and small-component removal
- Morphological closing and opening
- Optional iterative hole filling

### Step 5: Mesh Generation
Converts cleaned NIfTI masks to surface meshes using a C++ binary built on VTK:
- Flying Edges isosurface extraction
- Windowed-sinc smoothing (configurable iterations and passband)
- Topology cleaning and triangulation
- Bones are saved as STL, muscles as OBJ

### Step 6: Mesh Renaming and Merging
- Renames bone meshes to STAPLE-compatible names (e.g. `hip_left` ->
  `pelvis_no_sacrum`)
- Merges pelvis halves, splits tibia+fibula/patella/phalanges into L/R
  components using PyMeshLab

### Step 7: OpenSim Bone Model (MSK-STAPLE)
Invokes MATLAB to run the MSK-STAPLE toolbox, which computes joint coordinate
systems, assigns mass properties, and generates `bone_model.osim`.

### Step 8: Attachment Extraction
A C++ binary uses `vtkStaticCellLocator` to find muscle vertices within a
configurable distance threshold of each bone surface. Outputs ordered contour
points as VTK point clouds.

### Step 9: XML Configuration
Generates `setup_MuscleGeneratorTool.xml` with mesh references, attachment
areas, fibre parameters, and joint interaction information extracted from the
bone model.

### Step 10: Muscle Wrapping
Runs OpenSim's `opensim-cmd` with `OsimMuscleGeneratorTool.dll` to produce the
final `pipeline_model.osim` with wrapped muscle fibres.

## Configuration

All pipeline parameters are in `config/config.json`:

| Section | Key | Description |
|---|---|---|
| `paths.input_dir` | `data/input` | Default input directory |
| `paths.output_dir` | `data/output` | Output base directory |
| `totalsegmentator.device` | `gpu` / `cpu` | Segmentation device |
| `totalsegmentator.model` | `ct` / `mr` | Imaging modality |
| `totalsegmentator.fast` | `true` / `false` | Fast mode (lower resolution) |
| `bone_preprocessing.*` | | Mask cleaning parameters for bones |
| `muscle_preprocessing.*` | | Mask cleaning parameters for muscles |
| `bone_to_mesh.*` | | Smoothing parameters for bone meshes |
| `muscle_to_mesh.*` | | Smoothing parameters for muscle meshes |
| `attachment_extraction.threshold_mm` | `2.0` | Distance threshold for attachments |
| `muscle_map.labels` | | Muscle name -> label ID mapping |

Muscle-to-bone attachment topology is defined in `config/muscle_topology.json`.

## Running

```bash
# Full pipeline with pre-flight checks:
python -m runner

# Skip pre-flight checks (if dependencies are already set up):
# Set "skip_preflight_checks": true in config/config.json

# With a specific input:
python -m runner --input /path/to/scan.nii.gz
```

## License

See repository for license details.
