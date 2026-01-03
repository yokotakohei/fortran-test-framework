# fortest - Testing Framework for Fortran

A testing framework for Fortran with automated test discovery and execution, powered by Python.


## Features

- Assertion functions for integers, reals, doubles, logicals, strings, and arrays
- Automatic detection and handling of error stop in tests
- Automatic test discovery for files matching `test_*.f90` pattern
- Python-based test runner for flexible test discovery and execution
- Integration with CMake and FPM build systems


## Architecture

fortest consists of two components:

1. **Python runner** (installed via pip): Test discovery and execution engine
2. **Fortran assertions** (installed via CMake/FPM): Assertion functions used in test code


## Installation

### 1. Install Python Runner

#### From GitHub

```bash
pip install git+https://github.com/yokotakohei/fortran-test-framework.git#subdirectory=fortest
```

#### For Development

Clone the repository and install in editable mode:

```bash
git clone https://github.com/yokotakohei/fortran-test-framework.git
cd fortran-test-framework
pip install -e fortest/
```

### 2. Install Fortran Assertions

Choose one method based on your build system:

#### Using CMake (FetchContent)

Add to your `CMakeLists.txt`:

```cmake
include(FetchContent)

FetchContent_Declare(
    fortest-assertions
    GIT_REPOSITORY https://github.com/yokotakohei/fortran-test-framework.git
    GIT_TAG main
    SOURCE_SUBDIR fortran
)
FetchContent_MakeAvailable(fortest-assertions)
```

#### Using FPM

Add to your `fpm.toml`:

```toml
[dependencies]
fortest-assertions = { git = "https://github.com/yokotakohei/fortran-test-framework.git" }
```


## Quick Start

### Test File Naming

fortest automatically discovers test files matching these patterns:
- `test_*.f90`
- `module_test_*.f90`

