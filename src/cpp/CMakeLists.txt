# ── Top-level CMakeLists.txt for all C++ tools ────────────────────────────────
# Builds mask_to_mesh and extract_attachments in a single CMake project,
# sharing VTK discovery and placing all binaries + runtime DLLs into a
# common output directory (build/bin/).  This avoids duplicating VTK DLLs
# in each sub-project's Release folder.
# ──────────────────────────────────────────────────────────────────────────────

cmake_minimum_required(VERSION 3.21)
project(msk_cpp_tools LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Shared output directories ─────────────────────────────────────────────────
# Put all executables and DLLs side-by-side so the runtime linker can
# find VTK DLLs without per-target post-build copies.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE ${CMAKE_BINARY_DIR}/bin/Release)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_DEBUG ${CMAKE_BINARY_DIR}/bin/Debug)

# ── VTK (single shared find_package for all sub-projects) ─────────────────────
find_package(VTK 9.0 CONFIG REQUIRED COMPONENTS
  CommonCore
  CommonDataModel
  FiltersCore
  FiltersGeneral
  FiltersSources
  IOImage
  IOGeometry
)

# ── Sub-projects ──────────────────────────────────────────────────────────────
add_subdirectory(mask_to_mesh/src)
add_subdirectory(extract_attachments/src)

# ── Single post-build DLL copy (runs after the last target) ───────────────────
# We create a dummy custom target that depends on both executables and
# copies VTK runtime DLLs once into the shared output directory.
add_custom_target(copy_vtk_dlls ALL
  DEPENDS mask_to_mesh extract_attachments
)

add_custom_command(TARGET copy_vtk_dlls POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          $<TARGET_RUNTIME_DLLS:mask_to_mesh>
          $<TARGET_FILE_DIR:mask_to_mesh>
  COMMAND_EXPAND_LISTS
  COMMENT "Copying VTK runtime DLLs to shared output directory"
)
