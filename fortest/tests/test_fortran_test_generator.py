"""
Tests for TestCodeGenerator class.
Tests are ordered according to method definitions in test_code_generator.py.
"""

from pathlib import Path

import pytest

from fortest.fortran_test_generator import FortranTestGenerator


def write_file(path: Path, content: str) -> None:
    """
    Helper function to write test files.
    """
    path.write_text(content)


@pytest.fixture
def generator() -> FortranTestGenerator:
    """
    Create a FortranTestGenerator instance for testing.
    """
    return FortranTestGenerator(verbose=False)


def test_extract_test_subroutines(
    tmp_path: Path,
    generator: FortranTestGenerator,
) -> None:
    """
    Test extract_test_subroutines.
    Verify that it extracts test subroutines.
    """
    f = tmp_path / "test_sample.f90"
    content = """
module test_sample
contains
function test_dummy_func() return(y)
integer :: y
y = 0
end
subroutine dummy_subroutine()
end subroutine
 subroutine test_one()
end subroutine test_one
! comment subroutine test_ignore()
! subroutine test_ignore()
subroutine test_two() ! subroutine
end subroutine test_two
end module test_sample
"""
    write_file(f, content)
    subs = generator.extract_test_subroutines(f)
    assert subs == ["test_one", "test_two"]


def test_separate_error_stop_tests(generator: FortranTestGenerator) -> None:
    """
    Test separate_error_stop_tests.
    Verify that it separates test names correctly.
    """
    names = ["test_ok", "test_error_stop_div", "test_another_error_stop"]
    normal, errors = generator.separate_error_stop_tests(names)
    assert normal == ["test_ok"]
    assert errors == ["test_error_stop_div", "test_another_error_stop"]


def test_generate_test_program(
    tmp_path: Path,
    generator: FortranTestGenerator,
) -> None:
    """
    Test generate_test_program.
    Verify that it generates a correct test code.
    """
    test_file = tmp_path / "test_module_sample.f90"
    test_file.write_text("")
    out = generator.generate_test_program(
        test_file, "test_module_sample", ["test_a", "test_b"], tmp_path
    )
    text = out.read_text()
    expected = """program run_test_module_sample
    use fortest_assertions
    use test_module_sample
    implicit none
    call test_a()
    call test_b()
    call print_summary()
end program run_test_module_sample\n"""

    assert text == expected


def test_generate_error_stop_test_program(
    tmp_path: Path,
    generator: FortranTestGenerator,
) -> None:
    """
    Test generate_error_stop_test_program.
    Verify that it generates error_stop test program correctly.
    """
    out = generator.generate_error_stop_test_program(
        "test_module", "test_error_stop_divide_by_zero", tmp_path
    )
    text = out.read_text()
    expected = """program run_test_error_stop_divide_by_zero
    use test_module
    implicit none
    call test_error_stop_divide_by_zero()
end program run_test_error_stop_divide_by_zero\n"""

    assert text == expected


def test_generate_single_test_program(
    tmp_path: Path,
    generator: FortranTestGenerator,
) -> None:
    """
    Test generate_single_test_program.
    Verify that it generates a correct single test program.
    """
    out = generator.generate_single_test_program(
        "test_module", "test_addition", tmp_path
    )
    text = out.read_text()
    expected = """program run_test_addition
    use fortest_assertions
    use test_module
    implicit none
    call test_addition()
end program run_test_addition\n"""

    assert text == expected