#pragma once

#include <string>
#include <vector>
#include <memory>
#include <cmath>

#include <vtkSmartPointer.h>
#include <vtkPolyData.h>
#include <vtkPoints.h>
#include <vtkStaticCellLocator.h>

// ────────────────────────────────────────────────────────────────────────────
// AttachmentExtractor
//
// Encapsulates the workflow for finding muscle-to-bone attachment points via
// proximity queries on dense meshes.
//
// Optimized batch usage: load the bone ONCE, then call load_muscle() /
// extract() / export_vtk() for every muscle:
//
//   AttachmentExtractor ex;
//   ex.load_bone("pelvis.obj");            // Builds locator here
//   for each muscle:
//     ex.load_muscle("iliacus.obj");
//     ex.extract(3.0, 0.25);
//     ex.export_vtk("Iliacus_Ori.vtk");
//
// ────────────────────────────────────────────────────────────────────────────
class AttachmentExtractor {
public:
    AttachmentExtractor() = default;
    ~AttachmentExtractor() = default;

    // non-copyable, movable
    AttachmentExtractor(const AttachmentExtractor&) = delete;
    AttachmentExtractor& operator=(const AttachmentExtractor&) = delete;
    AttachmentExtractor(AttachmentExtractor&&) = default;
    AttachmentExtractor& operator=(AttachmentExtractor&&) = default;

    // Load the bone mesh from an .obj file.
    // Immediately builds the vtkStaticCellLocator so subsequent
    // extract() calls are O(1) for the build step.
    bool load_bone(const std::string& filepath);

    // Load the muscle mesh from an .obj file.
    // Every vertex of this mesh will be tested against the bone
    // surface during the next extract() call.
    bool load_muscle(const std::string& filepath);

    // Run proximity extraction.
    // For every muscle vertex within max_distance_mm of the bone
    // surface, the point is added to the internal result set.
    // Returns the number of attachment points found.
    std::size_t extract(double max_distance_mm, double clip_fraction);

    // Export the collected attachment points to a legacy ASCII .vtk
    // file compatible with OpenSim MuscleGeneratorTool.
    bool export_vtk(const std::string& output_path) const;

    // Return the number of attachment points found after extraction.
    std::size_t attachment_point_count() const;

private:
    vtkSmartPointer<vtkPolyData>            bone_mesh_;
    vtkSmartPointer<vtkPolyData>            muscle_mesh_;
    vtkSmartPointer<vtkPoints>              attachment_points_;
    vtkSmartPointer<vtkStaticCellLocator>   locator_;   // pre-built in load_bone()
};