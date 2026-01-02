!> Assertion module providing basic assertion functions.
module fortest_assertions
    use, intrinsic :: iso_fortran_env
    implicit none
    private

    public :: assert_equal
    public :: assert_array_equal
    public :: assert_true
    public :: assert_false
    public :: print_summary
    public :: reset_stats

    ! ANSI color codes.
    !> Red.
    character(len=*), parameter :: color_red = achar(27)//"[31m"
    !> Green.
    character(len=*), parameter :: color_green = achar(27)//"[32m"
    !> Yellow.
    character(len=*), parameter :: color_yellow = achar(27)//"[33m"
    character(len=*), parameter :: color_reset = achar(27)//"[0m"

    ! Tags to report test results.
    !> Expected values.
    character(len=*), parameter :: msg_expected = "Expected: "
    !> Actual values.
    character(len=*), parameter :: msg_got = "Got: "
    !> Total tests.
    character(len=*), parameter :: msg_total = "Total tests: "
    !> Versus separator.
    character(len=*), parameter :: msg_vs = " vs "
    !> Passed tests.
    character(len=*), parameter :: msg_pass = "[PASS] "
    !> Failed tests.
    character(len=*), parameter :: msg_fail = "[FAIL] "
    !> Indentation.
    character(len=*), parameter :: msg_indent = repeat(" ", 7)
    !> Separation line.
    character(len=*), parameter :: msg_separation_line = repeat("=", 50)
    
    ! Error messages.
    !> Error message for assert_true failure.
    character(len=*), parameter :: msg_err_expected_true = "Expected TRUE, got FALSE"
    !> Error message for assert_false failure.
    character(len=*), parameter :: msg_err_expected_false = "Expected FALSE, got TRUE"
    !> Error message for array size mismatch.
    character(len=*), parameter :: msg_err_array_size = "Array sizes differ"
    !> Error message prefix for array element mismatch.
    character(len=*), parameter :: msg_err_array_differ = "Arrays differ at index"
    
    ! Format strings for aligned output.
    !> Format for count output.
    character(len=*), parameter :: fmt_count = "(A,I0)"
    !> Format for result output with color (4-digit right-aligned).
    character(len=*), parameter :: fmt_result = "(A,A,I4,A)"
    
    ! Test execution statistics.
    !> The total number of tests.
    integer(int32) :: test_count = 0
    !> The total number of passed tests.
    integer(int32) :: passed_count = 0
    !> The total number of failed tests.
    integer(int32) :: failed_count = 0
    
    interface assert_equal
        module procedure assert_equal_int
        module procedure assert_equal_real
        module procedure assert_equal_double
        module procedure assert_equal_logical
        module procedure assert_equal_string
    end interface
    
    interface assert_array_equal
        module procedure assert_array_equal_int
        module procedure assert_array_equal_real
        module procedure assert_array_equal_double
    end interface

