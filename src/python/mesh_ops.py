"""
mesh_ops.py
~~~~~~~~~~~
Shared mesh post-processing operations.

Contains utility functions for merging and splitting meshes used
by other scripts in the pipeline.
"""

import os
import sys
from pathlib import Path
import trimesh
import numpy as np

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import print_error, print_info, print_step, print_success, print_warning


def merge_meshes(input_files, output_file):
    """Merge multiple STL/OBJ files into a single mesh."""
    missing = [p for p in input_files if not os.path.exists(p)]
    if missing:
        print_warning("Missing input files, skipping:")
        for m in missing:
            print_warning(f"  - {m}")
        return False

    print_step("\n--- MERGING MESHES ---")
    
    loaded_meshes = []
    for path in input_files:
        print_info(f"Loading '{path}'...")
        try:
            loaded_meshes.append(trimesh.load_mesh(path))
        except Exception as e:
            print_error(f"Failed to load {path}: {e}")
            return False

    if not loaded_meshes:
        return False

    print_step("Concatenating meshes in memory...")
    merged_mesh = trimesh.util.concatenate(loaded_meshes)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print_step(f"Saving merged mesh to '{output_file}'...")
    merged_mesh.export(output_file)

    print_success("Done.")
    return True


def split_into_left_right_components(input_file, left_out, right_out):
    """Split a mesh into left and right components based on X position."""
    try:
        print_info(f"Loaded for splitting: '{input_file}'")
        mesh = trimesh.load_mesh(input_file)
    except Exception as exc:
        print_error(f"Error loading '{input_file}': {exc}")
        return False

    print_step("Splitting into connected components...")
    # splits the mesh into a list of separate trimesh objects, each representing a connected component
    components = mesh.split(only_watertight=False)
    
    print_info(f"Mesh count after split: {len(components)}.")

    if len(components) < 2:
        print_warning("Not enough components to split into left/right.")
        return False

    # calculate the X coordinate of the centroid of each component to determine left vs right
    centroids_x = [comp.centroid[0] for comp in components]
    midpoint = (min(centroids_x) + max(centroids_x)) / 2.0

    left_meshes = []
    right_meshes = []

    for comp, cx in zip(components, centroids_x):
        if cx < midpoint:
            left_meshes.append(comp)
        else:
            right_meshes.append(comp)

    print_info(f"Left side components: {len(left_meshes)}")
    print_info(f"Right side components: {len(right_meshes)}")

    # save the left side
    if left_meshes:
        os.makedirs(os.path.dirname(left_out), exist_ok=True)
        trimesh.util.concatenate(left_meshes).export(left_out)
        
    # save the right side
    if right_meshes:
        os.makedirs(os.path.dirname(right_out), exist_ok=True)
        trimesh.util.concatenate(right_meshes).export(right_out)

    return bool(left_meshes and right_meshes)