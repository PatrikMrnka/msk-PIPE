# ── mask_to_mesh ──────────────────────────────────────────────────────────────
# Sub-project: converts segmentation masks to surface meshes using VTK.
# VTK is found by the parent CMakeLists.txt; all outputs go to the shared
# bin/ directory defined there.
#
# File layout (mirrors extract_attachments):
#   main.cpp            — CLI parsing and dispatch only
#   MeshConverter.h/.cpp — VTK pipeline (readNifti, smooth, decimate, write)
# ──────────────────────────────────────────────────────────────────────────────

add_executable(mask_to_mesh
    main.cpp
    MeshConverter.cpp
)

target_link_libraries(mask_to_mesh PRIVATE
  VTK::CommonCore
  VTK::CommonDataModel
  VTK::FiltersCore
  VTK::FiltersGeneral
  VTK::FiltersModeling
  VTK::FiltersSources
  VTK::IOImage
  VTK::IOGeometry
)

# vtk module auto-init (required for vtk 9+ factory registration)
vtk_module_autoinit(
    TARGETS mask_to_mesh
    MODULES ${VTK_LIBRARIES}
)

if(MSVC)
  target_compile_options(mask_to_mesh PRIVATE /W4)
else()
  target_compile_options(mask_to_mesh PRIVATE -Wall -Wextra -Wpedantic)
endif()