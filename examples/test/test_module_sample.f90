!> Tests of functions in module_sample.
module test_module_sample
    use, intrinsic :: iso_fortran_env
    use module_sample
    use fortest_assertions
    implicit none

contains

    !> Test of add_integers.
    subroutine test_add_integers()
        integer(int32) :: result

        result = add_integers(2, 3)
        call assert_equal(result, 5, "add_integers:  2 + 3 = 5")
    end subroutine test_add_integers


    !> Test of multiply_real with tol=1.0e-6.
    subroutine test_multiply_real()
        real(real32) :: result

        result = multiply_real(0.0e0, 100.0e0)

        ! tol is specified as single precision
        call assert_equal(result, 0.0e0, tol=1.0e-6, test_name="multiply_real: 0.0 * 100.0 = 0.0")
    end subroutine test_multiply_real


    !> Test of divide_integer.
    subroutine test_divide_integer()
        integer(int32) :: result

        result = divide_integer(4, 2)
        call assert_equal(result, 2, "divide_integer: 4 / 2 = 2")
    end subroutine test_divide_integer


    !> Test of divide_integer with error stop.
    subroutine test_error_stop_divide_integer_zero_division()
        integer(int32) :: result

        result = divide_integer(4, 0)
    end subroutine test_error_stop_divide_integer_zero_division


    !> Test of logical values.
    ! This is an example of multiple assertions within a single test.
    subroutine test_logical_operations()
        logical :: result

        result = is_positive(42)
        call assert_true(result, "is_positive:  42 is positive")

        result = is_positive(-7)
        call assert_false(result, "is_positive: -7 is not positive")
    end subroutine test_logical_operations

end module test_module_sample