contains

    !> Assert equality of int32 value.
    subroutine assert_equal_int(actual, expected, test_name)
        !> Actual value.
        integer, intent(in) :: actual
        !> Expected value.
        integer, intent(in) :: expected
        !> Test name.
        character(*), intent(in) :: test_name
        
        test_count = test_count + 1
        
        if(actual == expected) then
            call report_pass(test_name)
        else
            call report_fail(test_name, expected, actual)
        end if
    end subroutine assert_equal_int


    !> Assert equality of real32 value.
    !> Test passes if |actual - expected| < tol.
    subroutine assert_equal_real(actual, expected, test_name, tol)
        !> Actual value.
        real(real32), intent(in) :: actual
        !> Expected value.
        real(real32), intent(in) :: expected
        !> Test name.
        character(*), intent(in) :: test_name
        !> Tolerance for comparison (default 1.0e-6)
        real(real32), intent(in), optional :: tol
        real(real32) :: tolerance
        real(real32), parameter :: tolerance_default = 1.0e-6

        test_count = test_count + 1
        tolerance = tolerance_default
        if(present(tol)) tolerance = tol

        if(abs(actual - expected) < tolerance) then
            call report_pass(test_name)
        else
            call report_fail_real(test_name, expected, actual)
        end if
    end subroutine assert_equal_real


    !> Assert equality of real64 value.
    !> Test passes if |actual - expected| < tol.
    subroutine assert_equal_double(actual, expected, test_name, tol)
        !> Actual value.
        real(real64), intent(in) :: actual
        !> Expected value.
        real(real64), intent(in) :: expected
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Tolerance for comparison (default 1.0d-12).
        real(real64), intent(in), optional :: tol
        real(real64) :: tolerance
        real(real64), parameter :: tolerance_default = 1.0d-12
        
        test_count = test_count + 1
        tolerance = tolerance_default
        if(present(tol)) tolerance = tol
        
        if(abs(actual - expected) < tolerance) then
            call report_pass(test_name)
        else
            call report_fail_double(test_name, expected, actual)
        end if
    end subroutine assert_equal_double


    !> Assert equality of logical value.
    subroutine assert_equal_logical(actual, expected, test_name)
        !> Actual value.
        logical, intent(in) :: actual
        !> Expected value.
        logical, intent(in) :: expected
        !> Test name.
        character(len=*), intent(in) :: test_name
        
        test_count = test_count + 1
        
        if(actual .eqv. expected) then
            call report_pass(test_name)
        else
            call report_fail_logical(test_name)
        end if
    end subroutine assert_equal_logical


    !> Assert equality of string value.
    subroutine assert_equal_string(actual, expected, test_name)
        !> Actual value.
        character(len=*), intent(in) :: actual
        !> Expected value.
        character(len=*), intent(in) :: expected
        !> Test name.
        character(len=*), intent(in) :: test_name
        
        test_count = test_count + 1
        
        if(actual == expected) then
            call report_pass(test_name)
        else
            call report_fail_string(test_name, expected, actual)
        end if
    end subroutine assert_equal_string


    !> Assert that condition is true.
    subroutine assert_true(condition, test_name)
        !> Condition to test.
        logical, intent(in) :: condition
        !> Test name.
        character(len=*), intent(in) :: test_name
        
        test_count = test_count + 1
        
        if(condition) then
            call report_pass(test_name)
        else
            call report_fail_simple(test_name, msg_err_expected_true)
        end if
    end subroutine assert_true


    !> Assert that condition is false.
    subroutine assert_false(condition, test_name)
        !> Condition to test.
        logical, intent(in) :: condition
        !> Test name.
        character(len=*), intent(in) :: test_name
        
        test_count = test_count + 1
        
        if(.not. condition) then
            call report_pass(test_name)
        else
            call report_fail_simple(test_name, msg_err_expected_false)
        end if
    end subroutine assert_false


    !> Assert equality of integer array.
    subroutine assert_array_equal_int(actual, expected, test_name)
        !> Actual array.
        integer, intent(in) :: actual(:)
        !> Expected array.
        integer, intent(in) :: expected(:)
        !> Test name.
        character(len=*), intent(in) :: test_name
        integer :: i
        character(len=100) :: error_msg
        
        test_count = test_count + 1
        
        if(size(actual) /= size(expected)) then
            call report_fail_simple(test_name, msg_err_array_size)
            return
        end if
        
        do i = 1, size(actual)
            if(actual(i) /= expected(i)) then
                write(error_msg, '(A,I0,A,I0,A,I0)') msg_err_array_differ, i, ": ", expected(i), msg_vs, actual(i)
                call report_fail_simple(test_name, trim(error_msg))
                return
            end if
        end do
        
        call report_pass(test_name)
    end subroutine assert_array_equal_int


    !> Assert equality of real32 array.
    !> Test passes if |actual(i) - expected(i)| < tol for all i.
    subroutine assert_array_equal_real(actual, expected, test_name, tol)
        !> Actual array.
        real(real32), intent(in) :: actual(:)
        !> Expected array.
        real(real32), intent(in) :: expected(:)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Tolerance for comparison.
        real(real32), intent(in), optional :: tol
        real(real32) :: tolerance
        real(real32), parameter :: tolerance_default = 1.0e-6
        integer :: i
        character(len=100) :: error_msg
        
        test_count = test_count + 1
        tolerance = tolerance_default
        if(present(tol)) tolerance = tol
        
        if(size(actual) /= size(expected)) then
            call report_fail_simple(test_name, msg_err_array_size)
            return
        end if
        
        do i = 1, size(actual)
            if(abs(actual(i) - expected(i)) >= tolerance) then
                write(error_msg, '(A,I0,A,E12.5,A,E12.5)') msg_err_array_differ, i, ": ", expected(i), msg_vs, actual(i)
                call report_fail_simple(test_name, trim(error_msg))
                return
            end if
        end do
        
        call report_pass(test_name)
    end subroutine assert_array_equal_real


    !> Assert equality of real64 array.
    !> Test passes if |actual(i) - expected(i)| < tol for all i.
    subroutine assert_array_equal_double(actual, expected, test_name, tol)
        !> Actual array.
        real(real64), intent(in) :: actual(:)
        !> Expected array.
        real(real64), intent(in) :: expected(:)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Tolerance for comparison.
        real(real64), intent(in), optional :: tol
        real(real64) :: tolerance
        real(real64), parameter :: tolerance_default = 1.0d-12
        integer :: i
        character(len=100) :: error_msg
        
        test_count = test_count + 1
        tolerance = tolerance_default
        if(present(tol)) tolerance = tol
        
        if(size(actual) /= size(expected)) then
            call report_fail_simple(test_name, msg_err_array_size)
            return
        end if
        
        do i = 1, size(actual)
            if(abs(actual(i) - expected(i)) >= tolerance) then
                write(error_msg, '(A,I0,A,E20.12,A,E20.12)') msg_err_array_differ, i, ": ", expected(i), msg_vs, actual(i)
                call report_fail_simple(test_name, trim(error_msg))
                return
            end if
        end do
        
        call report_pass(test_name)
    end subroutine assert_array_equal_double


    !> Report test pass.
    subroutine report_pass(test_name)
        !> Test name.
        character(len=*), intent(in) :: test_name

        passed_count = passed_count + 1
        print*, color_green, msg_pass, color_reset, trim(test_name)
    end subroutine report_pass


    !> Report integer test failure.
    subroutine report_fail(test_name, expected, actual)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Expected value.
        integer, intent(in) :: expected
        !> Actual value.
        integer, intent(in) :: actual

        failed_count = failed_count + 1
        print*, color_red, msg_fail, color_reset, trim(test_name)
        print*, msg_indent, expected, msg_vs, actual
    end subroutine report_fail


    !> Report real32 test failure.
    subroutine report_fail_real(test_name, expected, actual)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Expected value.
        real(real32), intent(in) :: expected
        !> Actual value.
        real(real32), intent(in) :: actual

        failed_count = failed_count + 1
        print*, color_red, msg_fail, color_reset, trim(test_name)
        print*, msg_indent, expected, msg_vs, actual
    end subroutine report_fail_real


    !> Report real64 test failure.
    subroutine report_fail_double(test_name, expected, actual)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Expected value.
        real(real64), intent(in) :: expected
        !> Actual value.
        real(real64), intent(in) :: actual

        failed_count = failed_count + 1
        print*, color_red, msg_fail, color_reset, trim(test_name)
        print*, msg_indent, expected, msg_vs, actual
    end subroutine report_fail_double


    !> Report logical test failure.
    subroutine report_fail_logical(test_name)
        !> Test name.
        character(len=*), intent(in) :: test_name

        failed_count = failed_count + 1
        print*, color_red, msg_fail, color_reset, trim(test_name)
    end subroutine report_fail_logical


    !> Report string test failure.
    subroutine report_fail_string(test_name, expected, actual)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Expected value.
        character(len=*), intent(in) :: expected
        !> Actual value.
        character(len=*), intent(in) :: actual

        failed_count = failed_count + 1
        print*, color_red, msg_fail, color_reset, trim(test_name)
        print*, msg_indent, msg_expected, '"', expected, '", ', msg_got, '"', actual, '"'
    end subroutine report_fail_string


    !> Report test failure with simple message.
    subroutine report_fail_simple(test_name, message)
        !> Test name.
        character(len=*), intent(in) :: test_name
        !> Error message.
        character(len=*), intent(in) :: message

        failed_count = failed_count + 1
        print*, color_red, msg_fail, color_reset, trim(test_name)
        print*, msg_indent, trim(message)
    end subroutine report_fail_simple


    !> Print test results summary.
    subroutine print_summary()
        print '(A)', ""
        print '(A)', msg_separation_line
        print fmt_count, msg_total, test_count
        print fmt_result, color_green, msg_pass, passed_count, color_reset
        print fmt_result, color_red, msg_fail, failed_count, color_reset
        print '(A)', msg_separation_line
    end subroutine print_summary


    !> Reset test statistics.
    subroutine reset_stats()
        test_count = 0
        passed_count = 0
        failed_count = 0
    end subroutine reset_stats

end module fortest_assertions
