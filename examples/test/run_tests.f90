program run_tests
    use, intrinsic :: iso_fortran_env
    use fortest_assertions
    use test_module_sample
    implicit none

    call reset_stats()

    call test_add_integers()
    call test_multiply_real()
    call test_divide_integer()
    call test_logical_operations()

    call print_summary()

end program run_tests
