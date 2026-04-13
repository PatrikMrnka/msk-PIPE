// mask_to_mesh — Converts binary NIfTI masks to surface meshes (STL or OBJ).
// Responsibilities: reading NIfTI, isosurface extraction, smoothing, writing mesh.
// NOT responsible for file renaming; that belongs to the workflow (Snakefile).

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

#include <filesystem>
#include <string>
#include <vector>
#include <iostream>
#include <optional>

namespace fs = std::filesystem;

// ---------------------------------------------------------------------------
// CLI arguments
// ---------------------------------------------------------------------------

struct Args
{
    fs::path    input_dir;
    fs::path    output_dir;
    int         smooth_iters     = 30;
    double      passband         = 0.01;   // typical range: 0.005–0.02
    double      binary_threshold = 0.5;
    std::string format           = "stl";  // "stl" | "obj"
};

static void usage(const char *prog)
{
    std::cerr
        << "Usage: " << prog
        << " --input-dir <path> --output-dir <dir>"
           " [--smooth_iters N] [--passband F] [--format stl|obj]\n"
           "\n"
           "  --input-dir    Path to a NIfTI file or directory of NIfTI files.\n"
           "  --output-dir   Directory where meshes will be written.\n"
           "  --smooth_iters Number of windowed-sinc smoothing iterations (default 30).\n"
           "  --passband     Passband for smoothing filter (default 0.01).\n"
           "  --format       Output format: stl (default) or obj.\n";
}

static std::optional<Args> parseArgs(int argc, char **argv)
{
    Args a;

    // Helper: consume the next token from argv, or emit an error and return nullopt
    auto requireNext = [&](int &i, const std::string &flag) -> std::optional<std::string>
    {
        if (i + 1 >= argc)
        {
            std::cerr << "[ERROR] Missing value for " << flag << "\n";
            return {};
        }
        return std::string{argv[++i]};
    };

    for (int i = 1; i < argc; ++i)
    {
        std::string arg = argv[i];

        if (arg == "--input-dir")
        {
            auto v = requireNext(i, arg);
            if (!v) return {};
            a.input_dir = *v;
        }
        else if (arg == "--output-dir")
        {
            auto v = requireNext(i, arg);
            if (!v) return {};
            a.output_dir = *v;
        }
        else if (arg == "--smooth_iters")
        {
            auto v = requireNext(i, arg);
            if (!v) return {};
            a.smooth_iters = std::stoi(*v);
        }
        else if (arg == "--passband")
        {
            auto v = requireNext(i, arg);
            if (!v) return {};
            a.passband = std::stod(*v);
        }
        else if (arg == "--format")
        {
            auto v = requireNext(i, arg);
            if (!v) return {};
            if (*v == "stl" || *v == "obj")
                a.format = *v;
            else
            {
                std::cerr << "[ERROR] --format must be 'stl' or 'obj', got: " << *v << "\n";
                return {};
            }
        }
        else
        {
            std::cerr << "[ERROR] Unknown argument: " << arg << "\n";
            usage(argv[0]);
            return {};
        }
    }

    if (a.input_dir.empty() || a.output_dir.empty())
    {
        std::cerr << "[ERROR] --input-dir and --output-dir are required.\n";
        usage(argv[0]);
        return {};
    }

    return a;
}

// ---------------------------------------------------------------------------
// String helpers
// ---------------------------------------------------------------------------

