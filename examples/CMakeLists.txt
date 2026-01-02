cmake_minimum_required(VERSION 3.10)
project(ForTestExamples Fortran)

# Enable testing
enable_testing()

# Find the fortest assertions module
# Assumes fortest is installed via pip or the source is in parent directory
set(FORTEST_MODULE_DIR "${CMAKE_SOURCE_DIR}/../fortest")

# Build the sample module from src/ directory
add_library(sample_module src/module_sample.f90)
target_include_directories(sample_module PUBLIC ${CMAKE_CURRENT_BINARY_DIR})

# Build the test executable from test/ directory
add_executable(test_module_sample
    ${FORTEST_MODULE_DIR}/module_fortest_assertions.f90
    test/test_module_sample.f90
    test/run_tests.f90
)
target_link_libraries(test_module_sample sample_module)
target_include_directories(test_module_sample PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

# Add test
add_test(NAME sample_module_tests COMMAND test_module_sample)

# Note: You can also run tests using the fortest command:
# fortest test/test_module_sample.f90
