#include "MeshConverter.h"

#include <vtkImageData.h>
#include <vtkSmartPointer.h>
#include <vtkNIFTIImageReader.h>
#include <vtkFlyingEdges3D.h>
#include <vtkWindowedSincPolyDataFilter.h>
#include <vtkCleanPolyData.h>
#include <vtkTriangleFilter.h>
#include <vtkPolyData.h>
#include <vtkSTLWriter.h>
#include <vtkOBJWriter.h>
#include <vtkNew.h>
#include <vtkPolyDataConnectivityFilter.h>
#include <vtkQuadricDecimation.h>

#include <iostream>
#include <string>
#include <algorithm>

// ─────────────────────────────────────────────────────────────────────────────
// Constructor
// ─────────────────────────────────────────────────────────────────────────────

MeshConverter::MeshConverter(const MeshConverterArgs& args)
    : args_(args)
{}

// ─────────────────────────────────────────────────────────────────────────────
// String helpers
// ─────────────────────────────────────────────────────────────────────────────

std::string MeshConverter::toLower(std::string s)
{
    for (char& c : s)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

bool MeshConverter::endsWith(const std::string& s, const std::string& suffix)
{
    return s.size() >= suffix.size()
        && std::equal(suffix.rbegin(), suffix.rend(), s.rbegin());
}

/// Strips ".nii" from double-extension files like "bone.nii.gz" whose stem is "bone.nii".
std::string MeshConverter::stripNiiStem(const std::string& stem)
{
    if (endsWith(toLower(stem), ".nii"))
        return stem.substr(0, stem.size() - 4);
    return stem;
}

bool MeshConverter::isNiftiFile(const fs::path& p)
{
    std::string name = toLower(p.filename().string());
    return endsWith(name, ".nii.gz") || endsWith(name, ".nii");
}

// ─────────────────────────────────────────────────────────────────────────────
// VTK pipeline steps (file-local helpers)
// ─────────────────────────────────────────────────────────────────────────────

/// Read a NIfTI image from disk.
[[nodiscard]]
static vtkSmartPointer<vtkImageData> readNifti(const fs::path& p)
{
    vtkNew<vtkNIFTIImageReader> reader;
    reader->SetFileName(p.string().c_str());
    reader->Update();
    return reader->GetOutput();
}

/// Extract an isosurface from a binary mask volume using Flying Edges.
[[nodiscard]]
static vtkSmartPointer<vtkPolyData> extractSurface(vtkImageData* img, double isoValue)
{
    vtkNew<vtkFlyingEdges3D> fe;
    fe->SetInputData(img);
    fe->SetValue(0, isoValue);
    fe->ComputeNormalsOff();
    fe->Update();
    return fe->GetOutput();
}

/// Smooth, clean and triangulate a surface mesh.
/// Bilateral bones (fibula / tibia) skip the "keep largest region" step to
/// preserve both left and right sides.
[[nodiscard]]
static vtkSmartPointer<vtkPolyData> smoothMesh(vtkPolyData* pd,
                                                int iters,
                                                double passband,
                                                const std::string& filename)
{
    // Helper: lower-case filename for bilateral-bone detection.
    std::string name_lower = filename;
    std::transform(name_lower.begin(), name_lower.end(), name_lower.begin(),
                   [](unsigned char c){ return std::tolower(c); });

    vtkNew<vtkCleanPolyData>  clean;
    clean->SetInputData(pd);

    vtkNew<vtkPolyDataConnectivityFilter> connectivity;
    vtkNew<vtkWindowedSincPolyDataFilter> ws;

    if (name_lower.find("fibula") != std::string::npos ||
        name_lower.find("tibia")  != std::string::npos)
    {
        // Bilateral bones: keep ALL regions (both left + right sides).
        ws->SetInputConnection(clean->GetOutputPort());
    }
    else
    {
        // Single-structure bones / muscles: keep only the largest component.
        connectivity->SetInputConnection(clean->GetOutputPort());
        connectivity->SetExtractionModeToLargestRegion();
        ws->SetInputConnection(connectivity->GetOutputPort());
    }

    ws->SetNumberOfIterations(iters);
    ws->SetPassBand(passband);
    ws->BoundarySmoothingOff();
    ws->FeatureEdgeSmoothingOff();
    ws->NonManifoldSmoothingOn();
    ws->NormalizeCoordinatesOn();
    ws->Update();

    vtkNew<vtkTriangleFilter>  tri;
    tri->SetInputConnection(ws->GetOutputPort());

    vtkNew<vtkCleanPolyData> finalClean;
    finalClean->SetInputConnection(tri->GetOutputPort());
    finalClean->PointMergingOn();
    finalClean->Update();

    return finalClean->GetOutput();
}

/// Reduce polygon count with quadric edge-collapse decimation.
/// target_reduction in [0.0, 1.0): fraction of triangles to *remove*.
/// Returns the input unchanged when target_reduction == 0.
[[nodiscard]]
static vtkSmartPointer<vtkPolyData> decimateMesh(vtkPolyData* pd, double target_reduction)
{
    if (target_reduction <= 0.0)
        return pd;

    vtkNew<vtkQuadricDecimation> dec;
    dec->SetInputData(pd);
    dec->SetTargetReduction(target_reduction);
    dec->Update();
    return dec->GetOutput();
}

/// Write a poly data mesh to disk in the requested format.
[[nodiscard]]
static bool writeMesh(const fs::path& outPath, vtkPolyData* pd, const std::string& format)
{
    if (format == "obj")
    {
        vtkNew<vtkOBJWriter> w;
        w->SetFileName(outPath.string().c_str());
        w->SetInputData(pd);
        return w->Write() == 1;
    }
    else  // stl (default)
    {
        vtkNew<vtkSTLWriter> w;
        w->SetFileName(outPath.string().c_str());
        w->SetInputData(pd);
        w->SetFileTypeToBinary();
        return w->Write() == 1;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────────────

bool MeshConverter::convert(const fs::path& inputFile) const
{
    if (!isNiftiFile(inputFile))
    {
        std::cerr << "[WARNING] Not a NIfTI file, skipping: "
                  << inputFile.filename().string() << "\n";
        return false;
    }

    std::cout << "[INFO] Meshing: " << inputFile.filename().string() << "\n";

    auto img   = readNifti(inputFile);
    auto surf  = extractSurface(img, args_.binary_threshold);
    auto mesh  = smoothMesh(surf, args_.smooth_iters, args_.passband,
                             inputFile.filename().string());
    auto final = decimateMesh(mesh, args_.target_reduction);

    // Preserve the original stem (strip the double-.nii extension if present).
    std::string stem = stripNiiStem(inputFile.stem().string());
    std::string ext  = (args_.format == "obj") ? ".obj" : ".stl";
    fs::path    out  = args_.output_dir / (stem + ext);

    bool ok = writeMesh(out, final, args_.format);
    if (!ok)
        std::cerr << "[ERROR] Failed to write: " << out.string() << "\n";
    return ok;
}
