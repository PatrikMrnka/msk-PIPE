import os
import argparse
from pathlib import Path
import pymeshlab
import shutil
import sys


def merge_left_right_pairs(input_dir, output_dir, extensions=(".stl", ".obj")):
    """Merge all *_l + *_r mesh pairs into a single mesh without side suffix.

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
            print(f"Merged pair -> {out_file.name}")

    print(f"Merged {merged_count} left/right pairs.")
    return merged_count

def merge_meshes(input_files, output_file):
    """Sloučí více STL souborů do jednoho.

    Args:
        input_files (list): Seznam cest k vstupním STL souborům.
        output_file (str): Cesta k výstupnímu STL souboru.

    Returns:
        bool: True pokud bylo sloučení úspěšné, jinak False.
    """
    
    missing = [p for p in input_files if not os.path.exists(p)]
   
    if missing:
        print("Chybí vstupní soubory, přeskočeno:")
        for m in missing:
            print(f"  - {m}")
        return False

    print("\n--- SLUČUJI SÍTĚ ---")
    print("Vstupy:")
    for f in input_files:
        print(f"  - {f}")

    print(f"Výstup:\n  - {output_file}")
    
    ms = pymeshlab.MeshSet()
    for path in input_files:
        print(f"Načítám '{path}'...")
        ms.load_new_mesh(path)

    print(f"Počet sítí v projektu před spojením: {ms.number_meshes()}")
    print("Spojuji sítě do jedné (generate_by_merging_visible_meshes)...")
    ms.apply_filter("generate_by_merging_visible_meshes")
    print(f"Počet sítí v projektu po spojení: {ms.number_meshes()}")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print(f"Ukládám spojenou síť do '{output_file}'...")
    ms.save_current_mesh(output_file)

    print("Hotovo.")
    return True


def split_into_left_right_components(input_file, left_out, right_out):
    """Rozdělí STL na komponenty a vytvoří samostatné výstupy pro levou/pravou stranu.

    Postup:
    - Načte `input_file` do MeshSetu a provede dělení na souvislé komponenty
      filtrem `generate_splitting_by_connected_components`.
    - Odstraní původní "full" mesh (identifikován stejným počtem vrcholů jako původní, v rámci původního počtu meshů).
    - Spočítá pro každou komponentu průměrnou X souřadnici a podle mediánu (středu rozsahu X) je rozdělí
      na levou (X < mid) a pravou (X >= mid) stranu.
    - Každou stranu uloží do dočasných STL a následně je sloučí pomocí `merge_meshes` do `left_out` a `right_out`.

    Parametry:
        input_file (str | Path): Vstupní STL se sloučenými kostmi/částmi.
        left_out (str | Path): Cílový STL pro levou stranu.
        right_out (str | Path): Cílový STL pro pravou stranu.

    Vrací:
        bool: True, pokud byly generovány obě strany (ať už i prázdné sady komponent vrátí False), jinak False.
    """
    ms = pymeshlab.MeshSet()
    try:
        ms.load_new_mesh(input_file)
        print(f"Načteno pro dělení: '{input_file}'")
    except Exception as e:
        print(f"Chyba při načítání '{input_file}': {e}")
        return False

    # Zapamatuj si velikost původního meshe pro ignorování "full" kopie po splitu
    orig_vcount = ms.current_mesh().vertex_number()
    orig_mesh_count = ms.number_meshes()

    print("Rozděluji na souvislé komponenty")
    ms.apply_filter("generate_splitting_by_connected_components")
    total_count = ms.number_meshes()
    print(f"Po splitu je v projektu {total_count} meshů.")

    if total_count <= orig_mesh_count:
        print("Split nevytvořil žádné nové komponenty.")
        return False

    # Sestav seznam indexů komponent a ignoruj původní 'full' mesh
    candidate_indices = []
    for i in range(total_count):
        ms.set_current_mesh(i)
        vnum = ms.current_mesh().vertex_number()
        if vnum == orig_vcount and i < orig_mesh_count:
            # pravděpodobně původní nezpracovaný mesh – přeskočit
            continue
        candidate_indices.append(i)

    print(f"Nalezeno {len(candidate_indices)} komponent po odfiltrování originálu.")

    if len(candidate_indices) < 2:
        print("Nedostatek komponent pro rozdělení na levou/pravou stranu.")
        return False

    # Získej průměrné X každé komponenty
    comps = []
    for i in candidate_indices:
        ms.set_current_mesh(i)
        V = ms.current_mesh().vertex_matrix()
        if V.size == 0:
            continue
        cx = float(V[:, 0].mean())
        comps.append((i, cx))

    if len(comps) < 2:
        print("Nelze spočítat středy komponent.")
        return False

    xs = [cx for _, cx in comps]
    mid = (min(xs) + max(xs)) / 2.0

    left_ids = [i for i, cx in comps if cx < mid]
    right_ids = [i for i, cx in comps if cx >= mid]

    print(f"Levá strana (indexy komponent): {left_ids}")
    print(f"Pravá strana (indexy komponent): {right_ids}")

    # Ulož jednotlivé komponenty do dočasných souborů a sluč je po stranách
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

    # Úklid dočasných komponent
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return bool(ok_left and ok_right)

def main():
    """CLI tool for mesh post-processing.

    Post-processes meshes from mask2stl conversion:
    - Merges pelvis (hip_left + hip_right) into pelvis_no_sacrum.stl
    - Splits tibia+fibula, patella, and phalanges_feet into left/right components
    - Copies femur_l.stl and femur_r.stl to output folder

    Outputs are saved to the specified --output directory.
    """
    parser = argparse.ArgumentParser(description="Mesh post-processing for Snakemake pipeline.")
    parser.add_argument("--input", type=str, required=True, help="Input folder containing .stl files from mask2stl conversion")
    parser.add_argument("--output", type=str, required=True, help="Output folder for processed mesh files")
    parser.add_argument(
        "--merge-lr-pairs",
        action="store_true",
        help="Merge all *_l + *_r pairs to single meshes (e.g., iliacus_l + iliacus_r -> iliacus).",
    )
    args = parser.parse_args()

    data_dir = Path(args.input).resolve()
    result_dir = Path(args.output).resolve()

    if not data_dir.exists():
        print(f"ERROR: Input directory does not exist: {data_dir}")
        raise SystemExit(1)

    os.makedirs(result_dir, exist_ok=True)

    if args.merge_lr_pairs:
        merge_left_right_pairs(data_dir, result_dir)
        print("\nMesh post-processing completed successfully.")
        return 0

    # 1) Pelvis: hip_left + hip_right -> pelvis_no_sacrum.stl (optional)
    hip_left = data_dir / "hip_left.stl"
    hip_right = data_dir / "hip_right.stl"
    if hip_left.exists() and hip_right.exists():
        pelvis_out = result_dir / "pelvis_no_sacrum.stl"
        merge_meshes([str(hip_left), str(hip_right)], str(pelvis_out))
    else:
        print(f"Skipping pelvis merge: missing hip_left.stl or hip_right.stl")

    # 2) Tibia + Fibula -> tibia_l, tibia_r (optional)
    tibia_all = data_dir / "tibia.stl"
    fibula_all = data_dir / "fibula.stl"
    if tibia_all.exists() and fibula_all.exists():
        temp_merged = result_dir / "tibia_fibula_temp.stl"
        if merge_meshes([str(tibia_all), str(fibula_all)], str(temp_merged)):
            out_l = result_dir / "tibia_l.stl"
            out_r = result_dir / "tibia_r.stl"
            if split_into_left_right_components(str(temp_merged), str(out_l), str(out_r)):
                try:
                    os.remove(temp_merged)
                    print(f"Cleaned temporary file: {temp_merged}")
                except OSError:
                    pass
    else:
        print(f"Skipping tibia/fibula split: missing tibia.stl or fibula.stl")
            
    # 3) Patella -> patella_l, patella_r (optional)
    patella_all = data_dir / "patella.stl"
    if patella_all.exists():
        temp_merged = result_dir / "patella_temp.stl"
        if merge_meshes([str(patella_all)], str(temp_merged)):
            out_l = result_dir / "patella_l.stl"
            out_r = result_dir / "patella_r.stl"
            if split_into_left_right_components(str(temp_merged), str(out_l), str(out_r)):
                try:
                    os.remove(temp_merged)
                    print(f"Cleaned temporary file: {temp_merged}")
                except OSError:
                    pass
    else:
        print(f"Skipping patella split: patella.stl not found")
            
    # 4) Phalanges_feet -> toes_l, toes_r (optional)
    phalanges_all = data_dir / "phalanges_feet.stl"
    if phalanges_all.exists():
        temp_merged = result_dir / "phalanges_feet_temp.stl"
        if merge_meshes([str(phalanges_all)], str(temp_merged)):
            out_l = result_dir / "toes_l.stl"
            out_r = result_dir / "toes_r.stl"
            if split_into_left_right_components(str(temp_merged), str(out_l), str(out_r)):
                try:
                    os.remove(temp_merged)
                    print(f"Cleaned temporary file: {temp_merged}")
                except OSError:
                    pass
    else:
        print(f"Skipping phalanges split: phalanges_feet.stl not found")
    
    # 5) Copy femur files to output directory (optional, may not exist)
    for bone in ["femur_l.stl", "femur_r.stl"]:
        src = data_dir / bone
        dst = result_dir / bone
        if src.exists():
            try:
                shutil.copy2(src, dst)
                print(f"Copied '{src}' to '{dst}'")
            except OSError as e:
                print(f"Error copying '{src}' to '{dst}': {e}")
        else:
            print(f"Skipping {bone}: not found in input directory")
    
    print("\nMesh post-processing completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())