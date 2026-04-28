"""
clean_mesh.py
~~~~~~~~~~~~~
Validate and clean a single 3D mesh (OBJ/STL) in place.

The script is invoked per-file so that Snakemake can parallelise cleaning.
It performs the following validations / fixes using `trimesh`:

    1. NaN / Inf vertex coordinates  -> drop such vertices (and faces using them)
    2. Duplicate vertices            -> merged
    3. Degenerate faces (zero area)  -> removed
    4. Unreferenced vertices         -> removed
    5. Duplicate faces               -> removed
    6. Non-manifold edges            -> reported (edge shared by > 2 faces)
    7. Non-manifold vertices         -> reported (fan connectivity check)

All edits are written back to the same path (in place). A JSON-like stats
line is printed to stdout so Snakemake logs remain auditable.

Usage
-----
    python clean_mesh.py \
        --input data/temp/mesh.obj
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from runner.ui import print_error, print_info, print_step, print_success, print_warning
except Exception:  # pragma: no cover - UI helpers are non-critical.
    def print_error(msg):   print(f"[ERROR] {msg}", file=sys.stderr)
    def print_info(msg):    print(msg)
    def print_step(msg):    print(msg)
    def print_success(msg): print(f"[ OK ] {msg}")
    def print_warning(msg): print(f"[WARN] {msg}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_as_trimesh(path: str):
    """Load `path` and, if it is a Scene, concatenate into a single mesh."""
    try:
        loaded = trimesh.load_mesh(path, process=False)
    except Exception as exc:
        print_error(f"Failed to load mesh '{path}': {exc}")
        return None

    if isinstance(loaded, trimesh.Trimesh):
        return loaded

    try:
        parts = [
            g for g in getattr(loaded, "geometry", {}).values()
            if isinstance(g, trimesh.Trimesh)
        ]
        if not parts:
            print_error(f"No trimesh geometry found in '{path}'")
            return None
        return trimesh.util.concatenate(parts)
    except Exception as exc:
        print_error(f"Could not flatten scene in '{path}': {exc}")
        return None


def _count_non_manifold_edges(mesh: trimesh.Trimesh) -> int:
    """Return the number of edges shared by more than two faces."""
    try:
        edges = np.sort(mesh.edges, axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        return int((counts > 2).sum())
    except Exception:
        return -1


def _count_non_manifold_vertices(mesh: trimesh.Trimesh) -> int:
    """Return vertices whose incident faces do not form a single fan.

    A vertex is manifold iff the sub-graph of faces incident to it (connected
    through shared edges) is a single connected component.
    """
    try:
        vf = mesh.vertex_faces  # (n_vertices, max_degree) with -1 padding
        face_adj = mesh.face_adjacency
    except Exception:
        return -1

    adj = [[] for _ in range(len(mesh.faces))]
    for a, b in face_adj:
        adj[a].append(b)
        adj[b].append(a)

    non_manifold = 0
    for row in vf:
        local = row[row >= 0]
        if len(local) <= 1:
            continue
        local_set = set(int(x) for x in local)
        start = next(iter(local_set))
        seen = {start}
        stack = [start]
        while stack:
            f = stack.pop()
            for nb in adj[f]:
                if nb in local_set and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(seen) != len(local_set):
            non_manifold += 1
    return non_manifold


# ---------------------------------------------------------------------------
# Core cleaning routine
# ---------------------------------------------------------------------------


def clean_mesh_in_place(path: str, area_tol: float = 1e-12) -> Tuple[bool, dict]:
    """Clean `path` in place.  Returns (success, stats)."""
    stats = {
        "nan_inf_vertices": 0,
        "duplicate_vertices": 0,
        "degenerate_faces": 0,
        "unreferenced_vertices": 0,
        "duplicate_faces": 0,
        "non_manifold_edges": 0,
        "non_manifold_vertices": 0,
    }

    if not os.path.exists(path):
        print_error(f"Input mesh not found: {path}")
        return False, stats

    print_step(f"\n--- CLEAN MESH ---  {path}")
    mesh = _load_as_trimesh(path)
    if mesh is None:
        return False, stats

    v0, f0 = len(mesh.vertices), len(mesh.faces)
    print_info(f"Loaded: {v0} vertices, {f0} faces")

    # 1. NaN / Inf coordinates
    finite_mask = np.isfinite(mesh.vertices).all(axis=1)
    n_bad = int((~finite_mask).sum())
    if n_bad:
        stats["nan_inf_vertices"] = n_bad
        print_warning(f"NaN/Inf in {n_bad} vertices - removing those and their faces")
        remap = np.full(len(mesh.vertices), -1, dtype=np.int64)
        keep = np.where(finite_mask)[0]
        remap[keep] = np.arange(len(keep))
        new_vertices = mesh.vertices[keep]
        face_mask = finite_mask[mesh.faces].all(axis=1)
        new_faces = remap[mesh.faces[face_mask]]
        mesh = trimesh.Trimesh(vertices=new_vertices, faces=new_faces, process=False)

    # 2. Degenerate faces (zero area)
    try:
        areas = mesh.area_faces
        nondeg = areas > area_tol
        n_deg = int((~nondeg).sum())
        if n_deg:
            stats["degenerate_faces"] = n_deg
            print_warning(f"Degenerate faces: {n_deg} - removing")
            mesh.update_faces(nondeg)
    except Exception as exc:
        print_warning(f"Could not evaluate face areas: {exc}")

    # 3. Duplicate vertices (merge)
    v_before = len(mesh.vertices)
    try:
        mesh.merge_vertices(merge_tex=False, merge_norm=False)
    except TypeError:
        mesh.merge_vertices()
    v_after = len(mesh.vertices)
    if v_after < v_before:
        stats["duplicate_vertices"] = v_before - v_after
        print_warning(f"Merged {v_before - v_after} duplicate vertices")

    # 4. Duplicate faces
    try:
        sorted_faces = np.sort(mesh.faces, axis=1)
        _, unique_idx = np.unique(sorted_faces, axis=0, return_index=True)
        n_dup_faces = len(mesh.faces) - len(unique_idx)
        if n_dup_faces > 0:
            stats["duplicate_faces"] = n_dup_faces
            print_warning(f"Duplicate faces: {n_dup_faces} - removing")
            keep_mask = np.zeros(len(mesh.faces), dtype=bool)
            keep_mask[unique_idx] = True
            mesh.update_faces(keep_mask)
    except Exception as exc:
        print_warning(f"Could not deduplicate faces: {exc}")

    # 5. Unreferenced vertices
    referenced = np.zeros(len(mesh.vertices), dtype=bool)
    if len(mesh.faces):
        referenced[np.unique(mesh.faces)] = True
    n_unref = int((~referenced).sum())
    if n_unref:
        stats["unreferenced_vertices"] = n_unref
        print_warning(f"Unreferenced vertices: {n_unref} - removing")
        mesh.remove_unreferenced_vertices()

    # 6. Non-manifold edges / vertices (report only)
    nm_edges = _count_non_manifold_edges(mesh)
    if nm_edges > 0:
        stats["non_manifold_edges"] = nm_edges
        print_warning(f"Non-manifold edges: {nm_edges} (reported, not auto-fixed)")
    nm_verts = _count_non_manifold_vertices(mesh)
    if nm_verts > 0:
        stats["non_manifold_vertices"] = nm_verts
        print_warning(f"Non-manifold vertices: {nm_verts} (reported, not auto-fixed)")

    v1, f1 = len(mesh.vertices), len(mesh.faces)
    print_info(
        f"Cleaned: {v1} vertices, {f1} faces  "
        f"(delta_v={v0 - v1}, delta_f={f0 - f1})"
    )
    print_info(f"stats={stats}")

    try:
        mesh.export(path)
    except Exception as exc:
        print_error(f"Failed to write cleaned mesh '{path}': {exc}")
        return False, stats

    print_success(f"Saved cleaned mesh in place: {path}")
    return True, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate & clean a single OBJ/STL mesh in place.",
    )
    parser.add_argument("--input", required=True, help="Path to mesh file (modified in place).")
    parser.add_argument(
        "--area-tol",
        type=float,
        default=1e-12,
        help="Triangle area below this value is treated as degenerate.",
    )
    args = parser.parse_args()

    ok, _stats = clean_mesh_in_place(args.input, area_tol=args.area_tol)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
