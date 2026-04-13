cmake_minimum_required(VERSION 3.21)
project(extract_attachments LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -----------------------------------------------------------------
# find the vtk library – VTK_DIR is typically passed via cmake cli:
#   cmake -S src -B build -DVTK_DIR=<path_to_vtk_cmake_config>
# -----------------------------------------------------------------
find_package(VTK REQUIRED COMPONENTS
    CommonCore
    CommonDataModel
    FiltersGeneral
    FiltersCore
    IOGeometry
)

# -----------------------------------------------------------------
# define the executable from sources in the current (src) directory
# -----------------------------------------------------------------
add_executable(extract_attachments
    main.cpp
    AttachmentExtractor.cpp
)

target_link_libraries(extract_attachments PRIVATE ${VTK_LIBRARIES})

# vtk module auto-init (required for vtk 9+ factory registration)
vtk_module_autoinit(
    TARGETS extract_attachments
    MODULES ${VTK_LIBRARIES}
)

add_custom_command(TARGET extract_attachments POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          $<TARGET_RUNTIME_DLLS:extract_attachments>
          $<TARGET_FILE_DIR:extract_attachments>
  COMMAND_EXPAND_LISTS
)