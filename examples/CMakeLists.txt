cmake_minimum_required(VERSION 3.10)
project(ForTestExamples Fortran)

# Enable testing
enable_testing()

# Fetch fortest assertions module
include(FetchContent)

FetchContent_Declare(
    fortest-assertions
    GIT_REPOSITORY https://github.com/yokotakohei/fortran-test-framework.git
    GIT_TAG main
    SOURCE_SUBDIR fortran
)
FetchContent_MakeAvailable(fortest-assertions)

# Build the sample module from src/ directory
add_library(sample_module src/module_sample.f90)
target_include_directories(sample_module PUBLIC ${CMAKE_CURRENT_BINARY_DIR})

# Build the test executable from test/ directory
add_executable(test_module_sample
    test/test_module_sample.f90
    test/run_tests.f90
)
target_link_libraries(test_module_sample 
    PRIVATE 
        sample_module
        fortest::assertions
)

# Add test
add_test(NAME sample_module_tests COMMAND test_module_sample)

# Note: You can also run tests using the fortest command:
# pip install fortest
# fortest test/
