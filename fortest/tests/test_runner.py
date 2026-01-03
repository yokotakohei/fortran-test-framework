"""
Tests of fortest/runner.py
"""
from pathlib import Path

import pytest

from fortest.runner import FortranTestRunner


@pytest.fixture
def runner() -> FortranTestRunner:
    """
    Returns runner used in tests.
    """
    return FortranTestRunner(verbose=False)


def write_file(path: Path, content: str):
    """
    Write a content to a file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_extract_module_name(tmp_path, runner):
    """
    Test extract_module_name.
    Check if a module name can be extracted as lower case.
    """
    f = tmp_path / "test_mod.f90"
    write_file(f, "  module My_Module \n end module My_Module \n")
    name = runner.extract_module_name(f)
    assert name == "my_module"


def test_extract_test_subroutines(tmp_path, runner):
    """
    Test extract_test_subroutines.
    Check if defined test subroutines are extracted.
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
subroutine test_two() ! subroutine
end subroutine test_two
end module test_sample
"""
    write_file(f, content)
    subs = runner.extract_test_subroutines(f)
    assert "test_one" in subs
    assert "test_two" in subs
    assert len(subs) == 2


def test_separate_error_stop_tests(runner):
    """
    Test separate_error_stop_tests.
    Check if test names are correctly separated.
    """
    names = ["test_ok", "test_error_stop_div", "test_another_error_stop"]
    normal, errors = runner.separate_error_stop_tests(names)
    assert normal == ["test_ok"]
    assert set(errors) == {"test_error_stop_div", "test_another_error_stop"}


def test_generate_test_program(tmp_path, runner):
    """
    Test generate_test_program.
    Check if a correct test code is generated.
    """
    test_file = tmp_path / "test_module_sample.f90"
    test_file.write_text("")
    out = runner.generate_test_program(test_file, "test_module_sample", ["test_a", "test_b"], tmp_path)
    text = out.read_text()
    correct = """program run_test_module_sample
    use fortest_assertions
    use test_module_sample
    implicit none
    call test_a()
    call test_b()
    call print_summary()
end program run_test_module_sample\n"""

    assert correct == text


def test_find_module_files_finds_assertions_and_user_modules(tmp_path, runner):
    """
    Test find_module_files.
    Check if the function finds assertion and modules.
    """
    # Create project layout
    project = tmp_path
    (project / "fortran" / "src").mkdir(parents=True)
    assertions = project / "fortran" / "src" / "module_fortest_assertions.f90"
    assertions.write_text("module fortest_assertions\nend module fortest_assertions\n")

    # examples/src and examples/test
    (project / "examples" / "src").mkdir(parents=True)
    (project / "examples" / "test").mkdir(parents=True)
    user_mod = project / "examples" / "src" / "module_sample.f90"
    user_mod.write_text("module module_sample\nend module module_sample\n")

    test_file = project / "examples" / "test" / "test_module_sample.f90"
    test_file.write_text("module test_module_sample\nend module test_module_sample\n")

    found = runner.find_module_files(test_file)

    # Should find both assertions and user module
    found_names = [p.name for p in found]
    assert len(found_names) == 2
    assert "module_fortest_assertions.f90" in found_names
    assert "module_sample.f90" in found_names


def test_find_test_files(tmp_path, runner):
    """
    Tests find_test_files.
    Check if lists of test file names are generated.
    """
    d = tmp_path / "tests"
    (d).mkdir()
    f1 = d / "test_one.f90"
    f1.write_text("")
    f2 = d / "module_test_two.f90"
    f2.write_text("")
    f3 = d / "module_example_functions.f90"
    f3.write_text("")
    f4 = d / "class_example_class.f90"
    f4.write_text("")
    res = runner.find_test_files(str(d))

    # Should find both files
    names = [p.name for p in res]
    assert len(names) == 2
    assert "test_one.f90" in names
    assert "module_test_two.f90" in names
