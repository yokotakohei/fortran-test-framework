cmake_minimum_required(VERSION 3.15)
project(fortest-assertions VERSION 0.1.0 LANGUAGES Fortran)

# Create library target
add_library(fortest-assertions
    src/module_fortest_assertions.f90
)

# Set module directory
set_target_properties(fortest-assertions PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod
)

# Include directories for module files
target_include_directories(fortest-assertions
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/mod>
        $<INSTALL_INTERFACE:include/fortest>
)

# Create alias for FetchContent usage (fortest::assertions)
add_library(fortest::assertions ALIAS fortest-assertions)

# Installation rules
include(GNUInstallDirs)

# Install library
install(TARGETS fortest-assertions
    EXPORT fortest-assertions-targets
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

# Install module files
install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod/
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/fortest
    FILES_MATCHING PATTERN "*.mod"
)

# Install source files (for FPM compatibility)
install(FILES src/module_fortest_assertions.f90
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/fortest
)

# Export targets
install(EXPORT fortest-assertions-targets
    FILE fortest-assertions-targets.cmake
    NAMESPACE fortest::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/fortest-assertions
)

# Note: For FetchContent usage, the alias fortest::assertions is available.
# For find_package() support after installation, create cmake/fortest-assertions-config.cmake.in

# Create alias for use as a subdirectory
add_library(fortest::assertions ALIAS fortest-assertions)
