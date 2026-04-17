"""
generate_attachment_xml.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Generates a MuscleGeneratorTool XML setup file from a topology JSON
and the extracted VTK attachment files.

Produces output compatible with the OpenSim / MW-2.0 schema visible
in data/input/mw2/setup_MuscleGeneratorTool.xml.

Usage
-----
    python generate_attachment_xml.py \
        --osim      data/temp/output_STAPLE/bone_model.osim \
        --muscles   data/temp/muscle_models \
        --vtks      data/temp/attachments \
        --topology  config/muscle_topology.json \
        --out-xml   data/temp/setup_MuscleGeneratorTool.xml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom
import shutil

# Ensure runner/ and src/python/ are on the path regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.ui import print_info, print_success, print_warning, print_error, print_step
from muscle_names import MUSCLE_NAME_TO_STEM

# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────


def indent_xml(elem: ET.Element, level: int = 0) -> str:
    """Return a pretty-printed XML string for *elem*."""
    rough = ET.tostring(elem, encoding="unicode")
    reparsed = minidom.parseString(rough)
    pretty = reparsed.toprettyxml(indent="\t")
    # minidom adds an extra xml declaration – strip first line
    lines = pretty.splitlines()
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    return "\n".join(lines)


def sub(parent: ET.Element, tag: str, text: str = "", **attrib) -> ET.Element:
    """Create a sub-element with optional text and attributes."""
    el = ET.SubElement(parent, tag, **attrib)
    if text:
        el.text = text
    return el


def relative_to_xml(xml_dir: Path, target: Path) -> str:
    """Return target path relative to xml_dir using forward slashes."""
    return os.path.relpath(target, xml_dir).replace("\\", "/")


def normalize_body_name(body_name: str) -> str:
    """Map internal bone names to the names expected in the XML."""
    return "pelvis" if body_name == "pelvis_no_sacrum" else body_name


def extract_joint_transform(
    osim_path: Path, joint_name: str = "hip_r"
) -> tuple[str, str]:
    """
    Parses the .osim file robustly (ignoring namespaces) and extracts
    the translation (centre) and orientation of the defined joint's PhysicalOffsetFrame.
    """
    try:
        tree = ET.parse(osim_path)
        root = tree.getroot()

        def local_name(tag: str) -> str:
            return tag.split("}")[-1]

        # 1. Find joint
        joint_el = None
        for elem in root.iter():
            tag = local_name(elem.tag)
            if tag.endswith("Joint") and elem.get("name") == joint_name:
                joint_el = elem
                break

        if joint_el is None:
            return "", ""

        # 2. OpenSim 4.x: find parent frame name (usually 'pelvis_offset')
        # from <socket_parent_frame>, then resolve it in joint <frames>.
        parent_frame_name = ""
        for elem in joint_el.iter():
            tag = local_name(elem.tag)
            if tag == "socket_parent_frame" and elem.text:
                parent_frame_name = elem.text.strip().split("/")[-1]
                break

        offset_frame = None

        # Preferred branch for OpenSim 4.x .osim files
        if parent_frame_name:
            for elem in joint_el.iter():
                tag = local_name(elem.tag)
                if (
                    tag == "PhysicalOffsetFrame"
                    and elem.get("name") == parent_frame_name
                ):
                    offset_frame = elem
                    break

        # Backward-compatible fallback for older schema used by reference MW2 XMLs
        if offset_frame is None:
            parent_frame = None
            for elem in joint_el.iter():
                tag = local_name(elem.tag)
                if tag == "parent_frame":
                    parent_frame = elem
                    break

            if parent_frame is not None:
                for elem in parent_frame.iter():
                    tag = local_name(elem.tag)
                    if tag == "PhysicalOffsetFrame":
                        offset_frame = elem
                        break

        if offset_frame is None:
            return "", ""

        translation = ""
        orientation = ""
        for elem in offset_frame.iter():
            tag = local_name(elem.tag)
            if tag == "translation" and elem.text:
                translation = elem.text.strip()
            elif tag == "orientation" and elem.text:
                orientation = elem.text.strip()

        return translation, orientation
    except Exception as e:
        print_warning(f"Error parsing osim for joint '{joint_name}': {e}")
        return "", ""


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate MuscleGeneratorTool XML from topology JSON + VTK attachments."
    )
    p.add_argument(
        "--osim", required=True, help="Input .osim file produced by MSK-STAPLE."
    )
    p.add_argument(
        "--muscles", required=True, help="Directory containing muscle mesh .obj files."
    )
    p.add_argument(
        "--vtks",
        required=True,
        help="Directory containing extracted .vtk attachment files.",
    )
    p.add_argument(
        "--topology", required=True, help="Path to config/muscle_topology.json."
    )
    p.add_argument("--out-xml", required=True, help="Output XML file path.")
    p.add_argument(
        "--motion-file",
        default="hip_flexion_kinematics.mot",
        help="Motion .mot file name (default: hip_flexion_kinematics.mot).",
    )
    p.add_argument(
        "--output-model",
        default="pipeline_model.osim",
        help="Output .osim model file name (default: pipeline_model.osim).",
    )
    p.add_argument(
        "--num-lines",
        type=int,
        default=16,
        help="num_of_lines per muscle generator (default: 16).",
    )
    p.add_argument(
        "--line-res",
        type=int,
        default=15,
        help="line_res per muscle generator (default: 15).",
    )
    p.add_argument(
        "--kinematics-algorithm",
        type=str.lower,
        default="havlicek",
        choices=["havlicek", "luca"],
        help="Kinematics fibre algorithm to write into XML (havlicek or luca).",
    )
    return p


# ─────────────────────────────────────────────────────────────────
# XML builder
# ─────────────────────────────────────────────────────────────────


def build_xml(
    osim_path: Path,
    muscles_dir: Path,
    vtks_dir: Path,
    out_xml_dir: Path,
    topology: dict[str, dict[str, str]],
    motion_file: str,
    muscle_activations_file: str,
    output_model: str,
    num_lines: int,
    line_res: int,
    kinematics_algorithm: str,
) -> ET.Element:

    root = ET.Element("OpenSimDocument", Version="20302")
    tool = sub(root, "MuscleGeneratorTool", name="pipeline_MGT")

    sub(tool, "model_file", osim_path.name)
    sub(tool, "motion_file", motion_file)
    sub(tool, "output_model_file", output_model)
    # ET.Comment(" <output_muscle_analysis_file_prefix>./Experiments/</output_muscle_analysis_file_prefix> ")
    sub(tool, "output_muscle_analysis_file_prefix", "./Experiments/")

    gen_set = sub(tool, "MuscleGeneratorSet")
    objects = sub(gen_set, "objects")

    added_muscles = set()

    for muscle_name, roles in topology.items():
        origin_bone = normalize_body_name(roles.get("origin", ""))
        insertion_bone = normalize_body_name(roles.get("insertion", ""))

        # Locate the muscle mesh .obj (filename may vary -- try stem match)
        muscle_obj = None
        for ext in (".obj", ".OBJ"):
            candidate = muscles_dir / (muscle_name + ext)
            if candidate.exists():
                muscle_obj = candidate
                break

        if muscle_obj is None:
            prefix = MUSCLE_NAME_TO_STEM.get(muscle_name)
            if prefix:
                for side in ("_r", "_l"):
                    candidate = muscles_dir / (prefix + side + ".obj")
                    if candidate.exists():
                        muscle_obj = candidate
                        break

        if muscle_obj is None:
            # Try a looser match (first file containing muscle_name)
            for f in muscles_dir.glob("*.obj"):
                if muscle_name.lower() in f.stem.lower():
                    muscle_obj = f
                    break

        # Locate the VTK files
        ori_vtk = vtks_dir / f"{muscle_name}_Ori.vtk"
        ins_vtk = vtks_dir / f"{muscle_name}_Ins.vtk"

        if not ori_vtk.exists() or not ins_vtk.exists():
            print_warning(
                f"Missing attachment VTK(s) for {muscle_name} (ori: {ori_vtk.exists()}, ins: {ins_vtk.exists()}). Skipping."
            )
            continue

        added_muscles.add(muscle_name)

        # ── MuscleGenerator block ─────────────────────────────────
        mg = sub(objects, "MuscleGenerator", name=muscle_name)

        geom = sub(mg, "MuscleGeometry")
        sub(geom, "body", origin_bone)

        mesh_el = sub(geom, "Mesh", name=muscle_name)
        sub(mesh_el, "scale_factors", "0.001 0.001 0.001")
        if muscle_obj:
            mesh_file_name = relative_to_xml(out_xml_dir, muscle_obj)
        else:
            mesh_file_name = f"{muscle_name}.obj"
        sub(mesh_el, "mesh_file", mesh_file_name)

        # Attachment areas
        areas = sub(geom, "attachment_areas")

        # Origin
        ori_area = sub(areas, "AttachmentArea", name=f"origin {origin_bone}")
        sub(ori_area, "type", "origin")
        sub(ori_area, "body", origin_bone)
        sub(ori_area, "point_file", relative_to_xml(out_xml_dir, ori_vtk))
        sub(ori_area, "scale_factors", "0.001 0.001 0.001")

        # Insertion
        ins_area = sub(areas, "AttachmentArea", name=f"insertion {insertion_bone}")
        sub(ins_area, "type", "insertion")
        sub(ins_area, "body", insertion_bone)
        sub(ins_area, "point_file", relative_to_xml(out_xml_dir, ins_vtk))
        sub(ins_area, "scale_factors", "0.001 0.001 0.001")

        # Fibre parameters
        sub(mg, "fiber_template", " parallel ")
        sub(mg, "fiber_arrangement", " uniform ")
        sub(mg, "num_of_lines", f" {num_lines} ")
        sub(mg, "line_res", f" {line_res} ")

    sub(gen_set, "groups")

    # ── Add kinematics_fibre_algorithm block (configurable) ─────
    kfa = sub(tool, "kinematics_fibre_algorithm")

    if kinematics_algorithm == "luca":
        sub(kfa, "Luca2018viaPointsAlgorithm")
        return root

    translation, orientation = extract_joint_transform(osim_path, "hip_r")
    if not translation or not orientation:
        print_warning("Could not extract joint transform from OSIM. Using defaults.")
        translation = "0 0 0"
        orientation = "0 0 0"

    muscles_involved = []
    for muscle_name, roles in topology.items():
        if muscle_name not in added_muscles:
            continue
        origin = normalize_body_name(roles.get("origin", ""))
        insertion = normalize_body_name(roles.get("insertion", ""))
        if origin in ("pelvis", "femur_r") or insertion in ("pelvis", "femur_r"):
            muscles_involved.append(muscle_name)

    xpbd = sub(kfa, "Havlicek2024XPBDAlgorithm")
    jii_container = sub(xpbd, "joint_interaction_information")

    jii = sub(jii_container, "JointInteractionInformation", name="hip_r")
    sub(jii, "body", "femur_r")
    sub(jii, "centre", translation)
    sub(jii, "orientation", orientation)
    sub(jii, "scale_factors", "0.001 0.001 0.001")

    # Adding a trailing space to match the string in the example
    sub(jii, "muscles_involved", " ".join(muscles_involved) + " ")

    sub(jii, "muscle_activations_file", muscle_activations_file)

    return root


# ─────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────


def main() -> None:
    args = build_argparser().parse_args()
    selected_algorithm = args.kinematics_algorithm.lower()

    osim_path = Path(args.osim).resolve()
    muscles_dir = Path(args.muscles).resolve()
    vtks_dir = Path(args.vtks).resolve()
    topology_p = Path(args.topology).resolve()
    out_xml = Path(args.out_xml).resolve()
    out_xml_dir = out_xml.parent

    opensim_data_dir = Path("data/opensim").resolve()
    motion_candidate = Path(args.motion_file)
    if motion_candidate.is_absolute():
        motion_target = motion_candidate
    else:
        motion_target = opensim_data_dir / motion_candidate.name

    motion_file_rel = relative_to_xml(out_xml_dir, motion_target)
    activations_file_rel = relative_to_xml(
        out_xml_dir, opensim_data_dir / "hip_activations.sto"
    )

    # ── Validation ────────────────────────────────────────────────
    for label, p in [
        ("osim", osim_path),
        ("muscles", muscles_dir),
        ("vtks", vtks_dir),
        ("topology", topology_p),
    ]:
        if not p.exists():
            print_error(f"{label} path not found: {p}")
            sys.exit(1)

    with open(topology_p, encoding="utf-8") as fh:
        topology: dict[str, dict[str, str]] = json.load(fh)

    print_step(f"Building XML for {len(topology)} muscle(s)...")

    root = build_xml(
        osim_path=osim_path,
        muscles_dir=muscles_dir,
        vtks_dir=vtks_dir,
        out_xml_dir=out_xml_dir,
        topology=topology,
        motion_file=motion_file_rel,
        muscle_activations_file=activations_file_rel,
        output_model=args.output_model,
        num_lines=args.num_lines,
        line_res=args.line_res,
        kinematics_algorithm=selected_algorithm,
    )

    out_xml.parent.mkdir(parents=True, exist_ok=True)
    (out_xml.parent / "Experiments").mkdir(parents=True, exist_ok=True)

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + indent_xml(root)
    out_xml.write_text(xml_str, encoding="utf-8")

    print_success(f"XML written to: {out_xml}")


if __name__ == "__main__":
    main()
