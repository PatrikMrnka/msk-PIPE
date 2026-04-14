#include "AttachmentExtractor.h"

#include <iostream>
#include <fstream>
#include <filesystem>
#include <cmath>

#include <vtkOBJReader.h>
#include <vtkStaticCellLocator.h>
#include <vtkGenericCell.h>
#include <vtkPolyData.h>
#include <vtkDoubleArray.h>
#include <vtkPointData.h>
#include <vtkClipPolyData.h>
#include <vtkFeatureEdges.h>
#include <vtkStripper.h>
#include <vtkCellArray.h>
#include <vtkDecimatePolylineFilter.h>

// ----------------------------------------------------------------
// load_bone
//
// Reads the bone .obj mesh, stores it, then immediately builds the
// vtkStaticCellLocator.  This amortises the expensive O(N log N)
// build cost across all muscles that will be tested later.
// ----------------------------------------------------------------
bool AttachmentExtractor::load_bone(const std::string& filepath) {
    if (!std::filesystem::exists(filepath)) {
        std::cerr << "[error] bone mesh file not found: " << filepath << "\n";
        return false;
    }

    auto reader = vtkSmartPointer<vtkOBJReader>::New();
    reader->SetFileName(filepath.c_str());
    reader->Update();

    bone_mesh_ = reader->GetOutput();

    if (!bone_mesh_ || bone_mesh_->GetNumberOfPoints() == 0) {
        std::cerr << "[error] bone mesh is empty or unreadable: " << filepath << "\n";
        return false;
    }

    std::cout << "[info] bone mesh loaded: " << filepath
              << " (" << bone_mesh_->GetNumberOfPoints() << " points, "
              << bone_mesh_->GetNumberOfCells() << " cells)\n";

    // Build the locator ONCE here so every subsequent extract() call
    // can reuse it without any rebuild overhead.
    locator_ = vtkSmartPointer<vtkStaticCellLocator>::New();
    locator_->SetDataSet(bone_mesh_);
    locator_->BuildLocator();

    std::cout << "[info] spatial locator built on bone mesh ("
              << bone_mesh_->GetNumberOfCells() << " cells)\n";

    return true;
}

// ----------------------------------------------------------------
// load_muscle
//
// Reads the muscle .obj mesh and stores it.
// Every vertex of the muscle will be queried in extract().
// ----------------------------------------------------------------
bool AttachmentExtractor::load_muscle(const std::string& filepath) {
    if (!std::filesystem::exists(filepath)) {
        std::cerr << "[error] muscle mesh file not found: " << filepath << "\n";
        return false;
    }

    auto reader = vtkSmartPointer<vtkOBJReader>::New();
    reader->SetFileName(filepath.c_str());
    reader->Update();

    muscle_mesh_ = reader->GetOutput();

    if (!muscle_mesh_ || muscle_mesh_->GetNumberOfPoints() == 0) {
        std::cerr << "[error] muscle mesh is empty or unreadable: " << filepath << "\n";
        return false;
    }

    std::cout << "[info] muscle mesh loaded: " << filepath
              << " (" << muscle_mesh_->GetNumberOfPoints() << " points, "
              << muscle_mesh_->GetNumberOfCells() << " cells)\n";
    return true;
}

