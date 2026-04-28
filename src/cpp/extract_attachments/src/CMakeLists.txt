# ── extract_attachments ───────────────────────────────────────────────────────
# Sub-project: extracts muscle attachment points from bone meshes using VTK.
# VTK is found by the parent CMakeLists.txt; all outputs go to the shared
# bin/ directory defined there.
# ──────────────────────────────────────────────────────────────────────────────

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