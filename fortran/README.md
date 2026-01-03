# Fortran Assertions Module

This directory contains the Fortran assertion module for the fortest testing framework.

## Installation

### Using CMake (FetchContent)

```cmake
include(FetchContent)

FetchContent_Declare(
    fortest-assertions
    GIT_REPOSITORY https://github.com/yokotakohei/fortran-test-framework.git
    GIT_TAG main
    SOURCE_SUBDIR fortran
)
FetchContent_MakeAvailable(fortest-assertions)

# Link to your test executable
add_executable(my_tests test/test_mymodule.f90)
target_link_libraries(my_tests PRIVATE fortest::assertions)
```

### Using FPM

Add to your `fpm.toml`:

```toml
[dependencies]
fortest-assertions = { git = "https://github.com/yokotakohei/fortran-test-framework.git", path = "fortran" }
```

## Usage

```fortran
program test_example
    use fortest_assertions
    implicit none
    
    call assert_equal(2 + 2, 4, "Addition test")
    call assert_true(.true., "Logical test")
    
    call print_summary()
end program test_example
```

## Building Standalone

```bash
cd fortran
mkdir build && cd build
cmake ..
make
make install
```

## API

See the parent README.md for the full API documentation.