// ----------------------------------------------------------------
// extract
//
// Core algorithm (the locator is already built in load_bone):
//
// 1. Compute the distance from every muscle vertex to the nearest
//    point on the bone surface (using the pre-built locator).
// 2. Store the distance as a per-vertex scalar on a copy of the
//    muscle mesh.
// 3. Clip the muscle to keep only the region within the threshold
//    distance (this produces the "attachment patch").
// 4. Extract the boundary edges of the attachment patch.
// 5. Order the edges into a continuous polyline contour.
// 6. Decimate the polyline to reduce the point count.
// 7. Select the longest contour and store its points.
//
// Complexity: O(M) where M = number of muscle vertices (each
//   locator query is O(1) amortised), instead of O(M * N) brute
//   force.
// ----------------------------------------------------------------
std::size_t AttachmentExtractor::extract(double max_distance_mm) {
    if (!bone_mesh_ || !muscle_mesh_) {
        std::cerr << "[error] both bone and muscle meshes must be loaded before extraction\n";
        return 0;
    }
    if (!locator_) {
        std::cerr << "[error] locator not initialised -- call load_bone() first\n";
        return 0;
    }

    attachment_points_ = vtkSmartPointer<vtkPoints>::New();
    const vtkIdType num_muscle_points = muscle_mesh_->GetNumberOfPoints();

    // 1. Compute per-vertex distance to bone and store as point data.
    auto distances = vtkSmartPointer<vtkDoubleArray>::New();
    distances->SetName("DistanceToBone");
    distances->SetNumberOfComponents(1);
    distances->SetNumberOfTuples(num_muscle_points);

    double closest_point[3];
    auto generic_cell = vtkSmartPointer<vtkGenericCell>::New();
    vtkIdType cell_id;
    int sub_id;
    double dist2;

    for (vtkIdType i = 0; i < num_muscle_points; ++i) {
        double muscle_point[3];
        muscle_mesh_->GetPoint(i, muscle_point);
        locator_->FindClosestPoint(muscle_point, closest_point, generic_cell, cell_id, sub_id, dist2);

        // Store the actual distance (not squared) because the clip filter
        // operates on exact values.
        distances->SetValue(i, std::sqrt(dist2));
    }

    // Deep-copy the muscle so we can safely attach the distance scalars.
    auto muscle_copy = vtkSmartPointer<vtkPolyData>::New();
    muscle_copy->DeepCopy(muscle_mesh_);
    muscle_copy->GetPointData()->SetScalars(distances);

    // 2. Clip the muscle to keep only the patch closer than the threshold.
    auto clipper = vtkSmartPointer<vtkClipPolyData>::New();
    clipper->SetInputData(muscle_copy);
    clipper->SetValue(max_distance_mm);
    clipper->InsideOutOn();  // keep values LESS than the threshold
    clipper->Update();

    auto attached_patch = clipper->GetOutput();
    if (attached_patch->GetNumberOfPoints() == 0) {
        return 0;  // muscle is not within range of the bone
    }

    // 3. Extract the boundary edges of the attachment patch.
    auto edges = vtkSmartPointer<vtkFeatureEdges>::New();
    edges->SetInputData(attached_patch);
    edges->BoundaryEdgesOn();
    edges->FeatureEdgesOff();
    edges->NonManifoldEdgesOff();
    edges->ManifoldEdgesOff();
    edges->Update();

    // 4. Order the scattered edges into a smooth polyline contour.
    auto stripper = vtkSmartPointer<vtkStripper>::New();
    stripper->SetInputConnection(edges->GetOutputPort());

    // 5. Decimate the polyline to reduce the number of points.
    auto decimator = vtkSmartPointer<vtkDecimatePolylineFilter>::New();
    decimator->SetInputConnection(stripper->GetOutputPort());
    decimator->SetTargetReduction(0.90);  // remove 90% of the points
    decimator->Update();

    auto boundary = decimator->GetOutput();
    auto lines = boundary->GetLines();

    if (lines->GetNumberOfCells() == 0) {
        return 0;
    }

    // Walk through the contours (there may be more than one if the
    // attachment area is fragmented) and pick the longest one.
    vtkIdType max_points = 0;
    const vtkIdType* best_pts = nullptr;
    vtkIdType npts;
    const vtkIdType* pts;

    lines->InitTraversal();
    while (lines->GetNextCell(npts, pts)) {
        if (npts > max_points) {
            max_points = npts;
            best_pts = pts;
        }
    }

    if (max_points > 0 && best_pts != nullptr) {
        // Avoid a duplicate closing point (first == last).
        vtkIdType num_unique = max_points;
        if (max_points > 1 && best_pts[0] == best_pts[max_points - 1]) {
            num_unique = max_points - 1;
        }

        // Store the ordered contour points.
        for (vtkIdType i = 0; i < num_unique; ++i) {
            double p[3];
            boundary->GetPoint(best_pts[i], p);
            attachment_points_->InsertNextPoint(p);
        }
    }

    const auto count = static_cast<std::size_t>(attachment_points_->GetNumberOfPoints());
    std::cout << "[info] extraction complete: ordered contour contains " << count << " points.\n";

    return count;
}

// ----------------------------------------------------------------
// export_vtk
//
// Writes attachment points to a legacy ASCII VTK 3.0 file that is
// compatible with OpenSim MuscleGeneratorTool.
// ----------------------------------------------------------------
bool AttachmentExtractor::export_vtk(const std::string& output_path) const {
    if (!attachment_points_ || attachment_points_->GetNumberOfPoints() == 0) {
        std::cerr << "[warning] no attachment points to export\n";
        return false;
    }

    const vtkIdType num_points = attachment_points_->GetNumberOfPoints();

    // Ensure parent directories exist.
    std::filesystem::path out_p(output_path);
    if (out_p.has_parent_path()) {
        std::filesystem::create_directories(out_p.parent_path());
    }

    std::ofstream ofs(output_path);
    if (!ofs.is_open()) {
        std::cerr << "[error] cannot open output file for writing: " << output_path << "\n";
        return false;
    }

    // --- header ---
    ofs << "# vtk DataFile Version 3.0\n";
    ofs << "vtk output\n";
    ofs << "ASCII\n";
    ofs << "DATASET POLYDATA\n";

    // --- POINTS section (3 points per line) ---
    ofs << "POINTS " << num_points << " float\n";
    int coords_on_line = 0;
    for (vtkIdType i = 0; i < num_points; ++i) {
        double pt[3];
        attachment_points_->GetPoint(i, pt);
        ofs << pt[0] << " " << pt[1] << " " << pt[2] << " ";
        if (++coords_on_line >= 3) {
            ofs << "\n";
            coords_on_line = 0;
        }
    }
    if (coords_on_line > 0) ofs << "\n";

    // --- VERTICES section (legacy 3.0 style) ---
    ofs << "VERTICES " << num_points << " " << (num_points * 2) << "\n";
    for (vtkIdType i = 0; i < num_points; ++i) {
        ofs << "1 " << i << " \n";
    }

    // --- CELL_DATA + POINT_DATA ---
    ofs << "\nCELL_DATA " << num_points << "\n";
    ofs << "POINT_DATA " << num_points << "\n";
    ofs << "SCALARS scalars bit\n";
    ofs << "LOOKUP_TABLE default\n";
    for (vtkIdType i = 0; i < num_points; ++i) {
        ofs << "1";
        if ((i + 1) % 8 == 0 || i == num_points - 1) ofs << "\n";
        else ofs << " ";
    }

    ofs << "\n";
    ofs.close();

    std::cout << "[info] exported " << num_points
              << " attachment points (legacy vtk 3.0) to: " << output_path << "\n";
    return true;
}

// ----------------------------------------------------------------
// attachment_point_count
// ----------------------------------------------------------------
std::size_t AttachmentExtractor::attachment_point_count() const {
    if (!attachment_points_) return 0;
    return static_cast<std::size_t>(attachment_points_->GetNumberOfPoints());
}
