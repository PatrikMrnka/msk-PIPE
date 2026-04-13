# -------- CMakeLists.txt --------
cmake_minimum_required(VERSION 3.21)
project(mask_to_mesh LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(VTK 9.0 CONFIG REQUIRED COMPONENTS
  CommonCore
  CommonDataModel
  FiltersCore
  FiltersGeneral
  FiltersSources
  IOImage
  IOGeometry
)

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

add_custom_command(TARGET mask_to_mesh POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          $<TARGET_RUNTIME_DLLS:mask_to_mesh>
          $<TARGET_FILE_DIR:mask_to_mesh>
  COMMAND_EXPAND_LISTS
)