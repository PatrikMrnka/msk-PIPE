"""
check_attachments.py - sanity check of attachment VTK files of two pipeline runs.

Compares <base>/attachments/*.vtk with <new>/attachments/*.vtk and flags things
that can break Muscle Wrapping 2.0: missing/empty files, NaN/Inf, different point
counts, duplicate points, and points that are far from the corresponding point of
the base run (= registration probably failed for that bone).

Usage (from repo root):
    envs\\msk_base\\python.exe tools\\check_attachments.py data\\output\\run_1 data\\output\\run_2
"""
import sys
from pathlib import Path

import numpy as np


def load_points(path: Path) -> np.ndarray:
    pts, n, inside = [], 0, False
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s.startswith("POINTS"):
                n, inside = int(s.split()[1]), True
                continue
            if inside:
                v = s.split()
                for i in range(0, len(v) - 2, 3):
                    pts.append([float(v[i]), float(v[i + 1]), float(v[i + 2])])
                if len(pts) >= n:
                    break
    return np.asarray(pts[:n]).reshape(-1, 3)


def main(base: Path, new: Path) -> int:
    base_files = {p.name: p for p in sorted((base / "attachments").glob("*.vtk"))}
    new_files = {p.name: p for p in sorted((new / "attachments").glob("*.vtk"))}
    print(f"{'file':<34}{'n_base':>7}{'n_new':>7}{'uniq_new':>9}{'mean_d':>9}{'max_d':>9}  flags")
    problems = 0
    for name in sorted(set(base_files) | set(new_files)):
        flags = []
        pb = load_points(base_files[name]) if name in base_files else None
        pn = load_points(new_files[name]) if name in new_files else None
        if pn is None:
            print(f"{name:<34}{'-':>7}{'-':>7}{'-':>9}{'-':>9}{'-':>9}  MISSING in new run")
            problems += 1
            continue
        if len(pn) == 0:
            flags.append("EMPTY")
        if not np.isfinite(pn).all():
            flags.append("NaN/Inf")
        uniq = len({tuple(np.round(p, 4)) for p in pn})
        if len(pn) and uniq < len(pn):
            flags.append(f"{len(pn) - uniq} DUPLICATES")
        mean_d = max_d = float("nan")
        if pb is not None and len(pb):
            if len(pb) != len(pn):
                flags.append("COUNT differs")
            else:
                d = np.linalg.norm(pb - pn, axis=1)
                mean_d, max_d = float(d.mean()), float(d.max())
                if mean_d > 15:
                    flags.append("FAR from base run")
        problems += bool(flags)
        print(f"{name:<34}{(len(pb) if pb is not None else 0):>7}{len(pn):>7}{uniq:>9}{mean_d:>9.2f}{max_d:>9.2f}  {', '.join(flags)}")
    print(f"\n{problems} file(s) with flags.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
