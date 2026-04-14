"""
CT_raw_to_nifti.py -- Convert a RAW CT volume to NIfTI using Z coordinates.

Reads a flat binary file (.raw) together with a Z-coordinate text file,
constructs the proper affine matrix, and writes a NIfTI (.nii.gz) volume.

When the Z spacing is non-uniform the user can choose to:
  - ``--allow-nonuniform``: save with the mean dz (small positional error),
  - ``--resample-dz <mm>``: resample to a uniform grid (requires SciPy).

Example:
    python CT_raw_to_nifti.py ./data/ct.raw ./data/coordinates.txt -o ./result/ct.nii.gz
"""

import argparse
import sys
import pathlib

import numpy as np
import nibabel as nib

# Ensure runner/ is on the path so ui.py can be imported regardless of CWD.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step


def load_z_coordinates(path):
    """Load Z coordinates from a text file.

    Expects one numeric value per line (in mm).  Supports both comma and dot
    as the decimal separator and an optional unit suffix (e.g. "123,45",
    "123.45 mm").  Empty lines are ignored.  The order is preserved (no
    sorting).

    Parameters
    ----------
    path : str | pathlib.Path
        Path to the text file containing Z coordinates.

    Returns
    -------
    numpy.ndarray
        1-D float64 array of shape ``(Z,)`` where *Z* is the number of slices.

    Raises
    ------
    ValueError
        If a line cannot be converted to a number.
    OSError
        If the file cannot be opened.
    """
    zs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Support "123.45", "123,45", and "123.45 mm".
            line = line.replace(",", ".").split()[0]
            zs.append(float(line))
    return np.asarray(zs, dtype=np.float64)


def check_uniform(zs, tol=1e-3):
    """Check whether the Z coordinate spacing is uniform.

    Computes differences between consecutive values, estimates the mean step
    *dz*, and checks the maximum deviation from that mean.  If the deviation
    exceeds *tol* the grid is considered non-uniform.

    Parameters
    ----------
    zs : array-like
        1-D sequence of Z coordinates (mm) of length *Z*.
    tol : float
        Tolerance for non-uniformity detection (mm).  Default: 1e-3.

    Returns
    -------
    tuple
        - dz (float): Mean step between slices (mm).
        - nonuniform (bool): True if non-uniformity exceeds *tol*.
        - diffs (numpy.ndarray): 1-D array of consecutive Z differences.
    """
    diffs = np.diff(zs)
    dz = float(np.mean(diffs))
    nonuniform = np.max(np.abs(diffs - dz)) > tol
    return dz, nonuniform, diffs


def resample_to_uniform(grid, zs, target_dz):
    """Resample a volume with non-uniform Z slices onto a uniform grid.

    Uses linear interpolation (SciPy ``RegularGridInterpolator``) from the
    original physical coordinates ``(z_mm, y_idx, x_idx)`` to a new set of
    uniformly spaced Z values with step ``target_dz``.

    Parameters
    ----------
    grid : numpy.ndarray
        3-D array of shape ``(Z, Y, X)`` with the original data.
    zs : array-like
        1-D array of length *Z* with physical Z coordinates (mm).
    target_dz : float
        Desired step in mm for the new uniform grid.

    Returns
    -------
    tuple
        - out (numpy.ndarray): Resampled volume of shape ``(Z_new, Y, X)``, float32.
        - new_zs (numpy.ndarray): 1-D array of new Z coordinates (mm).

    Raises
    ------
    ImportError
        If SciPy is not available.
    """
    try:
        from scipy.interpolate import RegularGridInterpolator
    except ImportError:
        print_error(
            "Non-uniform Z spacing detected and SciPy is not available for "
            "resampling.\nEither install SciPy (`pip install scipy`) or use "
            "--allow-nonuniform to save with the mean dz."
        )
        raise

    z0, zN = zs[0], zs[-1]
    new_zs = np.arange(z0, zN + 0.5 * target_dz, target_dz, dtype=np.float64)
    Z, Y, X = grid.shape
    y_coords = np.arange(Y, dtype=np.float64)
    x_coords = np.arange(X, dtype=np.float64)

    interp = RegularGridInterpolator(
        (zs, y_coords, x_coords),
        grid.astype(np.float32),
        method="linear",
        bounds_error=False,
        fill_value=0,
    )

    yy, xx = np.meshgrid(y_coords, x_coords, indexing="ij")
    out = np.zeros((len(new_zs), Y, X), dtype=np.float32)
    for i, z in enumerate(new_zs):
        pts = np.stack([np.full_like(yy, z, dtype=np.float64), yy, xx], axis=-1)
        out[i] = interp(pts)

    return out, new_zs


