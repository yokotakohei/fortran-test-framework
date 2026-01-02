# fortest - A Python-aided Testing Framework for Fortran

A Python-aided testing framework for Fortran with automated test discovery and execution.

## Features

-  **Assertions**: Support for integers, reals, doubles, logicals, strings, and arrays
-  **Error stop detection**: Automatically detect and handle `error stop` in tests
-  **Auto-discovery**: Automatically finds and runs test files matching `test_*.f90` pattern
-  **Python runner**: Flexible test discovery and execution

## Installation

### Prerequisites

- Python 3.12 or later
- A Fortran compiler (gfortran recommended)

### Install from PyPI

```bash
pip install fortest
```

### Install from source

```bash
git clone https://github.com/yokotakohei/fortran-test-runner.git
cd fortran-test-runner
pip install -e .
```

## Quick Start

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

! String comparison
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

See the `examples/` directory for complete examples:

- [examples/module_sample.f90](examples/module_sample.f90) - Sample module with basic functions
- [examples/test_module_sample.f90](examples/test_module_sample.f90) - Test examples using assertions

### Running Examples

```bash
cd examples
fortest
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

## Test File Naming

fortest automatically discovers test files matching these patterns:
- `test_*.f90`
- `module_test_*.f90`

Files containing `error_stop` in their name are treated as error-stop tests.

## Output Example

```
Running Fortran tests...

Testing: examples/test_module_sample.f90
[PASS] test_add_integers: 2 + 3 = 5
[PASS] test_add_integers: -1 + 1 = 0
[PASS] test_multiply_real: 2.0 * 3.0 = 6.0
[PASS] test_divide_integer: 6 / 2 = 3

==================================================
Test Summary
==================================================
Total tests:     4
Passed:          4
Failed:          0
==================================================

All tests passed ✓
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Author

yokotakohei

## Repository

[fortran-test-runner on GitHub](https://github.com/yokotakohei/fortran-test-runner)

