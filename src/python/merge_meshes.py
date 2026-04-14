"""
merge_meshes.py -- Mesh post-processing: merging, splitting, and copying.

Post-processes meshes produced by the mask-to-mesh conversion step:
  - Merges pelvis (hip_left + hip_right) into pelvis_no_sacrum.stl
  - Splits tibia+fibula, patella, and phalanges_feet into left/right
  - Copies femur_l.stl and femur_r.stl to the output folder
  - Optionally merges all *_l + *_r pairs (--merge-lr-pairs flag)
"""

import os
import sys
import argparse
from pathlib import Path
import pymeshlab
import shutil

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step


def merge_left_right_pairs(input_dir, output_dir, extensions=(".stl", ".obj")):
    """Merge all *_l + *_r mesh pairs into a single mesh without a side suffix.

    Example:
        iliacus_l.stl + iliacus_r.stl -> iliacus.stl
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    pair_map = {}
    for p in input_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in extensions:
            continue

        stem = p.stem
        low = stem.lower()
        if low.endswith("_l"):
            key = (stem[:-2], p.suffix.lower())
            pair_map.setdefault(key, {})["l"] = p
        elif low.endswith("_r"):
            key = (stem[:-2], p.suffix.lower())
            pair_map.setdefault(key, {})["r"] = p

    merged_count = 0
    for (base, ext), sides in sorted(pair_map.items()):
        left = sides.get("l")
        right = sides.get("r")
        if not left or not right:
            continue

        out_file = output_dir / f"{base}{ext}"
        ok = merge_meshes([str(left), str(right)], str(out_file))
        if ok:
            merged_count += 1
            print_info(f"Merged pair -> {out_file.name}")

    print_success(f"Merged {merged_count} left/right pairs.")
    return merged_count


def merge_meshes(input_files, output_file):
    """Merge multiple STL/OBJ files into a single mesh.

    Args:
        input_files: List of paths to input mesh files.
        output_file: Path to the output merged mesh file.

    Returns:
        True if the merge succeeded, False otherwise.
    """
    missing = [p for p in input_files if not os.path.exists(p)]
    if missing:
        print_warning("Missing input files, skipping:")
        for m in missing:
            print_warning(f"  - {m}")
        return False

    print_step("\n--- MERGING MESHES ---")
    print_info("Inputs:")
    for f in input_files:
        print_info(f"  - {f}")

    print_info(f"Output:\n  - {output_file}")

    ms = pymeshlab.MeshSet()
    for path in input_files:
        print_step(f"Loading '{path}'...")
        ms.load_new_mesh(path)

    print_info(f"Mesh count before merge: {ms.number_meshes()}")
    print_step("Merging meshes (generate_by_merging_visible_meshes)...")
    ms.apply_filter("generate_by_merging_visible_meshes")
    print_info(f"Mesh count after merge: {ms.number_meshes()}")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print_step(f"Saving merged mesh to '{output_file}'...")
    ms.save_current_mesh(output_file)

    print_success("Done.")
    return True


def split_into_left_right_components(input_file, left_out, right_out):
    """Split a mesh into left and right components based on X-coordinate position.

    Algorithm:
      1. Load the input mesh and split it into connected components.
      2. Remove the original (full) mesh from the candidate list.
      3. Compute the mean X coordinate for each component and use the midpoint
         of the X range to classify components as left (X < mid) or right
         (X >= mid).
      4. Save each side into temporary files and merge them into *left_out*
         and *right_out*.

    Args:
        input_file: Path to the input mesh containing merged bone parts.
        left_out: Destination path for the left-side mesh.
        right_out: Destination path for the right-side mesh.

    Returns:
        True if both sides were generated successfully, False otherwise.
    """
    ms = pymeshlab.MeshSet()
    try:
        ms.load_new_mesh(input_file)
        print_info(f"Loaded for splitting: '{input_file}'")
    except Exception as e:
        print_error(f"Error loading '{input_file}': {e}")
        return False

    # Remember the original mesh size so we can ignore the "full" copy after split.
    orig_vcount = ms.current_mesh().vertex_number()
    orig_mesh_count = ms.number_meshes()

    print_step("Splitting into connected components")
    ms.apply_filter("generate_splitting_by_connected_components")
    total_count = ms.number_meshes()
    print_info(f"Mesh count after split: {total_count}.")

    if total_count <= orig_mesh_count:
        print_warning("Split produced no new components.")
        return False

    # Build a list of component indices, ignoring the original full mesh.
    candidate_indices = []
    for i in range(total_count):
        ms.set_current_mesh(i)
        vnum = ms.current_mesh().vertex_number()
        if vnum == orig_vcount and i < orig_mesh_count:
            continue  # likely the original unprocessed mesh
        candidate_indices.append(i)

    print_info(f"Found {len(candidate_indices)} components after filtering the original.")

    if len(candidate_indices) < 2:
        print_warning("Not enough components to split into left/right.")
        return False

    # Compute the mean X coordinate for each component.
    comps = []
    for i in candidate_indices:
        ms.set_current_mesh(i)
        V = ms.current_mesh().vertex_matrix()
        if V.size == 0:
            continue
        cx = float(V[:, 0].mean())
        comps.append((i, cx))

    if len(comps) < 2:
        print_warning("Cannot compute component centres.")
        return False

    xs = [cx for _, cx in comps]
    mid = (min(xs) + max(xs)) / 2.0

    left_ids = [i for i, cx in comps if cx < mid]
    right_ids = [i for i, cx in comps if cx >= mid]

    print_info(f"Left side (component indices): {left_ids}")
    print_info(f"Right side (component indices): {right_ids}")

    # Save individual components to temporary files, then merge per side.
    os.makedirs(os.path.dirname(left_out), exist_ok=True)
    tmp_dir = os.path.join(os.path.dirname(left_out), "_tmp_components")
    os.makedirs(tmp_dir, exist_ok=True)

    left_files = []
    right_files = []

    for i in left_ids:
        ms.set_current_mesh(i)
        p = os.path.join(tmp_dir, f"left_comp_{i}.stl")
        ms.save_current_mesh(p)
        left_files.append(p)

    for i in right_ids:
        ms.set_current_mesh(i)
        p = os.path.join(tmp_dir, f"right_comp_{i}.stl")
        ms.save_current_mesh(p)
        right_files.append(p)

    ok_left = merge_meshes(left_files, left_out) if left_files else False
    ok_right = merge_meshes(right_files, right_out) if right_files else False

    # Clean up temporary component files.
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return bool(ok_left and ok_right)


def main():
    """CLI tool for mesh post-processing.

    Post-processes meshes from mask-to-mesh conversion:
      - Merges pelvis (hip_left + hip_right) into pelvis_no_sacrum.stl
      - Splits tibia+fibula, patella, and phalanges_feet into left/right
      - Copies femur_l.stl and femur_r.stl to the output folder
    """
    parser = argparse.ArgumentParser(
        description="Mesh post-processing for Snakemake pipeline."
    )
    parser.add_argument(
        "--input-dir", type=str, required=True,
        help="Input folder containing .stl files from mask-to-mesh conversion",
    )
    parser.add_argument(
        "--output-dir", type=str, required=True,
        help="Output folder for processed mesh files",
    )
    parser.add_argument(
        "--merge-lr-pairs", action="store_true",
        help="Merge all *_l + *_r pairs to single meshes "
             "(e.g. iliacus_l + iliacus_r -> iliacus).",
    )
    args = parser.parse_args()

    data_dir = Path(args.input_dir).resolve()
    result_dir = Path(args.output_dir).resolve()

    if not data_dir.exists():
        print_error(f"Input directory does not exist: {data_dir}")
        raise SystemExit(1)

    os.makedirs(result_dir, exist_ok=True)

    if args.merge_lr_pairs:
        merge_left_right_pairs(data_dir, result_dir)
        print_success("\nMesh post-processing completed successfully.")
        return 0

    sacrum = data_dir / "sacrum.stl"
    if sacrum.exists():
        pelvis_out = result_dir / "sacrum.stl"
        merge_meshes([str(sacrum)], str(pelvis_out))
    else:
        print_warning("Skipping sacrum merge: sacrum.stl not found")

    # 1) Pelvis: hip_left + hip_right -> pelvis_no_sacrum.stl
    hip_left = data_dir / "hip_left.stl"
    hip_right = data_dir / "hip_right.stl"
    if hip_left.exists() and hip_right.exists():
        pelvis_out = result_dir / "pelvis_no_sacrum.stl"
        merge_meshes([str(hip_left), str(hip_right)], str(pelvis_out))
    else:
        print_warning("Skipping pelvis merge: missing hip_left.stl or hip_right.stl")

    # 2) Tibia + Fibula -> tibia_l, tibia_r
    tibia_all = data_dir / "tibia.stl"
    fibula_all = data_dir / "fibula.stl"
    if tibia_all.exists() and fibula_all.exists():
        temp_merged = result_dir / "tibia_fibula_temp.stl"
        if merge_meshes([str(tibia_all), str(fibula_all)], str(temp_merged)):
            out_l = result_dir / "tibia_l.stl"
            out_r = result_dir / "tibia_r.stl"
            if split_into_left_right_components(
                str(temp_merged), str(out_l), str(out_r)
            ):
                try:
                    os.remove(temp_merged)
                    print_info(f"Cleaned temporary file: {temp_merged}")
                except OSError:
                    pass
    else:
        print_warning("Skipping tibia/fibula split: missing tibia.stl or fibula.stl")

    # 3) Patella -> patella_l, patella_r
    patella_all = data_dir / "patella.stl"
    if patella_all.exists():
        temp_merged = result_dir / "patella_temp.stl"
        if merge_meshes([str(patella_all)], str(temp_merged)):
            out_l = result_dir / "patella_l.stl"
            out_r = result_dir / "patella_r.stl"
            if split_into_left_right_components(
                str(temp_merged), str(out_l), str(out_r)
            ):
                try:
                    os.remove(temp_merged)
                    print_info(f"Cleaned temporary file: {temp_merged}")
                except OSError:
                    pass
    else:
        print_warning("Skipping patella split: patella.stl not found")

    # 4) Phalanges_feet -> toes_l, toes_r
    phalanges_all = data_dir / "phalanges_feet.stl"
    if phalanges_all.exists():
        temp_merged = result_dir / "phalanges_feet_temp.stl"
        if merge_meshes([str(phalanges_all)], str(temp_merged)):
            out_l = result_dir / "toes_l.stl"
            out_r = result_dir / "toes_r.stl"
            if split_into_left_right_components(
                str(temp_merged), str(out_l), str(out_r)
            ):
                try:
                    os.remove(temp_merged)
                    print_info(f"Cleaned temporary file: {temp_merged}")
                except OSError:
                    pass
    else:
        print_warning("Skipping phalanges split: phalanges_feet.stl not found")

    # 5) Copy femur files to output directory.
    for bone in ["femur_l.stl", "femur_r.stl"]:
        src = data_dir / bone
        dst = result_dir / bone
        if src.exists():
            try:
                shutil.copy2(src, dst)
                print_success(f"Copied '{src}' to '{dst}'")
            except OSError as e:
                print_error(f"Error copying '{src}' to '{dst}': {e}")
        else:
            print_warning(f"Skipping {bone}: not found in input directory")

    print_success("\nMesh post-processing completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