def main():
    """CLI entry point for converting a RAW CT volume to NIfTI using Z coordinates.

    When the Z spacing is non-uniform:
      - ``--allow-nonuniform``: saves with the mean dz (may cause a small
        positional error),
      - ``--resample-dz <mm>``: resamples to a uniform grid (requires SciPy).

    Example:
        python CT_raw_to_nifti.py ./data/ct.raw ./data/coordinates.txt -o ./result/ct.nii.gz

    Exit codes:
        0 on success, >0 on input errors or incompatible dimensions.
    """
    ap = argparse.ArgumentParser(
        description="Convert a RAW CT volume to NIfTI using Z coordinates."
    )
    ap.add_argument("raw_path", type=pathlib.Path,
                    help="Path to the .raw file (e.g. LowerLimbCT_381x245x1120.raw)")
    ap.add_argument("z_txt", type=pathlib.Path,
                    help="Path to the Z coordinates text file.")
    ap.add_argument("-o", "--out", type=pathlib.Path, default=None,
                    help="Output NIfTI path (e.g. out.nii.gz)")
    ap.add_argument("--shape", type=str, default="381x245x1120",
                    help="Dimensions as XxYxZ (default: 381x245x1120)")
    ap.add_argument("--dtype", type=str, default="int16",
                    help="RAW data type (e.g. int16, uint16, float32). Default: int16")
    ap.add_argument("--little-endian", action="store_true", default=True,
                    help="RAW is little-endian (default: enabled)")
    ap.add_argument("--big-endian", action="store_true",
                    help="Switch to big-endian (overrides --little-endian)")
    ap.add_argument("--xy-spacing", type=str, default="1.0,1.0",
                    help="Pixel spacing in the X,Y plane in mm as 'sx,sy' (default: 1.0,1.0)")
    ap.add_argument("--origin-xy", type=str, default="0.0,0.0",
                    help="Origin (mm) in X,Y as 'ox,oy' (default: 0.0,0.0)")
    ap.add_argument("--allow-nonuniform", action="store_true",
                    help="Allow saving with mean dz even when Z is non-uniform "
                         "(NIfTI does not support non-uniform slices).")
    ap.add_argument("--resample-dz", type=float, default=None,
                    help="If Z is non-uniform, resample to this dz (mm). Requires SciPy.")
    ap.add_argument("--transpose", type=str, default="ZYX->XYZ",
                    choices=["none", "ZYX->XYZ"],
                    help="How to reorder axes after loading. RAW is typically (Z,Y,X); "
                         "default transposes to (X,Y,Z) for NIfTI.")
    args = ap.parse_args()

    # Parse dimensions.
    try:
        X, Y, Z = [int(v) for v in args.shape.lower().replace(" ", "").split("x")]
    except Exception:
        ap.error("--shape must be in the format XxYxZ, e.g. 381x245x1120.")

    # Data type with endianness.
    base_dtype = np.dtype(args.dtype)
    dtype = base_dtype.newbyteorder(">" if args.big_endian else "<")

    # Load RAW data.
    nvox = X * Y * Z
    raw = np.fromfile(args.raw_path, dtype=dtype, count=nvox)
    if raw.size != nvox:
        sys.exit(f"ERROR: Expected {nvox} voxels but read {raw.size}. "
                 "Check --shape, --dtype, and endianness.")

    vol_ZYX = raw.reshape((Z, Y, X))

    # Load Z coordinates.
    zs = load_z_coordinates(args.z_txt)
    if zs.size != Z:
        sys.exit(f"ERROR: Number of Z coordinates ({zs.size}) does not match "
                 f"the number of slices Z ({Z}).")

    # Uniformity check.
    dz_mean, nonuniform, diffs = check_uniform(zs)
    print_info(f"Mean dz = {dz_mean:.6f} mm; max dz deviation = "
               f"{np.max(np.abs(diffs - dz_mean)):.6f} mm")

    # Optional resampling.
    used_zs = zs
    used_grid = vol_ZYX
    if nonuniform:
        if args.resample_dz is not None:
            print_step(f"Non-uniform Z -> resampling to dz = {args.resample_dz} mm "
                       "(requires SciPy).")
            used_grid, used_zs = resample_to_uniform(vol_ZYX, zs, args.resample_dz)
        elif args.allow_nonuniform:
            print_warning("Non-uniform Z -> saving with mean dz "
                          "(may introduce a small positional error).")
        else:
            sys.exit(
                "ERROR: Z coordinates are not uniformly spaced.\n"
                "Options:\n"
                "  * add --allow-nonuniform (saves with mean dz),\n"
                "  * or use --resample-dz <mm> for resampling (requires SciPy)."
            )

    # Axis reordering.
    if args.transpose == "ZYX->XYZ":
        data_xyz = np.transpose(used_grid, (2, 1, 0))  # (X, Y, Z)
    else:
        data_xyz = used_grid  # keep (Z, Y, X) -- not recommended for NIfTI

    # Spacing and origin.
    try:
        sx, sy = [float(v) for v in args.xy_spacing.replace(" ", "").split(",")]
        ox, oy = [float(v) for v in args.origin_xy.replace(" ", "").split(",")]
    except Exception:
        ap.error("--xy-spacing and --origin-xy must be in the format 'a,b'.")

    z0 = float(used_zs[0])
    dz_for_affine = (
        float(np.mean(np.diff(used_zs))) if used_zs.size > 1 else float(dz_mean)
    )

    # Affine matrix (RAS).
    affine = np.array([
        [sx,  0.0, 0.0, ox],
        [0.0, sy,  0.0, oy],
        [0.0, 0.0, dz_for_affine, z0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float64)

    # Build NIfTI image.
    img = nib.Nifti1Image(data_xyz, affine)
    hdr = img.header
    hdr.set_xyzt_units("mm")
    zooms = (sx, sy, dz_for_affine)
    try:
        hdr.set_zooms(zooms + (1.0,))
    except Exception:
        hdr.set_zooms(zooms)

    # Output path.
    out_path = args.out
    if out_path is None:
        out_path = args.raw_path.with_suffix("").with_suffix(".nii.gz")
    out_path = pathlib.Path(out_path)

    nib.save(img, out_path)
    print_success(f"Done: {out_path}")


if __name__ == "__main__":
    main()
