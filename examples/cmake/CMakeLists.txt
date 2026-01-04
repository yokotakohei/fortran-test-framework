cmake_minimum_required(VERSION 3.24)
project(ForTestExamples VERSION 0.1.0 LANGUAGES Fortran)

# Module and binary output directories
set(CMAKE_Fortran_MODULE_DIRECTORY ${CMAKE_BINARY_DIR}/mod)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# Fortran standard
set(CMAKE_Fortran_FLAGS "${CMAKE_Fortran_FLAGS} -std=f2008")

# Fetch fortest-assertions library
include(FetchContent)
FetchContent_Declare(
    fortest-assertions
    GIT_REPOSITORY https://github.com/yokotakohei/fortran-test-framework.git
    GIT_TAG main
    SOURCE_SUBDIR fortran
)
FetchContent_MakeAvailable(fortest-assertions)

# Build the sample module from src/ directory
add_library(sample_module STATIC
    src/module_sample.f90
)
set_target_properties(sample_module PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_Fortran_MODULE_DIRECTORY}
)
target_include_directories(sample_module PUBLIC
    $<BUILD_INTERFACE:${CMAKE_Fortran_MODULE_DIRECTORY}>
)

# Note: Tests are run using the fortest command, not CTest
# After building:
#   $ cmake --build build
#   $ fortest test/
#
# The fortest command will:
# - Auto-detect test files (test_*.f90)
# - Generate test runners automatically
# - Use the fortest::assertions library
# - Use build artifacts from build/mod/ and build/