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
// Core algorithm (locator is already built in load_bone):
//
// 1. Iterate over every vertex in the muscle mesh.
// 2. For each vertex, query the pre-built locator for the closest
//    point on the bone surface.
// 3. vtkStaticCellLocator::FindClosestPoint returns the squared
//    distance (dist2). Compare against threshold_sq to avoid sqrt
//    on every iteration.
// 4. Accepted vertices are added to attachment_points_.
//
// Complexity: O(M) where M = muscle vertices,
// instead of O(M * N) brute-force.
// ----------------------------------------------------------------
std::size_t AttachmentExtractor::extract(double max_distance_mm) {
    if (!bone_mesh_ || !muscle_mesh_) {
        std::cerr << "[error] both bone and muscle meshes must be loaded before extraction\n";
        return 0;
    }
    if (!locator_) {
        std::cerr << "[error] locator not initialised – call load_bone() first\n";
        return 0;
    }

    attachment_points_ = vtkSmartPointer<vtkPoints>::New();
    const vtkIdType num_muscle_points = muscle_mesh_->GetNumberOfPoints();

    // 1. Spočítáme vzdálenosti a uložíme je jako Point Data svalu
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
        
        // Vkládáme skutečnou vzdálenost (ne kvadrát), protože clip pracuje s přesnými hodnotami
        distances->SetValue(i, std::sqrt(dist2)); 
    }
    
    // Kopie svalu pro bezpečné modifikace skalárů
    auto muscle_copy = vtkSmartPointer<vtkPolyData>::New();
    muscle_copy->DeepCopy(muscle_mesh_);
    muscle_copy->GetPointData()->SetScalars(distances);

    // 2. Vyřízneme "záplatu" svalu, která je blíže než max_distance_mm
    auto clipper = vtkSmartPointer<vtkClipPolyData>::New();
    clipper->SetInputData(muscle_copy);
    clipper->SetValue(max_distance_mm);
    clipper->InsideOutOn(); // InsideOutOn znamená, že chceme zachovat hodnoty MENŠÍ než threshold
    clipper->Update();

    auto attached_patch = clipper->GetOutput();
    if (attached_patch->GetNumberOfPoints() == 0) {
        return 0; // Sval není v dosahu kosti
    }

    // 3. Extrahujeme obvodové hrany záplaty
    auto edges = vtkSmartPointer<vtkFeatureEdges>::New();
    edges->SetInputData(attached_patch);
    edges->BoundaryEdgesOn();
    edges->FeatureEdgesOff();
    edges->NonManifoldEdgesOff();
    edges->ManifoldEdgesOff();
    edges->Update();

    // 4. Seřadíme rozházené hrany do plynulé polyline kontury
    auto stripper = vtkSmartPointer<vtkStripper>::New();
    stripper->SetInputConnection(edges->GetOutputPort());
    // Nepoužijeme hned Update(), ale napojíme další filtr

    // 5. Redukce počtu bodů (Decimace)
    auto decimator = vtkSmartPointer<vtkDecimatePolylineFilter>::New();
    decimator->SetInputConnection(stripper->GetOutputPort());
    decimator->SetTargetReduction(0.90); // 90 % of points will be removed
    decimator->Update();

    // Výstup si nyní vezmeme z decimátoru
    auto boundary = decimator->GetOutput();
    auto lines = boundary->GetLines();
    
    if (lines->GetNumberOfCells() == 0) {
        return 0;
    }

    // Procházíme nalezené kontury (může jich být více, pokud je úpon roztříštěný)
    // Vybereme tu nejdelší, což je obvykle hlavní úponová oblast.
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
        // Kontrola duplicity prvního a posledního bodu (aby křivka nebyla explicitně uzavřená bodem navíc)
        vtkIdType num_unique = max_points;
        if (max_points > 1 && best_pts[0] == best_pts[max_points - 1]) {
            num_unique = max_points - 1;
        }

        // Naplnění výsledných uspořádaných bodů
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