Test subroutines containing `error_stop` in their name are treated as error-stop tests (see section [Testing Error Stops](#testing-error-stops)).

### 1. Write your Fortran code

```fortran
! module_sample.f90
module sample_module
    use iso_fortran_env, only: real32, int32
    implicit none

contains

    function add_integers(a, b) result(c)
        integer(int32), intent(in) :: a, b
        integer(int32) :: c
        c = a + b
    end function add_integers

end module sample_module
```

### 2. Write your tests

```fortran
! test_module_sample.f90
module test_sample_module
    use fortest_assertions
    use module_sample
    implicit none

contains

    subroutine test_addition()
        integer(int32) :: result
        result = add_integers(2, 3)
        call assert_equal(result, 5_int32, "2 + 3 should equal 5")
    end subroutine test_addition

end module test_sample_module
```

### 3. Run your tests

```bash
fortest
```

Or specify a directory:

```bash
fortest path/to/tests/
```

Or with verbose output:

```bash
fortest -v
```


## Available Assertions

### Basic Assertions

#### Integer Types

Supports `int8`, `int16`, `int32`, and `int64` from `iso_fortran_env`:

```fortran
use fortest_assertions
use iso_fortran_env, only: int8, int16, int32, int64

! int8 comparison
call assert_equal(actual_i8, expected_i8, "test name")

! int16 comparison
call assert_equal(actual_i16, expected_i16, "test name")

! int32 comparison
call assert_equal(actual_i32, expected_i32, "test name")

! int64 comparison
call assert_equal(actual_i64, expected_i64, "test name")
```

#### Real Types

Supports `real32` and `real64` with optional tolerance:

```fortran
use iso_fortran_env, only: real32, real64

! real32 comparison (with optional tolerance)
call assert_equal(actual_r32, expected_r32, "test name", tol=1.0e-6)

! real64 comparison (with optional tolerance)
call assert_equal(actual_r64, expected_r64, "test name", tol=1.0d-12)
```

#### Complex Types

Supports `complex(real32)` and `complex(real64)` with optional tolerance:

```fortran
! complex(real32) comparison
call assert_equal(actual_c32, expected_c32, "test name", tol=1.0e-6)

! complex(real64) comparison
call assert_equal(actual_c64, expected_c64, "test name", tol=1.0d-12)
```

Note: For complex numbers, both real and imaginary parts must satisfy the tolerance.

#### Logical and Character Types

```fortran
! Logical comparison
call assert_equal(actual_bool, expected_bool, "test name")

! Character comparison (exact match)
call assert_equal(actual_str, expected_str, "test name")

! Logical assertions
call assert_true(condition, "test name")
call assert_false(condition, "test name")
```

### Array Assertions

#### Integer Arrays

```fortran
! int8 array
call assert_array_equal(actual_arr_i8, expected_arr_i8, "test name")

! int16 array
call assert_array_equal(actual_arr_i16, expected_arr_i16, "test name")

! int32 array
call assert_array_equal(actual_arr_i32, expected_arr_i32, "test name")

! int64 array
call assert_array_equal(actual_arr_i64, expected_arr_i64, "test name")
```

#### Real Arrays

```fortran
! real32 array (with optional tolerance)
call assert_array_equal(actual_arr_r32, expected_arr_r32, "test name", tol=1.0e-6)

! real64 array (with optional tolerance)
call assert_array_equal(actual_arr_r64, expected_arr_r64, "test name", tol=1.0d-12)
```

#### Complex Arrays

```fortran
! complex(real32) array (with optional tolerance)
call assert_array_equal(actual_arr_c32, expected_arr_c32, "test name", tol=1.0e-6)

! complex(real64) array (with optional tolerance)
call assert_array_equal(actual_arr_c64, expected_arr_c64, "test name", tol=1.0d-12)
```

#### Character Arrays

```fortran
! character array (exact match, no trimming)
call assert_array_equal(actual_arr_str, expected_arr_str, "test name")
```


## Testing Error Stops

fortest can automatically detect when a test subroutine correctly triggers `error stop`.

Name your test subroutine with `error_stop` in the name:

```fortran
! test_module_sample.f90
module test_sample_module
    use my_module
    implicit none

contains

    subroutine test_error_stop_divide_by_zero()
        ! This will trigger error stop, which is expected
        call divide_by_zero(0.0)
    end subroutine test_error_stop_divide_by_zero

end module test_sample_module
```

When a test subroutine name contains `error_stop`, fortest will:
1. Run it in isolation
2. Detect that the test caused an error stop
3. Mark the test as **PASSED** (because error stop was expected)
4. Continue running other tests


## Examples

See the `examples/` directory for complete working examples with both CMake and FPM.

### CMake Example

```bash
cd examples
cmake -S . -B build
cmake --build build
fortest test/
```

### FPM Example

```bash
cd examples
fpm build
fortest test/
```

### How fortest Works

After building your project (with either CMake or FPM), `fortest` automatically:
- Discovers test files (`test_*.f90`)
- Generates test runners
- Compiles tests using build artifacts from `build/`
- Executes all tests

## Command Line Options

```bash
fortest [pattern] [options]

Arguments:
  pattern              Directory or file pattern to search for tests
                       (default: current directory)

Options:
  --compiler COMPILER  Fortran compiler to use (default: gfortran)
  -v, --verbose       Verbose output showing compilation commands
  -h, --help          Show help message
```


## Output Example

```
Running Fortran tests...

Testing: examples/test/test_module_sample.f90
------------------------------------------------------------
[PASS] add_integers(2, 3) should return 5
[PASS] multiply_real(0.0, 100.0) should return 0.0
[FAIL] multiply_real(0.0, 100.0) should return 0.0
       expected = 1.00000000 vs actual = 0.00000000
[PASS] divide_integer(4, 2) should return 2
[FAIL] test_divide_integer_zero_division_fail
       Test caused error stop or abnormal termination (exit code 1)
[PASS] is_positive(42) should return true
[PASS] is_positive(-7) should return false

==================================================
Normal tests: 6
[PASS]   4
[FAIL]   2
==================================================

[PASS] test_error_stop_divide_integer_zero_division

==================================================
error_stop tests: 1
[PASS]   1
[FAIL]   0
==================================================


------------------------------------------------------------
All tests completed.
==================================================
Total tests: 7
[PASS]   5
[FAIL]   2
==================================================

Some tests failed ✗
```


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Author

Kohei Yokota

## Repository

https://github.com/yokotakohei/fortran-test-framework
