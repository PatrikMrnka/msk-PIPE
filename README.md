# MSK Pipeline

Automated pipeline for generating personalised musculoskeletal models from
medical images. Converts CT/MRI scans into fully parameterised OpenSim
biomechanical models (`.osim`) through segmentation, surface meshing,
muscle-attachment extraction, and muscle-wrapping simulation.

## Architecture

The pipeline is orchestrated by [Snakemake](https://snakemake.readthedocs.io/)
and managed by a Python runner that handles environment setup, dependency
checks, and pipeline execution.

```
python -m runner [--input <file_or_dir>] -> also automatical detection, but --input is recommened use! :-)
        |
        v
  Pre-flight checks (runner/)
    - GPU detection (CUDA)
    - Conda environment management (Micromamba)
    - External tool verification (MW2, STAPLE, MATLAB, VTK, MuscleMap, TotalSegmentator)
    - C++ binary compilation (mask_to_mesh, extract_attachments)
        |
        v
  Snakemake DAG execution (workflow/)
    Step 0:   Input preparation (NIfTI / RAW / DICOM)
    Step 1:   Bone segmentation (TotalSegmentator)
    Step 2:   Muscle segmentation (MuscleMap)
    Step 3:   Muscle mask extraction (multi-label → individual)
    Step 4:   Mask cleaning (binarise, filter, morphology) — per file
    Step 5:   Mesh generation (NIfTI → STL/OBJ via VTK) — per file
    Step 6:   Mesh merging for STAPLE
    Step 7:   OpenSim bone model generation (MSK-STAPLE via MATLAB)
    Step 8:   Muscle attachment extraction (proximity / atlas / user-provided)
    Step 9:   MuscleGeneratorTool XML configuration
    Step 10:  Muscle Wrapping 2.0 execution
    Step 11:  Statistical evaluation and benchmarking
        |
        v
  Output: pipeline_model.osim + statistical reports
```

## Prerequisites

| Dependency | Purpose | Notes |
|---|---|---|
| **Python** 3.12 | Runner, scripts, Snakemake | 3.11.8 for MuscleMap environment |
| **Micromamba** | Conda environment management | Auto-installed on Windows |
| **Snakemake** | Workflow orchestration | Installed via Conda (env_base) |
| **MATLAB** R2018b+ | MSK-STAPLE model generation | Requires Curve Fitting and Statistics & ML toolboxes |
| **CMake** ≥ 3.21 | C++ binary compilation | |
| **VTK** 9.0+ | 3D mesh processing (C++) | Shipped with Muscle Wrapping 2.0 |
| **Muscle Wrapping 2.0** | Final muscle-wrapping simulation | Provides `opensim-cmd` and `OsimMuscleGeneratorTool.dll` |
| **MSK-STAPLE** | Automated bone model creation | MATLAB toolbox |
| **MuscleMap** | Deep-learning muscle segmentation | Cloned from GitHub automatically |
| **OpenSim** API | Biomechanical modelling | Bundled with MW2 |

For correct operation in GPU mode with CUDA cores, the latest NVIDIA drivers must be installed.
If you have an NVIDIA GPU, its presence is verified via the `nvidia-smi` command.

Author tested it with MATLAB R2025b version. :-)

## Getting Started

Before running the pipeline for the first time, you need to set up the Python environment for the **runner** itself. The runner (`python -m runner`) uses your **host Python installation** (not one of the managed Conda environments), so its dependencies must be installed separately.

> [!IMPORTANT]
> The runner requires **Python 3.12**. Make sure `python --version` reports 3.12.x before proceeding.

### 1. Create a virtual environment (recommended)

Creating a virtual environment keeps the runner's dependencies isolated from your system Python:

```powershell
# From the project root (c:\msk-PIPE)
python -m venv .venv

# Activate the environment
.venv\Scripts\Activate.ps1        # PowerShell
# or
.venv\Scripts\activate.bat         # Command Prompt
```

> [!TIP]
> If PowerShell blocks script execution, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

### 2. Install runner dependencies

```powershell
pip install -r requirements.txt
```

This installs the minimal set of packages required by the runner (`pyyaml`, `rich`, `graphviz`,). All heavy pipeline dependencies (Snakemake, PyTorch, etc.) are managed automatically inside isolated Conda environments by the runner itself.

### 3. Run the pipeline

With the venv active, launch the runner from the project root:

```powershell
python -m runner --input data/input/ct/ct.nii.gz
```

