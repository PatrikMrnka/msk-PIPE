"""
CONVERTOVTK_DELETEAFTER.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Convert one STL/OBJ mesh into a legacy VTK file.

Usage
-----
    python CONVERTOVTK_DELETEAFTER.py \
        --input mesh.obj \
        --output mesh.vtk
"""

from __future__ import annotations

import argparse
from pathlib import Path

import vtk


SUPPORTED_EXTENSIONS = {".stl", ".obj"}


def build_reader(source_path: Path) -> vtk.vtkAlgorithm:
	extension = source_path.suffix.lower()
	if extension == ".stl":
		reader = vtk.vtkSTLReader()
	elif extension == ".obj":
		reader = vtk.vtkOBJReader()
	else:
		raise ValueError(f"Unsupported input format: {source_path.suffix}")

	reader.SetFileName(str(source_path))
	return reader


def convert_mesh(source_path: Path, target_path: Path, *, ascii_output: bool = True) -> None:
	target_path.parent.mkdir(parents=True, exist_ok=True)

	reader = build_reader(source_path)
	triangle_filter = vtk.vtkTriangleFilter()
	triangle_filter.SetInputConnection(reader.GetOutputPort())
	triangle_filter.Update()

	polydata = triangle_filter.GetOutput()
	if polydata.GetNumberOfPoints() == 0:
		raise RuntimeError(f"No geometry found in {source_path}")

	writer = vtk.vtkPolyDataWriter()
	writer.SetFileName(str(target_path))
	writer.SetInputData(polydata)
	writer.SetFileVersion(vtk.vtkPolyDataWriter.VTK_LEGACY_READER_VERSION_4_2)
	if ascii_output:
		writer.SetFileTypeToASCII()
	else:
		writer.SetFileTypeToBinary()

	if writer.Write() != 1:
		raise RuntimeError(f"Failed to write {target_path}")


def resolve_output_path(input_path: Path, output_path: Path) -> Path:
	if output_path.exists() and output_path.is_dir():
		return output_path / f"{input_path.stem}.vtk"

	if output_path.suffix.lower() == ".vtk":
		return output_path

	# If suffix is missing, treat --output as a folder path.
	if output_path.suffix == "":
		return output_path / f"{input_path.stem}.vtk"

	raise ValueError("--output must be a .vtk file or a directory path")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Convert one STL/OBJ mesh into a legacy VTK file."
	)
	parser.add_argument("--input", type=Path, required=True, help="Path to one .stl or .obj file")
	parser.add_argument("--output", type=Path, required=True, help="Path to output .vtk file or output folder")
	parser.add_argument("--binary", action="store_true", help="Write legacy VTK files in binary instead of ASCII.")
	return parser.parse_args()


def main() -> int:
	args = parse_args()

	input_path = args.input
	if not input_path.exists() or not input_path.is_file():
		print(f"Input file not found: {input_path}")
		return 1

	if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
		print("Unsupported input format. Use .stl or .obj")
		return 1

	try:
		target_path = resolve_output_path(input_path, args.output)
		convert_mesh(input_path, target_path, ascii_output=not args.binary)
		print(f"Converted: {input_path} -> {target_path}")
		return 0
	except Exception as exc:
		print(f"Failed: {input_path} ({exc})")
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
