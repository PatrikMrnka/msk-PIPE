# ── mask_to_mesh ──────────────────────────────────────────────────────────────
# Sub-project: converts segmentation masks to surface meshes using VTK.
# VTK is found by the parent CMakeLists.txt; all outputs go to the shared
# bin/ directory defined there.
# ──────────────────────────────────────────────────────────────────────────────

add_executable(mask_to_mesh main.cpp)

target_link_libraries(mask_to_mesh PRIVATE
  VTK::CommonCore
  VTK::CommonDataModel
  VTK::FiltersCore
  VTK::FiltersGeneral
  VTK::FiltersSources
  VTK::IOImage
  VTK::IOGeometry
)

if(MSVC)
  target_compile_options(mask_to_mesh PRIVATE /W4)
else()
  target_compile_options(mask_to_mesh PRIVATE -Wall -Wextra -Wpedantic)
endif()