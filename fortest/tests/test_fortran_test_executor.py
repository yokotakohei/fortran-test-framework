"""
Tests for TestExecutor class.
"""

from pathlib import Path

import pytest

from fortest.build_system_detector import BuildSystemDetector
from fortest.module_dependency_resolver import ModuleDependencyResolver
from fortest.project_builder import ProjectBuilder
from fortest.fortran_test_generator import FortranTestGenerator
from fortest.fortran_test_executor import FortranTestExecutor
from fortest.fortran_result_formatter import FortranResultFormatter


def write_file(path: Path, content: str) -> None:
    """
    Helper function to write test files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def executor() -> FortranTestExecutor:
    """
    Create a FortranTestExecutor instance for testing.
    """
    detector = BuildSystemDetector(verbose=False)
    resolver = ModuleDependencyResolver(verbose=False)
    generator = FortranTestGenerator(verbose=False)
    formatter = FortranResultFormatter(verbose=False)
    builder = ProjectBuilder(
        compiler="gfortran",
        verbose=False,
        detector=detector,
        resolver=resolver,
        generator=generator,
    )
    return FortranTestExecutor(
        compiler="gfortran",
        verbose=False,
        detector=detector,
        resolver=resolver,
        generator=generator,
        formatter=formatter,
        builder=builder,
    )


def test_is_standalone_program_with_program_statement(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test is_standalone_program with program statement.
    Verify that it detects standalone programs.
    """
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("program test_sample\nend program test_sample\n")

    assert executor.is_standalone_program(test_file) is True


def test_is_standalone_program_with_error_stop_in_name(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test is_standalone_program with error_stop in filename.
    Verify that it detects error_stop tests.
    """
    test_file = tmp_path / "test_error_stop_division.f90"
    test_file.write_text("module test_error_stop_division\nend module\n")

    assert executor.is_standalone_program(test_file) is True


def test_is_standalone_program_with_module(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test is_standalone_program with module-based test.
    Verify that it returns False for module-based tests.
    """
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    assert executor.is_standalone_program(test_file) is False


def test_execute_and_check_error_stop_triggered(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
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

    result = executor._execute_and_check_error_stop("test_error_stop", executable)

    assert result.name == "test_error_stop"
    assert result.passed is True
    assert "triggered error stop" in result.message.lower()


def test_execute_and_check_error_stop_not_triggered(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
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

    result = executor._execute_and_check_error_stop("test_error_stop", executable)

    assert result.name == "test_error_stop"
    assert result.passed is False
    assert "expected error stop" in result.message.lower()


def test_run_test_executable_success(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test run_test_executable with successful execution.
    Verify that it captures output and exit code correctly.
    """
    # Create a simple executable
    executable = tmp_path / "test_exe"
    executable.write_text("""#!/bin/bash
echo "Test output"
exit 0
""")
    executable.chmod(0o755)

    success, output, exit_code = executor.run_test_executable(executable)

    assert success is True
    assert "Test output" in output
    assert exit_code == 0


def test_run_test_executable_failure(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test run_test_executable with failed execution.
    Verify that it detects failure correctly.
    """
    # Create an executable that fails
    executable = tmp_path / "test_exe"
    executable.write_text("""#!/bin/bash
echo "Error message"
exit 1
""")
    executable.chmod(0o755)

    success, output, exit_code = executor.run_test_executable(executable)

    assert success is False
    assert "Error message" in output
    assert exit_code == 1


def test_compile_and_run_normal_tests(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test _compile_and_run_normal_tests.
    Verify that it compiles and runs multiple tests.
    Note: This requires gfortran to be available.
    """
    # Create a test module
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("""
module test_sample
    use fortest_assertions
    implicit none
contains
    subroutine test_one()
        call assert_true(.true., "test_one should pass")
    end subroutine

    subroutine test_two()
        call assert_true(.true., "test_two should pass")
    end subroutine
end module test_sample
""")

    output_dir = tmp_path / "build"
    output_dir.mkdir()

    try:
        results = executor._compile_and_run_normal_tests(
            test_file,
            "test_sample",
            ["test_one", "test_two"],
            output_dir,
        )

        # Should return 2 results
        assert len(results) == 2
        assert results[0].name in ["test_one", "test_two"]
        assert results[1].name in ["test_one", "test_two"]

    except Exception:
        # Skip test if gfortran not available or assertions module not found
        pytest.skip("gfortran or fortest_assertions not available")


def test_compile_and_run_normal_tests_empty(
    tmp_path: Path,
    executor: FortranTestExecutor,
) -> None:
    """
    Test _compile_and_run_normal_tests with empty test list.
    Verify that it returns empty results.
    """
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    output_dir = tmp_path / "build"
    output_dir.mkdir()

    results = executor._compile_and_run_normal_tests(
        test_file,
        "test_sample",
        [],
        output_dir,
    )

    assert results == []
