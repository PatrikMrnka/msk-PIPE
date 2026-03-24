# -------- CMakeLists.txt --------
# Minimal CMake project for ts2stl-staple
cmake_minimum_required(VERSION 3.20)
project(mask2stl LANGUAGES CXX)

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

add_executable(mask2stl main.cpp)

target_link_libraries(mask2stl PRIVATE
  VTK::CommonCore
  VTK::CommonDataModel
  VTK::FiltersCore
  VTK::FiltersGeneral
  VTK::FiltersSources
  VTK::IOImage
  VTK::IOGeometry
)

if(MSVC)
  target_compile_options(mask2stl PRIVATE /W4)
else()
  target_compile_options(mask2stl PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Zkopiruje vsechny runtime DLL (VC++ + VTK + dalsi) vedle exe.
add_custom_command(TARGET mask2stl POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          $<TARGET_RUNTIME_DLLS:mask2stl>
          $<TARGET_FILE_DIR:mask2stl>
  COMMAND_EXPAND_LISTS
)