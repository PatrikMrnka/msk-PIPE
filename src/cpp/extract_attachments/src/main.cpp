#include <iostream>
#include <string>
#include <vector>
#include <cstdlib>
#include <chrono>

#include "AttachmentExtractor.h"

// ----------------------------------------------------------------
// print_usage
// ----------------------------------------------------------------
static void print_usage(const char* prog) {
    std::cerr
        << "Usage:\n"
        << "  " << prog << " <bone.obj> <threshold_mm>"
           " <muscle1.obj> <out1.vtk> [<muscle2.obj> <out2.vtk> ...]\n\n"
        << "Arguments:\n"
        << "  bone.obj       Bone mesh (.obj). Locator is built ONCE.\n"
        << "  threshold_mm   Max distance in mm for attachment detection (e.g. 3.0).\n"
        << "  muscleN.obj    Muscle mesh (.obj) – one or more pairs.\n"
        << "  outN.vtk       Output attachment point cloud (.vtk) for the paired muscle.\n";
}

// ----------------------------------------------------------------
// main
// ----------------------------------------------------------------
int main(int argc, char* argv[]) {
    // Minimum: prog bone threshold muscle1 out1  => 5 args
    // Pairs of (muscle, out) must be even after the first two positional args.
    if (argc < 5 || (argc - 3) % 2 != 0) {
        print_usage(argv[0]);
        return EXIT_FAILURE;
    }

    const std::string bone_path = argv[1];

    // Parse threshold
    double threshold_mm = 0.0;
    try {
        threshold_mm = std::stod(argv[2]);
    } catch (const std::exception& e) {
        std::cerr << "[error] invalid threshold value '" << argv[2]
                  << "': " << e.what() << "\n";
        return EXIT_FAILURE;
    }
    if (threshold_mm <= 0.0) {
        std::cerr << "[error] threshold must be positive, got: " << threshold_mm << "\n";
        return EXIT_FAILURE;
    }

    // Collect (muscle, output) pairs from remaining arguments
    struct Pair { std::string muscle; std::string output; };
    std::vector<Pair> pairs;
    for (int i = 3; i + 1 < argc; i += 2) {
        pairs.push_back({argv[i], argv[i + 1]});
    }

    std::cout << "=== extract_attachments ===\n"
              << "  bone:        " << bone_path << "\n"
              << "  threshold:   " << threshold_mm << " mm\n"
              << "  muscles:     " << pairs.size() << "\n\n";

    // ── Load bone ONCE and build locator ──────────────────────────
    AttachmentExtractor extractor;
    if (!extractor.load_bone(bone_path)) {
        return EXIT_FAILURE;
    }

    // ── Process each muscle ───────────────────────────────────────
    int ok_count = 0;
    std::size_t total_points = 0;

    for (const auto& p : pairs) {
        std::cout << "--- " << p.muscle << " => " << p.output << "\n";

        if (!extractor.load_muscle(p.muscle)) {
            std::cerr << "[warning] skipping muscle (load failed): " << p.muscle << "\n";
            continue;
        }

        auto t0 = std::chrono::high_resolution_clock::now();
        const auto count = extractor.extract(threshold_mm);
        auto t1 = std::chrono::high_resolution_clock::now();
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();

        std::cout << "[info] extraction took " << ms << " ms\n";

        if (count == 0) {
            std::cerr << "[warning] no attachment points for " << p.muscle
                      << " – consider increasing the threshold\n";
            continue;
        }

        if (!extractor.export_vtk(p.output)) {
            std::cerr << "[warning] export failed for: " << p.output << "\n";
            continue;
        }

        ++ok_count;
        total_points += count;
    }

    std::cout << "\n[done] processed " << ok_count << "/" << pairs.size()
              << " muscles – " << total_points << " total attachment points.\n";

    return EXIT_SUCCESS;
}
