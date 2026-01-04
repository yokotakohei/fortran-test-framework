!> Sample module providing elementary operations.
module module_sample
    use, intrinsic :: iso_fortran_env
    implicit none
    private

    public :: add_integers
    public :: multiply_real
    public :: divide_integer
    public :: is_positive

contains

    function add_integers(a, b) result(sum)
        integer, intent(in) :: a, b
        integer :: sum

        sum = a + b
    end function add_integers


    function multiply_real(x, y) result(product)
        real(real32), intent(in) :: x, y
        real(real32) :: product

        product = x * y
    end function multiply_real


    function divide_integer(x, y) result(quotient)
        integer(int32), intent(in) :: x, y
        integer(int32) :: quotient

        if(y == 0) error stop "Zero division"
        quotient = x / y
    end function divide_integer


    function is_positive(n) result(is_pos)
        integer, intent(in) :: n
        logical :: is_pos

        is_pos = n > 0
    end function is_positive

end module module_sample
