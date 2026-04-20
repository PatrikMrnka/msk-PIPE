"""
VTK to NIfTI Converter
Converts VTK MRI images (RECTILINEAR_GRID) to NIfTI format (.nii.gz)
"""

import sys
import os
import numpy as np
import vtk
from vtk.util import numpy_support
import nibabel as nib
import argparse
from pathlib import Path


def read_vtk_file(filename):
    """
    Read VTK file and extract image data
    
    Args:
        filename: Path to VTK file
        
    Returns:
        tuple: (numpy_array, spacing, origin, dimensions)
    """
    print(f"Reading VTK file: {filename}")
    
    # Create reader for VTK file
    reader = vtk.vtkRectilinearGridReader()
    reader.SetFileName(filename)
    reader.ReadAllScalarsOn()
    reader.Update()
    
    # Get the rectilinear grid
    grid = reader.GetOutput()
    
    if grid is None:
        raise ValueError("Failed to read VTK file")
    
    # Get dimensions
    dims = grid.GetDimensions()
    print(f"Dimensions: {dims}")
    
    # Get coordinates for spacing calculation
    x_coords = numpy_support.vtk_to_numpy(grid.GetXCoordinates())
    y_coords = numpy_support.vtk_to_numpy(grid.GetYCoordinates())
    z_coords = numpy_support.vtk_to_numpy(grid.GetZCoordinates())
    
    # Calculate spacing (assuming regular spacing)
    spacing = [1.0, 1.0, 1.0]  # Default spacing
    
    if len(x_coords) > 1:
        spacing[0] = abs(x_coords[1] - x_coords[0])
    if len(y_coords) > 1:
        spacing[1] = abs(y_coords[1] - y_coords[0])
    if len(z_coords) > 1:
        spacing[2] = abs(z_coords[1] - z_coords[0])
    
    print(f"Spacing: {spacing}")
    
    # Get origin
    origin = [x_coords[0], y_coords[0], z_coords[0]]
    print(f"Origin: {origin}")
    
    # Get point data (scalar values)
    point_data = grid.GetPointData()
    
    if point_data.GetNumberOfArrays() == 0:
        raise ValueError("No scalar data found in VTK file")
    
    # Get the first scalar array
    scalars = point_data.GetArray(0)
    
    if scalars is None:
        scalars = point_data.GetScalars()
    
    if scalars is None:
        raise ValueError("Could not extract scalar data from VTK file")
    
    # Convert VTK array to numpy array
    numpy_array = numpy_support.vtk_to_numpy(scalars)
    
    # Reshape array to 3D
    numpy_array = numpy_array.reshape(dims[2], dims[1], dims[0])
    
    # Transpose to match NIfTI convention (may need adjustment based on your data)
    numpy_array = numpy_array.transpose(2, 1, 0)
    
    print(f"Array shape: {numpy_array.shape}")
    print(f"Data type: {numpy_array.dtype}")
    print(f"Value range: [{numpy_array.min()}, {numpy_array.max()}]")
    
    return numpy_array, spacing, origin, dims


def vtk_to_nifti(input_file, output_file, force_overwrite=False):
    """
    Convert VTK file to NIfTI format
    
    Args:
        input_file: Path to input VTK file
        output_file: Path to output NIfTI file
        force_overwrite: Whether to overwrite existing output file
    """
    
    # Check if input file exists
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    # Check if output file exists
    if os.path.exists(output_file) and not force_overwrite:
        response = input(f"Output file {output_file} already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Conversion cancelled.")
            return
    
    try:
        # Read VTK file
        image_data, spacing, origin, dims = read_vtk_file(input_file)
        
        # Create affine transformation matrix
        # This is a simple identity matrix with spacing and origin
        # May need adjustment based on your specific coordinate system
        affine = np.eye(4)
        affine[0, 0] = spacing[0]
        affine[1, 1] = spacing[1]
        affine[2, 2] = spacing[2]
        affine[0, 3] = origin[0]
        affine[1, 3] = origin[1]
        affine[2, 3] = origin[2]
        
        print("\nCreating NIfTI image...")
        
        # Create NIfTI image
        nifti_image = nib.Nifti1Image(image_data.astype(np.float32), affine)
        
        # Set pixel dimensions (spacing)
        nifti_image.header.set_zooms(spacing)
        
        # Save NIfTI file
        print(f"Saving to: {output_file}")
        nib.save(nifti_image, output_file)
        
        print("Conversion completed successfully!")
        
        # Verify saved file
        print("\nVerifying saved file...")
        loaded = nib.load(output_file)
        print(f"Loaded shape: {loaded.shape}")
        print(f"Loaded affine:\n{loaded.affine}")
        
    except Exception as e:
        print(f"Error during conversion: {str(e)}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Convert VTK MRI images to NIfTI format (.nii.gz)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.vtk output.nii.gz
  %(prog)s -f input.vtk output.nii.gz  # Force overwrite
  %(prog)s --batch *.vtk                # Convert multiple files
        """
    )
    
    parser.add_argument('input', help='Input VTK file path')
    parser.add_argument('output', nargs='?', help='Output NIfTI file path (optional, defaults to input_name.nii.gz)')
    parser.add_argument('-f', '--force', action='store_true', help='Force overwrite existing output file')
    parser.add_argument('--batch', action='store_true', help='Batch convert multiple VTK files')
    
    args = parser.parse_args()
    
    if args.batch:
        # Batch processing
        import glob
        vtk_files = glob.glob(args.input)
        
        if not vtk_files:
            print(f"No VTK files found matching pattern: {args.input}")
            sys.exit(1)
        
        print(f"Found {len(vtk_files)} VTK files to convert")
        
        for vtk_file in vtk_files:
            output_file = Path(vtk_file).stem + '.nii.gz'
            print(f"\nConverting {vtk_file} -> {output_file}")
            try:
                vtk_to_nifti(vtk_file, output_file, args.force)
            except Exception as e:
                print(f"Failed to convert {vtk_file}: {str(e)}")
                continue
    else:
        # Single file conversion
        input_file = args.input
        
        if args.output:
            output_file = args.output
        else:
            # Generate output filename
            output_file = Path(input_file).stem + '.nii.gz'
        
        # Ensure output has correct extension
        if not output_file.endswith('.nii.gz') and not output_file.endswith('.nii'):
            output_file += '.nii.gz'
        
        vtk_to_nifti(input_file, output_file, args.force)


if __name__ == "__main__":
    main()