On the very first run the runner will:
- Download and configure **Micromamba** (if not already present).

- Micromamba version: by default the runner downloads Micromamba `2.6.0-0`.
  You can override the version via `config/config.json` using either:

  ```json
  { "micromamba": { "version": "2.6.0-0" } }
  ```

  or the legacy top-level key:

  ```json
  { "micromamba_version": "2.6.0-0" }
  ```
- Create and populate all required Conda environments (`msk_base`, `msk_totalseg_gpu`, …).
- Compile the C++ binaries (`mask_to_mesh`, `extract_attachments`).
- Prompt for any missing configuration (input path, device, …).

Subsequent runs skip already-completed setup steps and go straight to pipeline execution.

---

## GPU / CPU Configuration

The pipeline automatically selects GPU or CPU mode based on the **`has_gpu`** setting in `config/config.json`.

### Quick Switch: GPU ↔ CPU

Simply change one setting in `config/config.json`:

```json
"user_settings": {
    "has_gpu": true,        // Use GPU (requires NVIDIA GPU + drivers)
    // or
    // "has_gpu": false,    // Use CPU (always works, but slower)
}
```

**When you change `has_gpu`, the runner automatically updates:**
- ✅ TotalSegmentator device: `gpu` or `cpu`
- ✅ MuscleMap environment: GPU or CPU PyTorch variant
- ✅ TotalSegmentator environment: GPU or CPU CUDA/PyTorch setup

### How It Works

The `runner/preflight.py` automatically configures based on `has_gpu`:

| `has_gpu` | TotalSegmentator | MuscleMap | Result |
|-----------|------------------|-----------|--------|
| `true` | `--device gpu` | `env_musclemap_gpu.yaml` | GPU mode (fast, requires NVIDIA GPU) |
| `false` | `--device cpu` | `env_musclemap_cpu.yaml` | CPU mode (slower, always works) |

### GPU Requirements

To use GPU mode (`has_gpu: true`), ensure:
1. **NVIDIA GPU** is installed on your system
2. **NVIDIA drivers** are up-to-date (check via `nvidia-smi`)
3. **CUDA-capable GPU** with sufficient VRAM (~4GB minimum for TotalSegmentator)

If `nvidia-smi` fails or GPU detection is disabled, the runner will automatically fall back to CPU mode.

### CPU-Only Setup

If you don't have a GPU (or want CPU-only for testing):
1. Set `has_gpu: false` in `config/config.json`
2. Run: `python -m runner --input data/input/ct/ct.nii.gz`

**Note:** CPU processing is significantly slower (~10-30x) than GPU, but produces identical results.

**IF `has_gpu` IS NOT AVAILABLE, THE SYSTEM WILL CHECK GPU AVAILABILITY AUTOMATICALLY!** 

---


**Micromamba "Package cache error" or "file is missing" on Windows**
During environment creation, you might encounter an error like `Invalid package cache, file ... is missing` or `Package cache error`. This is typically caused by the Windows 260 character path limit when unpacking libraries with deep folder structures (like `viskores`). 

To fix this, you must **enable Long Paths support** in Windows:
1. Open PowerShell as Administrator.
2. Run the following command:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```
3. Restart your terminal or IDE (VS Code) and run the pipeline again.

### STAPLE Pre-flight Automation

- During pre-flight, STAPLE is searched in `src/STAPLE` and then in `STAPLE_PATH`.
- If STAPLE is not found, the runner offers automatic download from GitHub into `src/STAPLE`.
- After STAPLE is detected or downloaded, pre-flight automatically applies a MATLAB R2023a+ compatibility patch in `GIBOC-core/SubFunctions/GeometricFun/PCRegionGrowing.m` (replaces `size(idx)` with `length(idx)` in `Pts_Out(...)`) when needed.
- The patch step is idempotent and is skipped if the fix is already present.
- CHECK: https://github.com/modenaxe/msk-STAPLE/issues/120

### Muscle Wrapping 2.0 (OsimMuscleGeneratorTool) Setup

The pipeline requires the Muscle Wrapping 2.0 library to perform the final muscle-wrapping simulation. Follow these steps to build and install it:

#### 1. Clone the Repository

Clone the Muscle Wrapping 2.0 repository from the `MrnkaBP` branch:

```bash
git clone -b MrnkaBP https://gitlab.com/besoft/muscle-wrapping-2.0.git src/MW2/Sources
```

This clones the repository into `src/MW2/Sources` relative to your project root.

#### 2. Build with CMake

Navigate to the project root and run CMake configure and build. The following commands use relative paths:

**Configure (CMake):**
```bash
cmake -B src/MW2/Build -S src/MW2/Sources/Sources `
  -DBUILD_EXTERNAL_DEPENDENCIES=OFF `
  -DBUILD_PIPELINE_DEPENDENCIES=ON `
  -DBUILD_SHARED_LIBS=ON `
  -DCMAKE_CONFIGURATION_TYPES="Debug;Release" `
  -DCMAKE_INSTALL_PREFIX="C:/Program Files (x86)/MuscleWrapping2" `
  -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreadedDLL" `
  -DENABLE_OPENMP=ON `
  -DMW2_CXX_STANDARD=20 `
  -DOVERRIDE_INSTALL_PREFIX=ON `
  -DPIPELINE_INSTALL_TOOLS=ON `
  -G "Visual Studio 17 2022"
