---
project: fortest-assertions
summary: Fortran assertion library for testing
author: yokotakohei
github: https://github.com/yokotakohei/fortran-test-framework
project_github: https://github.com/yokotakohei/fortran-test-framework
project_download: https://github.com/yokotakohei/fortran-test-framework/releases
license: mit
src_dir: ./src
output_dir: ./doc
page_dir: ./pages
media_dir: ./media
exclude_dir: ./build
exclude: CMakeLists.txt
preprocess: false
display: public
         protected
         private
source: true
graph: true
search: true
macro: TEST
       LOGIC=.true.
extra_mods: iso_fortran_env:https://gcc.gnu.org/onlinedocs/gfortran/ISO_005fFORTRAN_005fENV.html
            iso_c_binding:https://gcc.gnu.org/onlinedocs/gfortran/ISO_005fC_005fBINDING.html
---

# fortest-assertions

Fortran assertion library for testing.

## Overview

fortest-assertions provides a comprehensive set of assertion functions for Fortran testing. It supports:

- Integer assertions
- Real assertions with tolerance
- Logical assertions
- Character assertions  
- Array assertions for all numeric types

## Installation

### Using CMake

```cmake
include(FetchContent)

FetchContent_Declare(
    fortest-assertions
    GIT_REPOSITORY https://github.com/yokotakohei/fortran-test-framework.git
    GIT_TAG main
    SOURCE_SUBDIR fortran
)
FetchContent_MakeAvailable(fortest-assertions)

target_link_libraries(your_target PRIVATE fortest::assertions)
```

### Using FPM

```toml
[dependencies]
fortest-assertions = { git = "https://github.com/yokotakohei/fortran-test-framework.git", path = "fortran" }
```

## Usage

```fortran
program test_example
    use fortest_assertions
    use iso_fortran_env, only: int32, real64
    implicit none

    integer(int32) :: a, b
    real(real64) :: x, y

    a = 5
    b = 5
    call assert_equal(a, b, "integers should be equal")

    x = 3.14159d0
    y = 3.14159d0
    call assert_equal(x, y, "reals should be equal", tol=1.0d-10)

    call print_summary()
end program test_example
```

## API Documentation

See the module documentation for detailed API reference.