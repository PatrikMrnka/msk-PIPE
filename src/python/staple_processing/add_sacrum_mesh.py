"""
add_sacrum_mesh.py
~~~~~~~~~~~~~~~~~~
Insert sacrum display mesh under pelvis attached_geometry in a generated OpenSim model.

This script is intentionally idempotent:
- if pelvis or attached_geometry is missing, it fails with a clear error,
- if Mesh name="sacrum_geom" already exists in pelvis, it does nothing.

Usage
-----
    python add_sacrum_mesh.py \
        --osim bone_model.osim \
        --mesh-file bone_models\\sacrum.stl
"""

import argparse
import re
import sys
from pathlib import Path


SACRUM_MESH_BLOCK = (
    "\t\t\t\t\t\t<Mesh name=\"sacrum_geom\">\n"
    "\t\t\t\t\t\t\t<socket_frame>..</socket_frame>\n"
    "\t\t\t\t\t\t\t<scale_factors>0.001 0.001 0.001</scale_factors>\n"
    "\t\t\t\t\t\t\t<Appearance>\n"
    "\t\t\t\t\t\t\t\t<opacity>1</opacity>\n"
    "\t\t\t\t\t\t\t\t<color>1 1 1</color>\n"
    "\t\t\t\t\t\t\t</Appearance>\n"
    "\t\t\t\t\t\t\t<mesh_file>{mesh_file}</mesh_file>\n"
    "\t\t\t\t\t\t</Mesh>\n"
)


def _extract_pelvis_body(xml_text: str) -> re.Match[str] | None:
    return re.search(
        r'(?s)(<Body\s+name="pelvis">)(.*?)(</Body>)',
        xml_text,
    )


def _extract_attached_geometry(pelvis_body: str) -> re.Match[str] | None:
    return re.search(
        r'(?s)(<attached_geometry>)(.*?)(</attached_geometry>)',
        pelvis_body,
    )


def add_sacrum_mesh(osim_path: Path, mesh_file: str) -> bool:
    xml_text = osim_path.read_text(encoding="utf-8")

    pelvis_match = _extract_pelvis_body(xml_text)
    if pelvis_match is None:
        raise RuntimeError('Could not find <Body name="pelvis"> in model.')

    pelvis_full = pelvis_match.group(0)
    if 'Mesh name="sacrum_geom"' in pelvis_full:
        return False

    attached_match = _extract_attached_geometry(pelvis_full)
    if attached_match is None:
        raise RuntimeError(
            'Could not find <attached_geometry> inside <Body name="pelvis">.'
        )

    attached_full = attached_match.group(0)
    updated_attached = attached_full.replace(
        "</attached_geometry>",
        SACRUM_MESH_BLOCK.format(mesh_file=mesh_file) + "\t\t\t\t\t</attached_geometry>",
        1,
    )
    updated_pelvis = pelvis_full.replace(attached_full, updated_attached, 1)
    updated_xml = xml_text.replace(pelvis_full, updated_pelvis, 1)

    osim_path.write_text(updated_xml, encoding="utf-8")
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Insert sacrum mesh block under pelvis attached_geometry in an OpenSim .osim file."
    )
    parser.add_argument("--osim", required=True, help="Path to bone_model.osim")
    parser.add_argument(
        "--mesh-file",
        default=r"bone_models\sacrum.stl",
        help=r"Mesh path written into <mesh_file> (default: bone_models\sacrum.stl)",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    osim_path = Path(args.osim).resolve()

    if not osim_path.exists():
        print(f"ERROR: .osim file not found: {osim_path}", file=sys.stderr)
        sys.exit(1)

    try:
        changed = add_sacrum_mesh(osim_path, args.mesh_file)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Cannot insert sacrum mesh.", file=sys.stderr)
        sys.exit(1)

    if changed:
        print(f"Inserted sacrum mesh into pelvis attached_geometry: {osim_path}")
    else:
        print(f"sacrum_geom already present, no change: {osim_path}")


if __name__ == "__main__":
    main()
