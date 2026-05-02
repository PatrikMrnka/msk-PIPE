#pragma once

// MeshConverter — converts binary NIfTI masks to surface meshes (STL or OBJ).
//
// Encapsulates all VTK pipeline steps so that main.cpp only deals with CLI
// parsing and calling convert(). The class is intentionally stateless between
// conversions; every call to convert() is independent.
//
// Mirrors the design pattern established in extract_attachments/AttachmentExtractor.

#include <filesystem>
#include <string>

namespace fs = std::filesystem;

// ─────────────────────────────────────────────────────────────────────────────
// Configuration passed in from CLI
// ─────────────────────────────────────────────────────────────────────────────

struct MeshConverterArgs
{
    fs::path    input_dir;
    fs::path    output_dir;
    int         smooth_iters     = 30;
    double      passband         = 0.01;
    double      binary_threshold = 0.5;
    std::string format           = "stl";
    double      target_reduction = 0.0;   // 0.0 = disabled; 0.9 = keep 10 % polygons
};

// ─────────────────────────────────────────────────────────────────────────────
// MeshConverter
//
// Stateless converter: call convert() once per NIfTI file.
//
// Typical usage:
//   MeshConverterArgs args = { ... };
//   MeshConverter mc(args);
//   bool ok = mc.convert(inputFile);
// ─────────────────────────────────────────────────────────────────────────────

class MeshConverter
{
public:
    explicit MeshConverter(const MeshConverterArgs& args);

    // Convert a single binary NIfTI mask to a surface mesh.
    // Output is written to args.output_dir with the same stem as inputFile.
    // Returns true on success.
    [[nodiscard]] bool convert(const fs::path& inputFile) const;

private:
    const MeshConverterArgs& args_;

    // Pipeline steps — each returns the next stage's output.
    // All helpers are stateless (no side-effects on *this).
    [[nodiscard]] static bool isNiftiFile(const fs::path& p);
    [[nodiscard]] static std::string stripNiiStem(const std::string& stem);
    [[nodiscard]] static std::string toLower(std::string s);
    [[nodiscard]] static bool endsWith(const std::string& s, const std::string& suffix);
};
