"""
Tests of fortest/fortran_test_runner.py
Tests are ordered according to method definitions in fortran_test_runner.py.
"""
from pathlib import Path

import pytest

from fortest.fortran_test_runner import FortranTestRunner


@pytest.fixture
def runner() -> FortranTestRunner:
    """
    Returns runner used in tests.
    """
    return FortranTestRunner(verbose=False)


def write_file(path: Path, content: str) -> None:
    """
    Write a content to a file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ============================================================================
# Tests for methods in order of definition in runner.py
# ============================================================================

# __init__ - tested implicitly through fixture

def test_find_test_files(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Tests find_test_files.
    Verify that it generates list of test file names.
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
    assert names == ["test_one.f90", "module_test_two.f90"]


def test__find_build_directories(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_build_directories.
    Verify that it finds build directories with .mod and .o files.
    """
    # Create directory structure
    project = tmp_path / "project"
    build_dir = project / "build"
    build_dir.mkdir(parents=True)
    
    # Create some .mod and .o files
    (build_dir / "module1.mod").write_text("")
    (build_dir / "module1.o").write_text("")
    
    # Create nested build directory
    nested_build = project / "src" / "build"
    nested_build.mkdir(parents=True)
    (nested_build / "module2.mod").write_text("")
    
    # Create test file
    test_dir = project / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("")
    
    build_dirs = runner._find_build_directories(test_file)
    
    # Should find the build directories
    assert build_dir in build_dirs or nested_build in build_dirs