static std::string toLower(std::string s)
{
    for (char &c : s)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

/// Returns true if `s` ends with `suffix` (case-sensitive).
static bool endsWith(const std::string &s, const std::string &suffix)
{
    return s.size() >= suffix.size()
        && std::equal(suffix.rbegin(), suffix.rend(), s.rbegin());
}

/// Strips ".nii" from double-extension files like "bone.nii.gz" whose stem is "bone.nii".
static std::string stripNiiStem(const std::string &stem)
{
    if (endsWith(toLower(stem), ".nii"))
        return stem.substr(0, stem.size() - 4);
    return stem;
}

// ---------------------------------------------------------------------------
// VTK pipeline steps
// ---------------------------------------------------------------------------

/// Read a NIfTI image from disk.
[[nodiscard]]
static vtkSmartPointer<vtkImageData> readNifti(const fs::path &p)
{
    vtkNew<vtkNIFTIImageReader> reader;
    reader->SetFileName(p.string().c_str());
    reader->Update();
    return reader->GetOutput();
}

/// Extract an isosurface from a binary mask volume using Flying Edges.
[[nodiscard]]
static vtkSmartPointer<vtkPolyData> extractSurface(vtkImageData *img, double isoValue)
{
    vtkNew<vtkFlyingEdges3D> fe;
    fe->SetInputData(img);
    fe->SetValue(0, isoValue);
    fe->ComputeNormalsOff();
    fe->Update();
    return fe->GetOutput();
}

/// Smooth, clean and triangulate a surface mesh.
[[nodiscard]]
static vtkSmartPointer<vtkPolyData> smoothMesh(vtkPolyData *pd, int iters, double passband)
{
    vtkNew<vtkCleanPolyData> clean;
    clean->SetInputData(pd);

    vtkNew<vtkWindowedSincPolyDataFilter> ws;
    ws->SetInputConnection(clean->GetOutputPort());
    ws->SetNumberOfIterations(iters);
    ws->SetPassBand(passband);
    ws->BoundarySmoothingOff();
    ws->FeatureEdgeSmoothingOff();
    ws->NonManifoldSmoothingOn();
    ws->NormalizeCoordinatesOn();
    ws->Update();

    vtkNew<vtkTriangleFilter> tri;
    tri->SetInputConnection(ws->GetOutputPort());
    tri->Update();
    return tri->GetOutput();
}

/// Write a poly data mesh to disk in the requested format.
[[nodiscard]]
static bool writeMesh(const fs::path &outPath, vtkPolyData *pd, const std::string &format)
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

// ---------------------------------------------------------------------------
// High-level conversion
// ---------------------------------------------------------------------------

/// Convert a single binary NIfTI mask file to a surface mesh.
/// Output filename mirrors the input stem — renaming for downstream tools
/// is handled by the workflow orchestrator (Snakefile), not here.
[[nodiscard]]
static bool convertMaskToMesh(const fs::path &inputFile,
                               const fs::path &outputDir,
                               const Args     &a)
{
    std::cout << "[INFO] Meshing: " << inputFile.filename().string() << "\n";

    auto img  = readNifti(inputFile);
    auto surf = extractSurface(img, a.binary_threshold);
    auto mesh = smoothMesh(surf, a.smooth_iters, a.passband);

    // Preserve the original stem (strip the double-.nii extension if present)
    std::string stem = stripNiiStem(inputFile.stem().string());
    std::string ext  = (a.format == "obj") ? ".obj" : ".stl";
    fs::path    out  = outputDir / (stem + ext);

    bool ok = writeMesh(out, mesh, a.format);
    if (!ok)
        std::cerr << "[ERROR] Failed to write: " << out.string() << "\n";
    return ok;
}

/// Returns true if a file looks like a NIfTI file (.nii or .nii.gz).
static bool isNiftiFile(const fs::path &p)
{
    std::string name = toLower(p.filename().string());
    return endsWith(name, ".nii.gz") || endsWith(name, ".nii");
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

int main(int argc, char **argv)
{
    auto parsed = parseArgs(argc, argv);
    if (!parsed)
        return 1;

    const Args &a = *parsed;

    try
    {
        fs::create_directories(a.output_dir);
    }
    catch (const std::exception &e)
    {
        std::cerr << "[ERROR] Cannot create output directory: " << e.what() << "\n";
        return 1;
    }

    bool allOk = true;

    if (fs::is_regular_file(a.input_dir))
    {
        allOk = convertMaskToMesh(a.input_dir, a.output_dir, a);
    }
    else if (fs::is_directory(a.input_dir))
    {
        for (const auto &entry : fs::directory_iterator(a.input_dir))
        {
            if (entry.is_regular_file() && isNiftiFile(entry.path()))
                allOk &= convertMaskToMesh(entry.path(), a.output_dir, a);
        }
    }
    else
    {
        std::cerr << "[ERROR] --input-dir is neither a file nor a directory: "
                  << a.input_dir.string() << "\n";
        return 1;
    }

    std::cout << (allOk ? "[OK] Done.\n" : "[WARNING] Finished with errors.\n");
    return allOk ? 0 : 2;
}