```

**Build (Release configuration with automatic parallel jobs):**
```bash
cmake --build src/MW2/Build --config Release -j
```

The `-j` flag without an argument automatically uses all available CPU cores for parallel compilation.

#### 3. Verify the Build

After successful compilation, verify that `OsimMuscleGeneratorTool.dll` exists in the build directory:

```bash
ls src/MW2/Build/bin/
```

The pipeline's pre-flight checks will automatically detect the MW2 build at `paths.muscle_wrapping_path` (configured in `config/config.json`, default: `src/MW2/Build`).

### Python Libraries (env_base)

Key dependencies managed via `config/env_base.yaml`:

| Library | Purpose |
|---|---|
| `snakemake` | Pipeline orchestration |
| `nibabel`, `SimpleITK` | NIfTI and DICOM I/O |
| `pydicom` | DICOM file parsing |
| `numpy`, `scipy` | Numerical computation, morphological operations |
| `scikit-learn` | Metrics (RMSE, Pearson correlation) |
| `pandas` | Tabular data processing (benchmarks, statistics) |
| `matplotlib`, `seaborn` | Plot generation and PDF reports |
| `rich`, `colorama` | Formatted console output |
| `psutil` | System detection (GPU, processes) |
| `pyvista`, `trimesh`, `open3d` | 3D mesh processing (atlas registration) |
| `probreg`, `pycpd` | Point-cloud registration (CPD algorithm) |
| `pymeshlab` | Mesh merging and splitting |

### Conda Environments

The pipeline manages several isolated Conda environments:

| Environment | Config file | Purpose |
|---|---|---|
| `msk_base` | `config/env_base.yaml` | Snakemake + core Python scripts |
| `msk_totalseg_cpu` | `config/env_totalseg_cpu.yaml` | TotalSegmentator (CPU) |
| `msk_totalseg_gpu` | `config/env_totalseg_gpu.yaml` | TotalSegmentator (GPU + CUDA) |
| `msk_musclemap_cpu` | `config/env_musclemap_cpu.yaml` | MuscleMap (CPU, PyTorch) |
| `msk_musclemap_gpu` | `config/env_musclemap_gpu.yaml` | MuscleMap (GPU, PyTorch + CUDA 12.1) |

### C++ Components

Two C++ utilities compiled with CMake and linked against VTK 9.0+:

- **mask_to_mesh** — converts NIfTI masks to surface meshes (Flying Edges extraction, Windowed-sinc smoothing, quadric decimation)
- **extract_attachments** — extracts muscle-to-bone attachment regions via `vtkStaticCellLocator` proximity queries when **`proximity`** method is selected 

## Project Structure

```
msk-pipeline/
├── config/
│   ├── config.json                # Main configuration (paths, parameters, labels)
│   ├── muscle_topology.json       # Muscle-to-bone attachment definitions
│   ├── env_base.yaml              # Conda env: Snakemake + core Python
│   ├── env_totalseg_cpu.yaml      # Conda env: TotalSegmentator (CPU)
│   ├── env_totalseg_gpu.yaml      # Conda env: TotalSegmentator (GPU)
│   ├── env_musclemap_cpu.yaml     # Conda env: MuscleMap (CPU)
│   └── env_musclemap_gpu.yaml     # Conda env: MuscleMap (GPU)
├── data/
│   ├── input/                     # Default input directory
│       ├── landmarks/             # User provided landmarks of muscles
│       ├── mri/             
│       ├── ct/             
│       ├── landmarks/             # User provided landmarks of muscles
│       ├── data_download.txt      # download data foldeer from this URL!!!
│   ├── output/                    # Pipeline outputs (run_1, run_2, ...)
│   ├── opensim/                   # Motion files (.mot) and activations (.sto)
│   └── Experiments/               # LHDL reference datasets
├── envs/                          # Environment directories
├── runner/                        # Pipeline orchestration & pre-flight checks
│   ├── __main__.py                # CLI entry point (python -m runner)
│   ├── preflight.py               # Pre-flight check orchestrator
│   ├── pipeline.py                # Snakemake launcher, run ID management
│   ├── config_io.py               # JSON config load / save
│   ├── constants.py               # Path constants and defaults
│   ├── system.py                  # GPU detection, process management
│   ├── ui.py                      # Rich console output helpers
│   ├── micromamba.py              # Conda environment management
│   ├── external_tools.py          # External dependency checks & compilation
│   ├── matlab.py                  # MATLAB + OpenSim API setup
│   └── musclemap.py               # MuscleMap repository setup
├── src/
│   ├── python/
│   │   ├── clean_masks.py                          # Mask post-processing
│   │   ├── split_mesh.py                           # Calling mesh splitting
│   │   ├── merge_mesh.py                           # Calling mesh merging
│   │   ├── mesh_ops.py                             # Mesh merging & splitting algorithms
│   │   ├── subtract_bone_from_muscle.py            # Subtraction algorithm
│   │   ├── generate_statistics.py                  # Pipeline vs LHDL comparison
│   │   ├── generate_benchmark_plots.py             # Benchmark visualisation
│   │   ├── converting_formats/
│   │   │   ├── CT_dicom_to_nifti.py                # DICOM → NIfTI conversion
│   │   │   └── CT_raw_to_nifti.py                  # RAW → NIfTI conversion
│   │   ├── bones_segmentation/
│   │   │   └── run_totalsegmentator.py             # TotalSegmentator wrapper
│   │   ├── muscles_segmentation_extraction/
│   │   │   ├── run_musclemap.py                    # MuscleMap wrapper
│   │   │   └── extract_muscle_masks.py             # Multi-label → individual masks
│   │   ├── staple_processing/
│   │   │   ├── process_staple.py                   # STAPLE execution via MATLAB
│   │   │   ├── hip_model.m                         # MATLAB script for hip model
│   │   │   └── add_sacrum_mesh.py                  # Sacrum integration into .osim
│   │   └── extract_attachments_runner/
│   │       ├── generate_attachment_xml.py          # XML config generation
│   │       └── map_lhdl_attachments.py             # Atlas registration (CPD)
│   └── cpp/
│       ├── mask_to_mesh/                           # NIfTI → STL/OBJ (C++/VTK)
│       │   └── src/
│       │       ├── main.cpp
│       │       ├── MeshConverter.cpp
│       │       |── MeshConverter.h
│       |       └── CMakeLists.txt
│       └── extract_attachments/                    # Muscle-bone proximity (C++/VTK)
│           └── src/
│               ├── main.cpp
│               ├── AttachmentExtractor.h
│               ├── AttachmentExtractor.cpp
│               └── CMakeLists.txt
├── workflow/
│   ├── Snakefile                  # Top-level orchestrator (includes rule modules)
│   └── rules/
│       ├── common.smk             # Shared constants, helpers, config derivation
│       ├── input.smk              # Input format detection & normalisation
│       ├── segmentation.smk       # TotalSegmentator + MuscleMap rules
│       ├── preprocessing.smk      # Per-file mask cleaning rules
│       ├── meshing.smk            # Mask-to-mesh, renaming, merging
│       ├── modeling.smk           # STAPLE, attachments, muscle wrapping
│       └── statistics.smk         # Post-run statistics & benchmark reports
├── requirements.txt
└── README.md
```

## Input

The pipeline accepts three input formats. By default, the pipeline features an **Auto-Detection mechanism**. If you place your data into the default input directory (`data/input/`) and run the pipeline without arguments, it will automatically detect and process the first valid scan it finds.

The auto-detection scans for formats in the following priority:
1. **NIfTI** (`.nii` / `.nii.gz`) — a single CT or MRI volume.
2. **RAW** — a flat binary volume (`.raw`). *Note: Must be accompanied by a `coordinates.txt` file containing per-slice Z coordinates.*
3. **DICOM** — a directory of `.dcm` files (or standard DICOM files without extensions).

Alternatively, you can bypass auto-detection and specify a file diTherectly using the `--input` flag which is considered a better option. **The `--input` flag is the RECOMMENDED METHOD!!!**

## Pipeline Steps

### Step 0: Input Preparation
Detects the input format and converts DICOM or RAW data to standardised NIfTI
(`.nii.gz`). NIfTI inputs are used as-is. 

### Step 1: Bone Segmentation
Runs [TotalSegmentator](https://github.com/wasserth/TotalSegmentator) to
produce multi-label bone masks (pelvis, femur, tibia, fibula, sacrum).
Supports both CT and MR modalities, GPU or CPU. In `config/config.json` user needs to change "totalsegmentator" {"model" = "ct" or "mr"} based on the input file.

### Step 2: Muscle Segmentation
Runs [MuscleMap](https://github.com/MuscleMap/MuscleMap) or [TotalSegmentator](https://https://github.com/wasserth/TotalSegmentator) to produce a
multi-label segmentation of lower-limb muscle groups based on the "muscle_segmentator" in `config/config.json` (Options: musclemap or totalsegmentor).
Bone volumes are subtracted from muscle masks to prevent
physical overlap.

If [TotalSegmentator](https://https://github.com/wasserth/TotalSegmentator) is chosen, the masks of Gluteus Maximus/Medius/Minimus and Iliopsoas muscles are genereted, because they are the only muscles around hip that can be uniquely segmentated via this tool.

### Step 3: Muscle Mask Extraction
Splits the multi-label MuscleMap output into individual binary masks using the
label mapping defined in `config/config.json`.

### Step 4: Mask Cleaning
Per-file post-processing of segmentation masks:
- Binarisation with configurable threshold
- Connected-component analysis and small-component removal
- Morphological closing and opening
- Iterative hole filling

### Step 5: Mesh Generation
Converts cleaned NIfTI masks to surface meshes using a C++ binary built on VTK:
- Flying Edges isosurface extraction
- Windowed-sinc smoothing (configurable iterations and passband)
- Quadric edge-collapse decimation
- Topology cleaning and triangulation
- Bones → `.stl`, muscles → `.obj`

### Step 6: Mesh Renaming and Merging
- Renames bone meshes to STAPLE-compatible names (e.g. `hip_left` → `pelvis_no_sacrum`)
- Merges pelvis halves and splits composite meshes (tibia/fibula) using trimesh

### Step 7: OpenSim Bone Model (MSK-STAPLE)
Invokes MATLAB to run the MSK-STAPLE toolbox, which computes anatomical and
joint coordinate systems, assigns mass properties, and generates
`bone_model.osim`.

### Step 8: Attachment Extraction
Three methods available (configured via `config.json` in "attachment_extraction/method"):
- **`proximity_based`** — C++ binary uses `vtkStaticCellLocator` to find muscle vertices within a configurable distance threshold of each bone surface; outputs ordered contour points as VTK point clouds.
- **`atlas_based`** — maps reference LHDL attachment areas onto patient-specific bone geometry using Coherent Point Drift (CPD) registration.
- **`own_attachments`** — copies user-supplied `.vtk` attachment files directly from `data/input/landmarks` folder.

### Step 8.1: User provided attachments
If the `own_attachments` method is selected, the names of attachment files needs to follow names from `config/muscle_topology.json` file (such as **GluteusMaximus**) and have the **_Ori** (Origin) and **_Ins** (Insertion) sufixes.

### Step 9: XML Configuration
Generates `setup_MuscleGeneratorTool.xml` linking the bone model, muscle meshes,
attachment VTKs, motion file, and fibre-generation algorithm
(`Luca2018viaPoints` or `Havlicek2024XPBDAlgorithm`) which can be modified via "muscle_wrapping/kinematics_algorithm" option in file `config/config.json` .

### Step 10: Muscle Wrapping
Runs OpenSim's `opensim-cmd` with `OsimMuscleGeneratorTool.dll`, from the MW2 build path, to produce the
final `pipeline_model.osim` with wrapped and deformed muscle fibres.

### Step 11: Statistical Evaluation
Compares pipeline output kinematics against LHDL reference datasets:
- Per-muscle RMSE and Pearson correlation
- Relative error metrics (% of ground-truth mean and range)
- PDF report with comparison plots
- CSV summary table
- Optional benchmark report (runtime, RAM, CPU, disk I/O per Snakemake rule)

## Configuration

All pipeline parameters are in `config/config.json`:

| Section | Key | Description |
|---|---|---|
| `paths.input_dir` | `data/input` | Default input directory |
| `paths.output_dir` | `data/output` | Output base directory |
| `paths.muscle_wrapping_path` | `src/MW2/Build` | Path to Muscle Wrapping 2.0 |
| `paths.staple_path` | `src/STAPLE` | Path to MSK-STAPLE toolbox |
| `totalsegmentator.device` | `gpu` / `cpu` | Segmentation device |
| `totalsegmentator.model` | `ct` / `mr` | Imaging modality |
| `totalsegmentator.fast` | `true` / `false` | Fast mode (lower resolution) |
| `bone_preprocessing.*` | | Mask cleaning parameters for bones |
| `muscle_preprocessing.*` | | Mask cleaning parameters for muscles |
| `bone_to_mesh.*` | | Smoothing parameters for bone meshes |
| `muscle_to_mesh.*` | | Smoothing parameters for muscle meshes |
| `attachment_extraction.method` | `proximity_based` / `atlas_based` / `own_attachments` | Attachment extraction strategy |
| `attachment_extraction.threshold_mm` | `2.0` | Distance threshold (proximity method) |
| `attachment_extraction.clip_fraction` | `0.25` | Clip fraction (proximity method) |
| `muscle_wrapping.kinematics_algorithm` | `luca` / `havlicek` | Fibre generation algorithm |
| `muscle_map.labels` | | Muscle name → label ID mapping |
| `user_settings.enable_benchmarking` | `true` / `false` | Generate benchmark reports |

Muscle-to-bone attachment topology is defined in `config/muscle_topology.json`.

## Output Structure

Each pipeline run produces a sequentially numbered directory:

```
data/output/run_N/
├── bone_masks/              # Individual bone masks (.nii.gz)
├── muscle_masks/            # Individual muscle masks (.nii.gz)
├── bone_models/             # Bone surface meshes (.stl)
├── muscle_models/           # Muscle surface meshes (.obj)
├── bones_STAPLE/            # Renamed/merged meshes for STAPLE
├── Geometry/                # Final bone geometries (.obj) for OpenSim
├── attachments/             # Muscle attachment VTK files
├── bone_model.osim          # Bone-only OpenSim model
├── setup_MuscleGeneratorTool.xml
├── pipeline_model.osim      # Final model with wrapped muscles
├── Experiments/             # Muscle fibre length data (.sto)
├── statistics/              # Comparison reports and benchmarks
│   ├── Kinematika_Report.pdf
│   ├── Celkove_Statistiky_s_Procenty.csv
│   ├── Benchmark_Report.pdf
│   └── summary_metadata.txt
└── benchmarks/              # Per-rule Snakemake benchmark files

