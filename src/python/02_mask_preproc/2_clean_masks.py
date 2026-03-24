import argparse
from pathlib import Path
import shutil
import tempfile

import SimpleITK as sitk


def clean_mask_file(
    in_path: Path,
    out_path: Path,
    iso: float = 0.5,
    keep_largest: bool = True,
    min_voxels: int = 2000,
    opening: int = 1,
    closing: int = 1,
    fill_holes: bool = False,
    fully_connected: bool = False,
) -> None:
    """Načte masku, binarizuje a provede základní čištění a uložení.

    Kroky zpracování:
    - Binarizace s prahem `iso` (>= iso je 1, jinak 0)
    - Komponentová analýza, ponechání největší a/nebo větších než `min_voxels`
    - Morfologické operace (closing, opening) a volitelné vyplnění děr

    Parametry:
        in_path: Cesta ke vstupnímu .nii/.nii.gz.
        out_path: Cesta k výstupnímu souboru .nii.gz s vyčištěnou maskou.
        iso: Prah pro binarizaci (v intenzitách obrazu). 
        keep_largest: Pokud True, vždy zachová největší komponentu.
        min_voxels: Minimální velikost komponenty (ve voxelech), která bude zachována.
        opening: Poloměr pro BinaryMorphologicalOpening (0 vypíná).
        closing: Poloměr pro BinaryMorphologicalClosing (0 vypíná).
        fill_holes: Vyplnit malé díry vevnitř masky.
        fully_connected: Použít fully-connected mód pro ConnectedComponents.

    Návratová hodnota:
        None. Výsledek se uloží do `out_path`.
    """
    img = sitk.ReadImage(str(in_path))

    # Binarizace: hodnoty v intervalu <iso, +inf> nastaví na 0, ostatní na 1 (inverzní maska)
    bin_img = sitk.BinaryThreshold(img, lowerThreshold=iso, upperThreshold=1e9, insideValue=0, outsideValue=1)

    # Spojité komponenty (Connected Components)
    cc_filter = sitk.ConnectedComponentImageFilter()
    if fully_connected:
        cc_filter.FullyConnectedOn()
    else:
        cc_filter.FullyConnectedOff()
    cc = cc_filter.Execute(bin_img)

    # Statistika značek (počet voxelů v komponentách)
    stats = sitk.LabelShapeStatisticsImageFilter()
    stats.Execute(cc)
    labels = list(stats.GetLabels())

    if not labels:
        empty = sitk.Image(img.GetSize(), sitk.sitkUInt8)
        empty.CopyInformation(img)
        sitk.WriteImage(empty, str(out_path))
        return

    keep = set()
    if keep_largest:
        largest = max(labels, key=lambda l: stats.GetNumberOfPixels(l))
        keep.add(largest)

    if min_voxels and min_voxels > 0:
        for l in labels:
            if stats.GetNumberOfPixels(l) >= int(min_voxels):
                keep.add(l)

    if not keep:
        largest = max(labels, key=lambda l: stats.GetNumberOfPixels(l))
        keep.add(largest)

    mask = sitk.Image(img.GetSize(), sitk.sitkUInt8)
    mask.CopyInformation(img)
    for l in keep:
        mask = mask | sitk.Cast(cc == l, sitk.sitkUInt8)

    if closing and closing > 0:
        mask = sitk.BinaryMorphologicalClosing(mask, [closing, closing, closing])
    if opening and opening > 0:
        mask = sitk.BinaryMorphologicalOpening(mask, [opening, opening, opening])

    if fill_holes:
        vf = sitk.VotingBinaryIterativeHoleFillingImageFilter()
        vf.SetForegroundValue(1)
        vf.SetBackgroundValue(0)
        vf.SetMaximumNumberOfIterations(3)
        vf.SetRadius([1, 1, 1])
        mask = vf.Execute(mask)

    sitk.WriteImage(mask, str(out_path))


