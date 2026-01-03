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

```bash
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

# Link to your test executable
target_link_libraries(your_test PRIVATE fortest::assertions)
```

#### Using FPM

Add to your `fpm.toml`:

```toml
[dependencies]
fortest-assertions = { git = "https://github.com/yokotakohei/fortran-test-framework.git", path = "fortran" }
```


## Quick Start

### Test File Naming

fortest automatically discovers test files matching these patterns:
- `test_*.f90`
- `module_test_*.f90`

Files containing `error_stop` in their name are treated as error-stop tests (see section [Testing Error Stops](#Testing Error Stops)).

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

end program test_sample_module
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

```fortran
use fortest_assertions
use iso_fortran_env, only: real32, real64, int32

! Integer comparison
call assert_equal(actual, expected, "test name")

! Real comparison (with optional tolerance)
call assert_equal(actual_real, expected_real, "test name", tol=1.0e-6)

! Double precision comparison
call assert_equal(actual_dp, expected_dp, "test name", tol=1.0d-12)

! Logical comparison
call assert_equal(actual_bool, expected_bool, "test name")

! Character comparison
call assert_equal(actual_str, expected_str, "test name")

! Logical assertions
call assert_true(condition, "test name")
call assert_false(condition, "test name")
```

### Array Assertions

```fortran
! Integer array
call assert_array_equal(actual_arr, expected_arr, "test name")

! Real array (with optional tolerance)
call assert_array_equal(actual_arr, expected_arr, "test name", tol=1.0e-6)

! Double precision array
call assert_array_equal(actual_arr_dp, expected_arr_dp, "test name", tol=1.0d-12)
```


## Testing Error Stops

fortest can automatically detect when a function correctly triggers `error stop`:

```fortran
! test_error_stop_example.f90
program test_error_stop_example
    use my_module
    implicit none

    ! This will trigger error stop, which is expected
    call divide_by_zero(0.0)
    
end program test_error_stop_example
```

Name your test file with `error_stop` in the filename, and fortest will:
1. Detect that the test caused an error stop
2. Mark the test as **PASSED** (because error stop was expected)
3. Continue running other tests


## Examples

See the `examples/` directory for complete working examples with both CMake and FPM.

### CMake Example

```bash
cd examples
mkdir build && cd build
cmake ..
make
ctest
```

Or run with fortest:

```bash
fortest ../test/
```

### FPM Example

```bash
cd examples
fpm test
```

Or run with fortest:

```bash
fortest test/
```

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
 [PASS] add_integers(2, 3) should return 5
 [PASS] multiply_real(0.0, 100.0) should return 0.0
 [PASS] divide_integer(4, 2) should return 2
 [PASS] is_positive(42) should return true
 [PASS] is_positive(-7) should return false

==================================================
Total tests: 5
[PASS]    5
[FAIL]    0
==================================================

[PASS] test_error_stop_divide_integer_zero_division

==================================================
error_stop tests: 1
[PASS]   1
[FAIL]   0
==================================================


All tests completed.
==================================================
Total tests: 6
[PASS]   6
[FAIL]   0
==================================================

All tests passed! ✓
```


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Author

Kohei Yokota

## Repository

https://github.com/yokotakohei/fortran-test-framework
