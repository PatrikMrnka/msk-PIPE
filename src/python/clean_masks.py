"""
clean_masks.py — Binary mask post-processing for NIfTI segmentation files.

Processing pipeline per mask:
    1. Binarize with threshold `iso`  (values >= iso → 0, else → 1)
    2. Connected-component analysis; discard small / unwanted components
    3. Optional morphological closing then opening
    4. Optional iterative hole filling

Multiple files are processed in parallel (--workers flag).
"""

import argparse
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import SimpleITK as sitk

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class CleanConfig:
    """All tunable parameters for the mask-cleaning pipeline."""
    iso: float = 0.5
    keep_largest: bool = True
    min_voxels: int = 2000
    opening: int = 1            # morphological opening radius  (0 = disabled)
    closing: int = 1            # morphological closing radius  (0 = disabled)
    fill_holes: bool = False
    fully_connected: bool = False


# ---------------------------------------------------------------------------
# Pipeline steps  (private helpers, each does exactly one thing)
# ---------------------------------------------------------------------------

def _binarize(img: sitk.Image, iso: float) -> sitk.Image:
    """Threshold the image: voxels >= iso → 0 (background), else → 1 (foreground).

    Note: the inside/outside values are intentionally inverted relative to the
    threshold direction — this convention is preserved from the original script.
    """
    return sitk.BinaryThreshold(
        img,
        lowerThreshold=iso,
        upperThreshold=1e9,
        insideValue=0,
        outsideValue=1,
    )


def _label_components(bin_img: sitk.Image, fully_connected: bool) -> tuple[sitk.Image, dict[int, int]]:
    """Run connected-component labelling and return (label image, {label: voxel_count})."""
    cc_filter = sitk.ConnectedComponentImageFilter()
    cc_filter.SetFullyConnected(fully_connected)
    cc = cc_filter.Execute(bin_img)

    stats = sitk.LabelShapeStatisticsImageFilter()
    stats.Execute(cc)

    sizes = {lbl: stats.GetNumberOfPixels(lbl) for lbl in stats.GetLabels()}
    return cc, sizes


def _select_labels(sizes: dict[int, int], keep_largest: bool, min_voxels: int) -> set[int]:
    """Return the set of component labels that should be kept."""
    keep: set[int] = set()

    if keep_largest:
        keep.add(max(sizes, key=lambda lbl: sizes[lbl]))

    keep.update(lbl for lbl, n in sizes.items() if n >= min_voxels)

    # Fallback: always keep at least the largest component.
    if not keep:
        keep.add(max(sizes, key=lambda lbl: sizes[lbl]))

    return keep


def _build_mask(cc: sitk.Image, keep: set[int], reference: sitk.Image) -> sitk.Image:
    """Create a binary uint8 mask retaining only the selected component labels.

    Uses np.isin for a single vectorised pass — much faster than iterative OR.
    """
    cc_arr = sitk.GetArrayFromImage(cc)                         # shape (Z, Y, X)
    mask_arr = np.isin(cc_arr, list(keep)).astype(np.uint8)

    mask = sitk.GetImageFromArray(mask_arr)
    mask.CopyInformation(reference)                             # preserve spacing / origin / direction
    return mask


def _apply_morphology(mask: sitk.Image, closing: int, opening: int) -> sitk.Image:
    """Apply morphological closing then opening (either can be disabled with radius=0)."""
    if closing > 0:
        mask = sitk.BinaryMorphologicalClosing(mask, [closing, closing, closing])
    if opening > 0:
        mask = sitk.BinaryMorphologicalOpening(mask, [opening, opening, opening])
    return mask


def _fill_holes(mask: sitk.Image) -> sitk.Image:
    """Fill small interior holes using iterative voting hole filling."""
    filler = sitk.VotingBinaryIterativeHoleFillingImageFilter()
    filler.SetForegroundValue(1)
    filler.SetBackgroundValue(0)
    filler.SetMaximumNumberOfIterations(3)
    filler.SetRadius([1, 1, 1])
    return filler.Execute(mask)


# ---------------------------------------------------------------------------
# Main per-file entry point
# ---------------------------------------------------------------------------

def clean_mask_file(in_path: Path, out_path: Path, cfg: CleanConfig) -> None:
    """Load, clean, and save a single binary mask according to *cfg*.

    Writes an empty mask (all zeros) if the binarized image contains no
    foreground voxels.
    """
    img = sitk.ReadImage(str(in_path))

    bin_img = _binarize(img, cfg.iso)
    cc, sizes = _label_components(bin_img, cfg.fully_connected)

    if not sizes:
        empty = sitk.Image(img.GetSize(), sitk.sitkUInt8)
        empty.CopyInformation(img)
        sitk.WriteImage(empty, str(out_path))
        return

    keep = _select_labels(sizes, cfg.keep_largest, cfg.min_voxels)
    mask = _build_mask(cc, keep, reference=img)
    mask = _apply_morphology(mask, cfg.closing, cfg.opening)

    if cfg.fill_holes:
        mask = _fill_holes(mask)

    sitk.WriteImage(mask, str(out_path))


# ---------------------------------------------------------------------------
# Task dataclass + worker
# ---------------------------------------------------------------------------

@dataclass
class CleanTask:
    """Describes a single file to process."""
    src: Path
    dst: Path
    do_clean: bool      # False → just copy the file unchanged
    inplace: bool
    backup_dir: Path | None
    cfg: CleanConfig