def iter_mask_files(input_dir: Path):
    for p in sorted(input_dir.glob("*.nii.gz")):
        yield p
    for p in sorted(input_dir.glob("*.nii")):
        yield p


def stem_without_nii_suffix(path: Path) -> str:
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


def run_cleaning(
    input_dir: Path,
    output_dir: Path,
    labels: list[str] | None,
    iso: float,
    keep_largest: bool,
    min_voxels: int,
    opening: int,
    closing: int,
    fill_holes: bool,
    fully_connected: bool,
    inplace: bool,
) -> None:
    in_dir = input_dir.resolve()
    if not in_dir.exists():
        raise SystemExit(f"Input directory does not exist: {in_dir}")

    selected = set(labels or [])

    if inplace:
        out_dir = in_dir
        backup_dir = in_dir.parent / "segmentations_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"Cleaning in-place in {in_dir} (backup: {backup_dir})")
    else:
        out_dir = output_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        backup_dir = None
        print(f"Cleaning from {in_dir} -> {out_dir}")

    files = list(iter_mask_files(in_dir))
    if not files:
        print("No .nii/.nii.gz mask files found.")
        return

    for src in files:
        stem = stem_without_nii_suffix(src)
        should_clean = not selected or stem in selected

        dst = out_dir / src.name
        if should_clean:
            if inplace and backup_dir is not None:
                backup_path = backup_dir / src.name
                if not backup_path.exists():
                    shutil.copy2(src, backup_path)
                with tempfile.TemporaryDirectory() as td:
                    tmp_path = Path(td) / src.name
                    clean_mask_file(
                        src,
                        tmp_path,
                        iso=iso,
                        keep_largest=keep_largest,
                        min_voxels=min_voxels,
                        opening=opening,
                        closing=closing,
                        fill_holes=fill_holes,
                        fully_connected=fully_connected,
                    )
                    shutil.move(str(tmp_path), str(src))
                    print(f"Cleaned (in-place): {src.name}")
            else:
                clean_mask_file(
                    src,
                    dst,
                    iso=iso,
                    keep_largest=keep_largest,
                    min_voxels=min_voxels,
                    opening=opening,
                    closing=closing,
                    fill_holes=fill_holes,
                    fully_connected=fully_connected,
                )
                print(f"Cleaned: {src.name}")
        elif not inplace:
            if not dst.exists():
                shutil.copy2(src, dst)
            print(f"Copied unchanged: {src.name}")

    print("Mask cleaning finished.")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Clean binary masks from any source (not only TotalSegmentator)."
    )
    p.add_argument("--input-dir", required=True, help="Input folder with .nii/.nii.gz masks")
    p.add_argument(
        "--output-dir",
        default="",
        help="Output folder for cleaned masks (ignored with --inplace)",
    )
    p.add_argument(
        "--labels",
        nargs="*",
        default=None,
        help="Optional list of mask names to clean (without extension). If omitted, all masks are cleaned.",
    )
    p.add_argument("--iso", type=float, default=0.5)
    p.add_argument("--min-voxels", type=int, default=2000)
    p.add_argument("--keep-largest", action="store_true")
    p.add_argument("--no-keep-largest", dest="keep_largest", action="store_false")
    p.set_defaults(keep_largest=True)
    p.add_argument("--opening", type=int, default=1)
    p.add_argument("--closing", type=int, default=1)
    p.add_argument("--fill-holes", action="store_true")
    p.add_argument("--fully-connected", action="store_true")
    p.add_argument("--inplace", action="store_true")
    return p


def main() -> None:
    args = build_argparser().parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.input_dir)

    run_cleaning(
        input_dir=Path(args.input_dir),
        output_dir=output_dir,
        labels=args.labels,
        iso=args.iso,
        keep_largest=bool(args.keep_largest),
        min_voxels=int(args.min_voxels),
        opening=int(args.opening),
        closing=int(args.closing),
        fill_holes=bool(args.fill_holes),
        fully_connected=bool(args.fully_connected),
        inplace=bool(args.inplace),
    )


if __name__ == "__main__":
    main()