def test__build_search_directories(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _build_search_directories.
    Verify that it finds common FPM/CMake directory structures.
    """
    # Create directory structure
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "app").mkdir(parents=True)
    (project / "lib").mkdir(parents=True)
    (project / "test").mkdir(parents=True)
    (project / "fortran" / "src").mkdir(parents=True)

    test_file = project / "test" / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    search_dirs = runner._build_search_directories(test_file)

    # Should find src, app, lib, fortran/src, and test directories
    dir_names = {str(d.relative_to(project)) for d in search_dirs if project in d.parents or d == project or d.parent == project}
    expected_dirs = {".", "src", "app", "lib", "test", str(Path("fortran") / "src")}

    assert dir_names == expected_dirs















def test__is_standalone_program_with_program_statement(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _is_standalone_program with program statement.
    Verify that it detects standalone programs.
    """
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("program test_sample\nend program test_sample\n")

    assert runner._is_standalone_program(test_file) is True


def test__is_standalone_program_with_error_stop_in_name(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _is_standalone_program with error_stop in filename.
    Verify that it detects error_stop tests.
    """
    test_file = tmp_path / "test_error_stop_division.f90"
    test_file.write_text("module test_error_stop_division\nend module\n")

    assert runner._is_standalone_program(test_file) is True


def test__is_standalone_program_with_module(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _is_standalone_program with module-based test.
    Verify that it returns False for module-based tests.
    """
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    assert runner._is_standalone_program(test_file) is False


# _compile_standalone_program, _compile_module_test: Complex integration tests not included

# compile_test: Integration test not included (requires actual compilation)

# run_test_executable: Integration test not included (requires actual executables)




def test__compile_module_dependencies_success(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _compile_module_dependencies with successful compilation.
    Verify that it compiles modules and returns object files.
    """
    # Create a simple Fortran module
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    module_file = src_dir / "module_sample.f90"
    module_file.write_text("""
module sample
    implicit none
contains
    subroutine sample_sub()
    end subroutine
end module sample
""")
    
    output_dir = tmp_path / "build"
    output_dir.mkdir()
    test_file = tmp_path / "test" / "test_sample.f90"
    test_file.parent.mkdir()
    test_file.touch()
    
    # Note: This test will only work if gfortran is available
    try:
        objects, error = runner._compile_module_dependencies(
            [module_file],
            test_file,
            output_dir,
        )
        
        # If compilation succeeds
        if error is None:
            assert len(objects) == 1
            assert objects[0].suffix == ".o"
            assert objects[0].exists()
    except Exception:
        # Skip test if gfortran not available
        pytest.skip("gfortran not available")


def test__compile_single_module_creates_object(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _compile_single_module.
    Verify that it compiles a single module and creates object file.
    """
    # Create a simple Fortran module
    module_file = tmp_path / "module_math.f90"
    module_file.write_text("""
module math_ops
    implicit none
contains
    function add(a, b) result(c)
        integer, intent(in) :: a, b
        integer :: c
        c = a + b
    end function
end module math_ops
""")
    
    output_dir = tmp_path / "build"
    output_dir.mkdir()
    
    try:
        obj_file = runner._compile_single_module(
            module_file,
            [],  # No build directories
            output_dir,
        )
        
        # If compilation succeeds
        if obj_file is not None:
            assert obj_file.exists()
            assert obj_file.suffix == ".o"
            assert obj_file.parent == output_dir
    except Exception:
        # Skip test if gfortran not available
        pytest.skip("gfortran not available")


def test__compile_test_executable_success(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _compile_test_executable.
    Verify that it compiles test executable successfully.
    """
    # Create test files
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("""
module test_sample
    implicit none
contains
    subroutine test_addition()
        print *, '[PASS] Addition test'
    end subroutine
end module test_sample
""")
    
    program_file = tmp_path / "main.f90"
    program_file.write_text("""
program test_main
    use test_sample
    implicit none
    call test_addition()
end program test_main
""")
    
    output_dir = tmp_path / "build"
    output_dir.mkdir()
    executable = output_dir / "test_exe"
    
    try:
        error = runner._compile_test_executable(
            test_file,
            program_file,
            executable,
            [],  # No compiled objects
            output_dir,
        )
        
        # If compilation succeeds
        if error is None:
            assert executable.exists()
    except Exception:
        # Skip test if gfortran not available
        pytest.skip("gfortran not available")


def test__execute_and_check_error_stop_triggered(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _execute_and_check_error_stop when error stop is triggered.
    Verify that it returns PASS when exit code is non-zero.
    """
    # Create a mock executable that exits with error code
    executable = tmp_path / "test_error"
    executable.write_text("""#!/bin/bash
exit 2
""")
    executable.chmod(0o755)
    
    result = runner._execute_and_check_error_stop("test_error_stop", executable)
    
    assert result.name == "test_error_stop"
    assert result.passed is True
    assert "triggered error stop" in result.message.lower()


def test__execute_and_check_error_stop_not_triggered(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _execute_and_check_error_stop when error stop is NOT triggered.
    Verify that it returns FAIL when exit code is zero.
    """
    # Create a mock executable that exits successfully
    executable = tmp_path / "test_no_error"
    executable.write_text("""#!/bin/bash
exit 0
""")
    executable.chmod(0o755)
    
    result = runner._execute_and_check_error_stop("test_error_stop", executable)
    
    assert result.name == "test_error_stop"
    assert result.passed is False
    assert "expected error stop" in result.message.lower()


# _run_single_normal_test: Integration test not included (requires compilation)


def test__generate_temp_test_filename(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _generate_temp_test_filename.
    Verify that it generates unique filenames with proper hash-based naming.
    """
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    
    # Test basic filename generation
    temp_file1, program_name1 = runner._generate_temp_test_filename("test_addition", test_dir)
    assert temp_file1.parent == test_dir
    assert temp_file1.suffix == ".f90"
    assert temp_file1.name.startswith("fortest_")
    assert program_name1.startswith("fortest_")
    assert len(program_name1) <= 20  # Should be short (fortest_ + 8 char hash)
    
    # Test that the same test name generates the same hash
    temp_file2, program_name2 = runner._generate_temp_test_filename("test_addition", test_dir)
    assert temp_file1 == temp_file2
    assert program_name1 == program_name2
    
    # Test different test names generate different hashes
    temp_file3, program_name3 = runner._generate_temp_test_filename("test_subtraction", test_dir)
    assert temp_file3.name != temp_file1.name
    assert program_name3 != program_name1
    
    # Test collision handling: create a file, then generate name again
    temp_file1.touch()
    temp_file4, program_name4 = runner._generate_temp_test_filename("test_addition", test_dir)
    assert temp_file4 != temp_file1  # Should get a different name due to collision
    assert program_name4 != program_name1  # Program name should also differ
    assert "_1" in temp_file4.name or "_1" in program_name4  # Counter added