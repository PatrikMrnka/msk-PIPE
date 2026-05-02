#include "MeshConverter.h"

#include <filesystem>
#include <iostream>
#include <optional>
#include <string>

namespace fs = std::filesystem;

// ─────────────────────────────────────────────────────────────────────────────
// CLI
// ─────────────────────────────────────────────────────────────────────────────

static void usage(const char* prog)
{
    std::cerr
        << "Usage: " << prog
        << " --input-dir <path> --output-dir <dir>"
           " [--smooth_iters N] [--passband F] [--format stl|obj]\n"
           "\n"
           "  --input-dir       Path to a NIfTI file or directory of NIfTI files.\n"
           "  --output-dir      Directory where meshes will be written.\n"
           "  --smooth_iters    Windowed-sinc smoothing iterations (default 30).\n"
           "  --passband        Passband for smoothing filter (default 0.01).\n"
           "  --format          Output format: stl (default) or obj.\n"
           "  --decimate_target Quadric decimation reduction ratio 0.0-1.0 (default 0.0 = off).\n";
}

static std::optional<MeshConverterArgs> parseArgs(int argc, char** argv)
{
    MeshConverterArgs a;

    auto requireNext = [&](int& i, const std::string& flag) -> std::optional<std::string>
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
            auto v = requireNext(i, arg); if (!v) return {};
            a.input_dir = *v;
        }
        else if (arg == "--output-dir")
        {
            auto v = requireNext(i, arg); if (!v) return {};
            a.output_dir = *v;
        }
        else if (arg == "--smooth_iters")
        {
            auto v = requireNext(i, arg); if (!v) return {};
            a.smooth_iters = std::stoi(*v);
        }
        else if (arg == "--passband")
        {
            auto v = requireNext(i, arg); if (!v) return {};
            a.passband = std::stod(*v);
        }
        else if (arg == "--format")
        {
            auto v = requireNext(i, arg); if (!v) return {};
            if (*v == "stl" || *v == "obj")
                a.format = *v;
            else
            {
                std::cerr << "[ERROR] --format must be 'stl' or 'obj', got: " << *v << "\n";
                return {};
            }
        }
        else if (arg == "--decimate_target")
        {
            auto v = requireNext(i, arg); if (!v) return {};
            a.target_reduction = std::stod(*v);
            if (a.target_reduction < 0.0 || a.target_reduction >= 1.0)
            {
                std::cerr << "[ERROR] --decimate_target must be in [0.0, 1.0).\n";
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

// ─────────────────────────────────────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────────────────────────────────────

int main(int argc, char** argv)
{
    auto parsed = parseArgs(argc, argv);
    if (!parsed) return 1;

    const MeshConverterArgs& a = *parsed;

    try
    {
        fs::create_directories(a.output_dir);
    }
    catch (const std::exception& e)
    {
        std::cerr << "[ERROR] Cannot create output directory: " << e.what() << "\n";
        return 1;
    }

    MeshConverter converter(a);
    bool allOk = true;

    if (fs::is_regular_file(a.input_dir))
    {
        allOk = converter.convert(a.input_dir);
    }
    else if (fs::is_directory(a.input_dir))
    {
        for (const auto& entry : fs::directory_iterator(a.input_dir))
        {
            if (entry.is_regular_file())
                allOk &= converter.convert(entry.path());
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