```

And reports folder:
```
data/output/reports/run_N/
├── dag.pdf
├── rulegraph.pdf
├── snakemake_report.html
├── summary.txt
```

## Usage

You can launch the pipeline in fully automatic mode or specify your inputs explicitly:

```bash
# 1. Automatic Mode
# Automatically scans data/input/ for NIfTI, RAW, or DICOM files and processes the first one found.
python -m runner

# 2. Explicit Input (NIfTI or RAW)
# Run with a specific input file, ignoring the data/input/ directory.
# RECOMMENDED!!!!!
python -m runner --input /path/to/patient_ct {.nii.gz/.raw}

# 3. Explicit Input (DICOM)
# Run with a specific directory containing DICOM slices.
python -m runner --input /path/to/dicom_folder/
```

The runner will interactively prompt for any missing settings (input format,
number of CPU cores, whether to generate reports) and persist them for
subsequent runs.

## Algorithms and Methods

- **Bone segmentation**: TotalSegmentator (nnU-Net-based, multi-label, CT/MR)
- **MusclaMap muscle segmentation**: MuscleMap (deep-learning, lower-limb muscles)
- **TotalSegmentator muscle segmentation**: Totalsegmentator (nnU-Net-based, hip muscles)
- **Surface reconstruction**: Flying Edges isosurface extraction (VTK)
- **Mesh smoothing**: Windowed-sinc (Taubin) smoothing — shrinkage-free
- **Mesh decimation**: Quadric edge-collapse decimation
- **Bone modelling**: MSK-STAPLE (automatic ACS/JCS from bone geometry)
- **Attachment extraction**: vtkStaticCellLocator proximity + contour extraction, or CPD atlas registration or user provided
- **Muscle simulation**: Position Based Dynamics / XPBD (Muscle Wrapping 2.0)
- **Statistical validation**: RMSE, Pearson correlation against LHDL reference
