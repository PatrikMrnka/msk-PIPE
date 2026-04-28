# C++ Tools Documentation

## Overview

This directory contains two main C++ tools for the MSK pipeline:
- **mask_to_mesh**: Converts binary NIfTI segmentation masks to surface meshes (STL/OBJ format)
- **extract_attachments**: Extracts muscle-to-bone attachment points via proximity queries on dense meshes

Both tools leverage VTK (Visualization Toolkit) for efficient 3D mesh processing.

## Project Structure

```
src/cpp/
├── CMakeLists.txt              # Top-level CMake configuration
├── mask_to_mesh/src/           # Mask-to-mesh conversion tool
│   ├── CMakeLists.txt
│   └── main.cpp
├── extract_attachments/src/    # Attachment point extraction tool
│   ├── CMakeLists.txt
│   ├── main.cpp
│   ├── AttachmentExtractor.h
│   └── AttachmentExtractor.cpp
└── DOCUMENTATION.md            # This file
```

## Prerequisites
- CMake 3.21 or later
- C++17 compiler (MSVC on Windows)
- VTK 9.0+ with development headers


Output executables will be placed in `build/bin/Release/`:
- `mask_to_mesh.exe`
- `extract_attachments.exe`

## Tool 1: mask_to_mesh

### Purpose
Converts binary NIfTI segmentation masks into surface meshes (STL or OBJ format).

### Usage

```bash
mask_to_mesh --input-dir <path> --output-dir <dir> [options]
```

### Options
- `--input-dir <path>`: Single NIfTI file or directory of NIfTI files
- `--output-dir <dir>`: Output directory for generated meshes
- `--smooth_iters N`: Windowed-sinc smoothing iterations (default: 30)
- `--passband F`: Passband for smoothing filter (default: 0.01, range: 0.005–0.02)
- `--format stl|obj`: Output format - STL or OBJ (default: stl)

### Example

```bash
mask_to_mesh --input-dir ./masks/ --output-dir ./meshes/ --smooth_iters 30 --format stl
```

### Algorithm
1. **Read NIfTI**: Load binary mask volume
2. **Extract Surface**: Use Flying Edges (O(N)) algorithm for isosurface extraction
3. **Smooth & Clean**: Apply windowed-sinc smoothing and mesh cleaning
4. **Triangulate**: Ensure all faces are triangles
5. **Write Output**: Save as STL (binary) or OBJ format

## Tool 2: extract_attachments

### Purpose
Extracts muscle attachment points by finding regions where muscle meshes come within a specified distance of bone surfaces.

### Usage

```bash
extract_attachments <bone.poly> <threshold_mm> <clip_fraction> <muscle1.poly> <out1.vtk> [<muscle2.poly> <out2.vtk> ...]
```

### Arguments
- `bone.poly`: Bone mesh (.obj or .stl) – loaded once and reused for all muscles
- `threshold_mm`: Maximum distance in mm for attachment detection (e.g., 3.0)
- `clip_fraction`: Fraction of muscle length to keep at each end, middle removed (0.0–0.5)
- `muscleN.poly`: Muscle mesh (.obj or .stl) – one or more pairs
- `outN.vtk`: Output attachment point cloud (.vtk) for the paired muscle

### Example

```bash
extract_attachments pelvis.obj 3.0 0.25 iliacus.obj iliacus_ori.vtk psoas.obj psoas_ori.vtk
```

### Output Format
Legacy ASCII VTK 3.0 format, compatible with OpenSim MuscleGeneratorTool:
- POINTS section with 3D coordinates
- VERTICES cell data
- SCALARS bit array marking attachment vertices

### Algorithm

The extraction uses an optimized O(M) proximity-based approach where M is the number of muscle vertices:

1. **Load Bone**: Read mesh and build `vtkStaticCellLocator` for O(1) nearest-point queries
2. **Load Muscle**: Load muscle mesh for testing
3. **Distance Computation**: Compute distance from each muscle vertex to the nearest bone surface
4. **Clipping**: Keep only mesh regions within the threshold distance
5. **Belly Cutout**: Remove the middle section using a Z-axis aligned box clip based on `clip_fraction`
6. **Boundary Extraction**: Extract polyline contours of the clipped attachment patch
7. **Contour Selection**: Choose the longest continuous contour
8. **Smoothing & Resampling**: Apply spline smoothing with uniform resampling (~30 points)
9. **Projection**: Project all contour points onto the bone surface for accuracy
10. **Export**: Write attachment points to VTK format

### Optimization Notes
- **Single Bone Load**: The bone mesh and locator are built once, then reused for all muscles
- **O(M) Complexity**: Each muscle query is O(M) where M is the number of muscle vertices
- **Batch Processing**: Process multiple muscles efficiently without re-building the locator

## Dependencies

### VTK Components
- `vtkSmartPointer`: Memory management for VTK objects
- `vtkPolyData`: Mesh representation
- `vtkStaticCellLocator`: Spatial acceleration structure for proximity queries
- `vtkClipPolyData`: Clipping operations
- `vtkFeatureEdges`: Boundary extraction
- `vtkSplineFilter`: Smooth curve interpolation
- `vtkImageData`: Volume/raster data
- `vtkFlyingEdges3D`: Fast isosurface extraction
- `vtkWindowedSincPolyDataFilter`: Mesh smoothing
- `vtkNIFTIImageReader`: NIfTI file I/O
- `vtkSTLWriter/vtkOBJWriter`: Mesh file output

## Performance Characteristics

### mask_to_mesh
- **Time Complexity**: O(N log N) for isosurface extraction, O(N) for smoothing
- **Space Complexity**: O(N) for volume and surface representation
- **Typical Runtime**: 1–5 seconds per mask (depends on volume resolution and smoothing)

### extract_attachments
- **Per-Muscle Time**: O(M) where M = muscle vertex count
- **Locator Build**: O(N log N) amortized over all muscles, where N = bone cells
- **Typical Runtime**: 10–100 ms per muscle (after initial bone load)

## Error Handling

Both tools provide informative error messages with `[ERROR]`, `[WARNING]`, and `[INFO]` prefixes for debugging.

### Common Issues

**mask_to_mesh**:
- Missing NIfTI files: Check input path and file extensions (.nii, .nii.gz)
- Smoothing artifacts: Adjust `--passband` (smaller = more aggressive smoothing)

**extract_attachments**:
- No attachment points found: Increase `--threshold_mm` or check mesh alignment
- Large clip values: Ensure `clip_fraction` is in (0.0, 0.5) range

## Code Organization

### Module Responsibilities

**mask_to_mesh**:
- ✓ Reading NIfTI segmentation data
- ✓ Isosurface extraction
- ✓ Mesh smoothing and cleaning
- ✓ Writing STL/OBJ output
- ✗ File naming/organization (handled by workflow)

**extract_attachments** (AttachmentExtractor class):
- ✓ Loading and caching bone meshes
- ✓ Building spatial acceleration structures
- ✓ Computing vertex-to-surface distances
- ✓ Clipping and boundary extraction
- ✓ Contour smoothing via splines
- ✓ VTK file export
- ✗ File organization or batch scheduling (handled by workflow)