def _run_task(task: CleanTask) -> str:
    """Execute one CleanTask. Returns a human-readable status string."""
    if not task.do_clean:
        if not task.inplace and not task.dst.exists():
            shutil.copy2(task.src, task.dst)
        return f"Copied unchanged: {task.src.name}"

    if task.inplace and task.backup_dir is not None:
        backup_path = task.backup_dir / task.src.name
        if not backup_path.exists():
            shutil.copy2(task.src, backup_path)

        # Write to a temp file first, then atomically replace the original.
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / task.src.name
            clean_mask_file(task.src, tmp_path, task.cfg)
            shutil.move(str(tmp_path), str(task.src))

        return f"Cleaned (in-place): {task.src.name}"

    clean_mask_file(task.src, task.dst, task.cfg)
    return f"Cleaned: {task.src.name}"


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------

def _iter_mask_files(directory: Path):
    """Yield .nii.gz files first, then .nii — both sorted alphabetically."""
    yield from sorted(directory.glob("*.nii.gz"))
    yield from sorted(directory.glob("*.nii"))


def _stem(path: Path) -> str:
    """Filename without .nii or .nii.gz extension."""
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_cleaning(
    input_dir: Path,
    output_dir: Path,
    cfg: CleanConfig,
    labels: list[str] | None = None,
    inplace: bool = False,
    workers: int = 4,
) -> None:
    """Discover mask files and process them (in parallel when workers > 1)."""
    in_dir = input_dir.resolve()
    if not in_dir.exists():
        raise SystemExit(f"Input directory does not exist: {in_dir}")

    if inplace:
        out_dir = in_dir
        backup_dir = in_dir.parent / "segmentations_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        print_info(f"Cleaning in-place: {in_dir}  (backup → {backup_dir})")
    else:
        out_dir = output_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        backup_dir = None
        print_info(f"Cleaning: {in_dir} → {out_dir}")

    files = list(_iter_mask_files(in_dir))
    if not files:
        print_warning("No .nii / .nii.gz mask files found.")
        return

    selected = set(labels) if labels else set()

    tasks = [
        CleanTask(
            src=src,
            dst=out_dir / src.name,
            do_clean=not selected or _stem(src) in selected,
            inplace=inplace,
            backup_dir=backup_dir,
            cfg=cfg,
        )
        for src in files
    ]

    _execute_tasks(tasks, workers)
    print_success("Mask cleaning finished.")


def _execute_tasks(tasks: list[CleanTask], workers: int) -> None:
    """Run tasks in parallel (workers > 1) or sequentially (workers == 1)."""
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_task, t): t.src.name for t in tasks}
            for future in as_completed(futures):
                try:
                    print_info(future.result())
                except Exception as exc:
                    print_error(f"{futures[future]}: {exc}")
    else:
        for task in tasks:
            try:
                print_info(_run_task(task))
            except Exception as exc:
                print_error(f"{task.src.name}: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Clean binary NIfTI masks: binarize, filter components, morphological ops."
    )

    # I/O -- two modes: single-file or directory
    single = p.add_argument_group("single-file mode")
    single.add_argument("--input-file", default=None,
                        help="Path to a single .nii / .nii.gz mask file.")
    single.add_argument("--output-file", default=None,
                        help="Output path for the cleaned mask (single-file mode).")

    batch = p.add_argument_group("directory (batch) mode")
    batch.add_argument("--input-dir", default=None,
                       help="Folder containing input .nii / .nii.gz mask files.")
    batch.add_argument("--output-dir", default="",
                       help="Output folder for cleaned masks (ignored with --inplace).")
    batch.add_argument("--labels", nargs="*", default=None,
                       help="Mask names to clean (no extension). Omit to process all files.")
    batch.add_argument("--workers", type=int, default=4,
                       help="Number of parallel worker processes (default: 4).")
    batch.add_argument("--inplace", action="store_true",
                       help="Overwrite originals; a backup is created automatically.")

    # CleanConfig fields
    p.add_argument("--iso",        type=float, default=0.5,
                   help="Binarization threshold (default: 0.5).")
    p.add_argument("--min-voxels", type=int,   default=2000,
                   help="Minimum component size in voxels (default: 2000).")
    p.add_argument("--opening",    type=int,   default=1,
                   help="Morphological opening radius; 0 = disabled (default: 1).")
    p.add_argument("--closing",    type=int,   default=1,
                   help="Morphological closing radius; 0 = disabled (default: 1).")

    p.add_argument("--keep-largest",    dest="keep_largest", action="store_true")
    p.add_argument("--no-keep-largest", dest="keep_largest", action="store_false",
                   help="Do not force-keep the largest component.")
    p.set_defaults(keep_largest=True)

    p.add_argument("--fill-holes",      action="store_true",
                   help="Run iterative hole filling after morphological ops.")
    p.add_argument("--fully-connected", action="store_true",
                   help="Use 26-connectivity instead of 6-connectivity.")

    return p


def main() -> None:
    args = _build_argparser().parse_args()

    cfg = CleanConfig(
        iso=args.iso,
        keep_largest=args.keep_largest,
        min_voxels=args.min_voxels,
        opening=args.opening,
        closing=args.closing,
        fill_holes=args.fill_holes,
        fully_connected=args.fully_connected,
    )

    # Single-file mode: process one mask and exit.
    if args.input_file:
        in_path = Path(args.input_file)
        if not in_path.exists():
            raise SystemExit(f"Input file does not exist: {in_path}")
        out_path = Path(args.output_file) if args.output_file else in_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"Cleaning single file: {in_path} -> {out_path}")
        clean_mask_file(in_path, out_path, cfg)
        print_success(f"Cleaned: {out_path.name}")
        return

    # Directory (batch) mode.
    if not args.input_dir:
        raise SystemExit("Provide either --input-file or --input-dir.")

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.input_dir)

    run_cleaning(
        input_dir=Path(args.input_dir),
        output_dir=output_dir,
        cfg=cfg,
        labels=args.labels,
        inplace=args.inplace,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()