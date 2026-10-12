"""
map_lhdl_attachments_rnrr.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Map attachments from an LHDL template bone to a target bone using Fast-RNRR
(Yao et al., CVPR 2020) as the non-rigid step.

Drop-in alternative to ``map_lhdl_attachments.py`` (CPD).  Both scripts share
the SAME rigid pre-alignment (Z-180 rotation + point-to-plane ICP), so a
comparison between them isolates the effect of the non-rigid method only.

Pipeline
--------
1. Rigid pre-alignment of the LHDL bone onto the target bone
   (identical to the CPD variant, reused from map_lhdl_attachments.py).
2. Both meshes are centred and written as clean OBJ files, Fast_RNRR.exe
   deforms the LHDL mesh onto the target mesh (vertex order is preserved).
3. Per-vertex displacement field -> attachment points via inverse-distance
   weighted interpolation (k nearest template vertices).
4. Each transferred point is snapped to the nearest target-mesh vertex and
   written as legacy VTK POLYDATA (same format as the CPD variant).

Usage
-----
    python map_lhdl_attachments_rnrr.py \
        --lhdl-bone lhdl.obj \
        --target-bone target.stl \
        --lhdl-attachments att1.vtk att2.vtk \
        --outputs out1.vtk out2.vtk \
        --rnrr-exe src/FAST_RNRR/Fast_RNRR.exe \
        --work-dir data/output/run_1/attachments/_rnrr/femur_r

Fast-RNRR: https://github.com/Juyong/Fast_RNRR (research use only, patented).
Integration based on https://github.com/dannystefy/muscle-attachment-registration
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import trimesh
from scipy.spatial import cKDTree

# Reuse the exact rigid-alignment helpers / VTK I/O of the CPD variant so that
# both methods start from the same initial pose and write identical formats.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from map_lhdl_attachments import (  # noqa: E402
    export_to_legacy_vtk,
    load_and_sample_mesh,
    load_vtk_attachment,
)

R_Z180 = np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]])
RNRR_OUTPUT_SUFFIX = "res.obj"


# ── Mesh I/O ────────────────────────────────────────────────────────────────

def load_clean_mesh(path: str) -> trimesh.Trimesh:
    """Load OBJ/STL as an indexed triangle mesh (STL soups get merged)."""
    mesh = trimesh.load(path, force="mesh", process=True)
    mesh.remove_unreferenced_vertices()
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError(f"Empty mesh: {path}")
    return mesh


def write_obj(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    """Minimal OBJ writer (v + f only) - OpenMesh in Fast_RNRR reads it reliably."""
    with open(path, "w") as f:
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for tri in faces:
            f.write(f"f {tri[0] + 1} {tri[1] + 1} {tri[2] + 1}\n")


def read_obj_vertices(path: Path) -> np.ndarray:
    verts = []
    with open(path, "r") as f:
        for line in f:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
    return np.asarray(verts)


# ── Rigid pre-alignment (same as CPD variant) ──────────────────────────────

def rigid_prealign(lhdl_bone: str, target_bone: str):
    """Return a function mapping LHDL-space points into the target frame."""
    _, ref_pcd = load_and_sample_mesh(lhdl_bone)
    _, target_pcd = load_and_sample_mesh(target_bone)

    ref_center = ref_pcd.get_center()
    target_center = target_pcd.get_center()
    ref_pcd.rotate(R_Z180, center=ref_center)

    trans_init = np.eye(4)
    trans_init[0:3, 3] = target_center - ref_center

    reg = o3d.pipelines.registration.registration_icp(
        ref_pcd, target_pcd, 100.0, trans_init,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=5000),
    )
    T = reg.transformation.copy()
    print(f"  Rigid ICP: fitness={reg.fitness:.3f}  inlier_rmse={reg.inlier_rmse:.3f}")

    def apply(points: np.ndarray) -> np.ndarray:
        # same order as CPD script: rotate about ref_center, then apply ICP T
        p = (points - ref_center) @ R_Z180.T + ref_center
        p_h = np.hstack([p, np.ones((len(p), 1))])
        return (p_h @ T.T)[:, :3]

    return apply


# ── Fast-RNRR wrapper ───────────────────────────────────────────────────────

def run_fast_rnrr(rnrr_exe: Path, src_vertices: np.ndarray, src_faces: np.ndarray,
                  tgt_vertices: np.ndarray, tgt_faces: np.ndarray,
                  work_dir: Path, timeout: int) -> np.ndarray:
    """Deform source mesh onto target with Fast_RNRR; returns deformed source
    vertices (same order as src_vertices) in the target coordinate frame."""
    if not rnrr_exe.exists():
        raise FileNotFoundError(
            f"Fast_RNRR binary not found: {rnrr_exe}\n"
            "Copy Fast_RNRR.exe + OpenMeshCore.dll from "
            "https://github.com/dannystefy/muscle-attachment-registration/tree/main/win "
            "into the folder set in config.json -> paths.fast_rnrr_path."
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    src_c = src_vertices.mean(axis=0)
    tgt_c = tgt_vertices.mean(axis=0)

    src_obj = work_dir / "source_centered.obj"
    tgt_obj = work_dir / "target_centered.obj"
    out_stem = work_dir / "registered_centered"
    out_obj = Path(str(out_stem) + RNRR_OUTPUT_SUFFIX)
    if out_obj.exists():
        out_obj.unlink()

    write_obj(src_obj, src_vertices - src_c, src_faces)
    write_obj(tgt_obj, tgt_vertices - tgt_c, tgt_faces)

    cmd = [str(rnrr_exe.resolve()), str(src_obj.resolve()), str(tgt_obj.resolve()), str(out_stem.resolve())]
    print(f"  Fast_RNRR: {len(src_vertices)} src verts -> {len(tgt_vertices)} tgt verts")
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         cwd=str(rnrr_exe.resolve().parent))
    (work_dir / "rnrr_stdout.log").write_text(res.stdout or "")
    (work_dir / "rnrr_stderr.log").write_text(res.stderr or "")
    print(f"  Fast_RNRR finished in {time.perf_counter() - t0:.1f} s (exit {res.returncode})")

    if res.returncode != 0 or not out_obj.exists():
        raise RuntimeError(
            f"Fast_RNRR failed (exit {res.returncode}), expected output {out_obj}\n"
            f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )

    deformed = read_obj_vertices(out_obj)
    n = len(src_vertices)
    if len(deformed) < n:
        raise RuntimeError(
            f"Fast_RNRR returned {len(deformed)} vertices, expected >= {n}. "
            "Vertex correspondence lost (non-manifold source mesh?)."
        )
    # OpenMesh may append duplicated vertices for complex edges -> first n keep order
    return deformed[:n] + tgt_c


def idw_displacement(src_pts: np.ndarray, disp: np.ndarray, query: np.ndarray, k: int) -> np.ndarray:
    tree = cKDTree(src_pts)
    dists, idx = tree.query(query, k=k)
    if k == 1:
        return query + disp[idx]
    w = 1.0 / (dists + 1e-10)
    w /= w.sum(axis=1, keepdims=True)
    return query + np.einsum("mk,mkd->md", w, disp[idx])


# ── Main ────────────────────────────────────────────────────────────────────

def process_bone_attachments(lhdl_bone, target_bone, lhdl_attachments, outputs,
                             rnrr_exe, work_dir, k_interp=4, timeout=3600, no_snap=False):
    if len(lhdl_attachments) != len(outputs):
        raise ValueError("--lhdl-attachments and --outputs must have the same length")

    print(f"[RNRR] {Path(lhdl_bone).name} -> {Path(target_bone).name}")
    to_target_frame = rigid_prealign(lhdl_bone, target_bone)

    ref_mesh = load_clean_mesh(lhdl_bone)
    tgt_mesh = load_clean_mesh(target_bone)

    ref_aligned = to_target_frame(np.asarray(ref_mesh.vertices))
    tgt_verts = np.asarray(tgt_mesh.vertices)

    deformed = run_fast_rnrr(
        Path(rnrr_exe), ref_aligned, np.asarray(ref_mesh.faces),
        tgt_verts, np.asarray(tgt_mesh.faces), Path(work_dir), timeout,
    )
    displacement = deformed - ref_aligned

    # QA output: deformed template in target frame (open next to target bone)
    write_obj(Path(work_dir) / "lhdl_deformed_in_target.obj", deformed, np.asarray(ref_mesh.faces))

    # residual surface distance deformed-template -> target (quick sanity metric)
    d_res, _ = cKDTree(tgt_verts).query(deformed)
    print(f"  Residual |deformed - target|: mean={d_res.mean():.3f} mm  p95={np.percentile(d_res, 95):.3f} mm")

    tree_target = cKDTree(tgt_verts)
    for att_path, out_path in zip(lhdl_attachments, outputs):
        att_pts = np.asarray(load_vtk_attachment(att_path).points)
        att_aligned = to_target_frame(att_pts)
        moved = idw_displacement(ref_aligned, displacement, att_aligned, k_interp)
        if not no_snap:
            _, t_idx = tree_target.query(moved)
            moved = tgt_verts[t_idx]

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(moved)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        export_to_legacy_vtk(pcd, out_path)
        print(f"  {Path(att_path).name} -> {Path(out_path).name} ({len(moved)} pts)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LHDL attachment mapping with Fast-RNRR.")
    parser.add_argument("--lhdl-bone", required=True)
    parser.add_argument("--target-bone", required=True)
    parser.add_argument("--lhdl-attachments", nargs="+", required=True)
    parser.add_argument("--outputs", nargs="+", required=True)
    parser.add_argument("--rnrr-exe", required=True, help="Path to Fast_RNRR(.exe)")
    parser.add_argument("--work-dir", required=True, help="Folder for intermediate meshes/logs")
    parser.add_argument("--k-interp", type=int, default=4, help="Neighbours for IDW interpolation")
    parser.add_argument("--timeout", type=int, default=3600, help="Fast_RNRR timeout [s]")
    parser.add_argument("--no-snap", action="store_true", help="Do not snap points to target vertices")
    args = parser.parse_args()

    process_bone_attachments(
        args.lhdl_bone, args.target_bone, args.lhdl_attachments, args.outputs,
        args.rnrr_exe, args.work_dir, args.k_interp, args.timeout, args.no_snap,
    )
