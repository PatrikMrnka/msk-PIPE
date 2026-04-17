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
#include <vtkSplineFilter.h>
#include <vtkBox.h>

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
std::size_t AttachmentExtractor::extract(double max_distance_mm, double clip_fraction) {
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

    // ====================================================================
    // --- KROK 2.5: Odstranění střední části svalu (vyříznutí bříška) ---
    // ====================================================================
    
    // Získáme absolutní rozměry celého svalu
    double bounds[6];
    muscle_mesh_->GetBounds(bounds); 
    // bounds indexy: [xmin, xmax, ymin, ymax, zmin, zmax]
    double z_min = bounds[4];
    double z_max = bounds[5];
    double z_range = z_max - z_min;

    // Chceme zachovat clip_fraction nahoře a clip_fraction dole.
    // Vše mezi tím (střed) vyřízneme.

    // Vytvoříme virtuální 3D box, který reprezentuje střed svalu.
    // Pro osy X a Y nastavíme obrovský přesah, abychom ořezávali čistě jen podle výšky Z.
    double box_bounds[6];
    box_bounds[0] = bounds[0] - 1000.0; 
    box_bounds[1] = bounds[1] + 1000.0;
    box_bounds[2] = bounds[2] - 1000.0; 
    box_bounds[3] = bounds[3] + 1000.0;
    box_bounds[4] = z_min + (clip_fraction * z_range); // Spodní hranice řezu
    box_bounds[5] = z_max - (clip_fraction * z_range); // Horní hranice řezu

    auto box = vtkSmartPointer<vtkBox>::New();
    box->SetBounds(box_bounds);

    auto box_clipper = vtkSmartPointer<vtkClipPolyData>::New();
    box_clipper->SetInputData(attached_patch);
    box_clipper->SetClipFunction(box);
    
    // vtkBox definuje prostor UVNITŘ jako záporné hodnoty.
    // vtkClipPolyData standardně zachovává Kladné hodnoty (tj. to, co je VENKU z boxu).
    // Výsledkem tedy budou jen ty části dotykové plochy, které leží nad nebo pod boxem.
    box_clipper->InsideOutOff(); 
    box_clipper->Update();

    // Přepíšeme náš patch
    attached_patch = box_clipper->GetOutput(); 

    if (attached_patch->GetNumberOfPoints() == 0) {
        std::cerr << "[warning] Po vyriznuti stredu svalu nezbyly zadne body uponu.\n";
        return 0;
    }
    // ====================================================================

    // 3. Extract the boundary edges of the attachment patch.
    auto edges = vtkSmartPointer<vtkFeatureEdges>::New();
    edges->SetInputData(attached_patch);
    edges->BoundaryEdgesOn();
    edges->FeatureEdgesOff();
    edges->NonManifoldEdgesOff();
    edges->ManifoldEdgesOff();
    edges->Update();

 // 4. Seřazení rozházených hran do plynulé kontury (polyline)
    auto stripper = vtkSmartPointer<vtkStripper>::New();
    stripper->SetInputConnection(edges->GetOutputPort());
    stripper->Update();

    auto boundary = stripper->GetOutput();
    auto lines = boundary->GetLines();

    if (lines->GetNumberOfCells() == 0) {
        return 0;
    }

    // 5. Nalezení nejdelší kontury (eliminace drobných artefaktů)
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

    if (max_points < 3 || best_pts == nullptr) {
        return 0; // Příliš malá kontura
    }

    // Vytvoření samostatného PolyData pouze s tou nejdelší linií
    auto singleLine = vtkSmartPointer<vtkPolyData>::New();
    singleLine->SetPoints(boundary->GetPoints());
    auto cellArray = vtkSmartPointer<vtkCellArray>::New();
    cellArray->InsertNextCell(max_points, best_pts);
    singleLine->SetLines(cellArray);

    // 6. Vyhlazení a ROVNOMĚRNÉ převzorkování kontury pomocí Spline filtru
    // Místo decimace (která ničí rozestupy) vytvoříme plynulou křivku.
    int desired_points = 50; // Počet bodů, které definují finální úpon (lze parametrizovat)
    
    auto splineFilter = vtkSmartPointer<vtkSplineFilter>::New();
    splineFilter->SetInputData(singleLine);
    splineFilter->SetSubdivideToSpecified();
    splineFilter->SetNumberOfSubdivisions(desired_points);
    splineFilter->Update();

    auto smoothLine = splineFilter->GetOutput();
    const vtkIdType num_smooth_points = smoothLine->GetNumberOfPoints();


    for (vtkIdType i = 0; i < num_smooth_points; ++i) {
        double pt[3], closest_point[3];
        smoothLine->GetPoint(i, pt);
        
        // Použití již předpočítaného lokátoru kosti
        locator_->FindClosestPoint(pt, closest_point, generic_cell, cell_id, sub_id, dist2);
        
        attachment_points_->InsertNextPoint(closest_point);
    }

    const auto count = static_cast<std::size_t>(attachment_points_->GetNumberOfPoints());
    std::cout << "[info] extraction complete: smooth contour projected with " << count << " points.\n";

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