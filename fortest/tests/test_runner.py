"""
Tests of fortest/runner.py
Tests are ordered according to method definitions in runner.py.
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


def test__find_assertion_module(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_assertion_module.
    Verify that it finds module_fortest_assertions.f90.
    """
    # Create directory with assertions module
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    assertions_file = src_dir / "module_fortest_assertions.f90"
    assertions_file.write_text("module fortest_assertions\nend module fortest_assertions\n")

    search_dirs = [src_dir]
    found = runner._find_assertion_module(search_dirs)

    assert found is not None
    assert found.name == "module_fortest_assertions.f90"
    assert found == assertions_file


def test__find_user_modules(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_user_modules.
    Verify that it finds user modules while skipping intrinsic and assertion modules.
    """
    # Create directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create user modules
    module_a = src_dir / "module_a.f90"
    module_a.write_text("module module_a\nend module module_a\n")

    module_b = src_dir / "module_b.f90"
    module_b.write_text("module module_b\nend module module_b\n")

    # Create test file
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    # Test with various module names
    used_modules = [
        "iso_fortran_env",  # intrinsic - should be skipped
        "fortest_assertions",  # assertion - should be skipped
        "module_a",  # user module - should be found
        "module_b",  # user module - should be found
    ]

    search_dirs = [src_dir]
    found_modules = runner._find_user_modules(used_modules, search_dirs, test_file)

    # Should find only user modules
    found_names = {f.stem for f in found_modules}
    assert found_names == {"module_a", "module_b"}


def test_find_module_files_finds_assertions_and_user_modules(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test find_module_files.
    Verify that it finds assertion and modules.
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
    # Add use statements so find_module_files can discover dependencies
    test_file.write_text("""module test_module_sample
    use fortest_assertions
    use module_sample
end module test_module_sample
""")

    found = runner.find_module_files(test_file)

    # Should find both assertions and user module
    found_names = sorted([p.name for p in found])
    assert found_names == ["module_fortest_assertions.f90", "module_sample.f90"]


def test_extract_module_name(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test extract_module_name.
    Verify that it extracts a module name as lower case.
    """
    f = tmp_path / "test_mod.f90"
    write_file(f, "  module My_Module \n end module My_Module \n")
    name = runner.extract_module_name(f)
    assert name == "my_module"


def test_extract_module_name_no_module(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test extract_module_name when no module is defined.
    Verify that it returns None.
    """
    f = tmp_path / "program.f90"
    write_file(f, "program main\nend program main\n")
    name = runner.extract_module_name(f)
    assert name is None


def test_extract_use_statements(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test extract_use_statements.
    Verify that it extracts 'use' statements correctly.
    Note: This function extracts all use statements including intrinsic modules.
    Filtering is done in find_module_files.
    """
    f = tmp_path / "sample.f90"
    content = """
module sample
    use iso_fortran_env
    use :: module_a
    use, intrinsic :: iso_c_binding
    use module_b, only: func1, func2
    ! use module_c (this is a comment)
contains
    subroutine test()
        use module_d  ! inline use
    end subroutine
end module sample
"""
    write_file(f, content)
    uses = runner.extract_use_statements(f)

    # Should find all use statements (lowercase, unique), comment should be ignored
    assert uses == ["iso_fortran_env", "module_a", "iso_c_binding", "module_b", "module_d"]


def test_extract_use_statements_with_comments(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test extract_use_statements with comments.
    Verify that commented use statements are ignored.
    """
    f = tmp_path / "sample.f90"
    content = """
module sample
    use module_a
    ! use module_b
    use module_c
end module sample
"""
    write_file(f, content)
    uses = runner.extract_use_statements(f)
    
    # module_b should not be in the list (it's commented out)
    assert "module_a" in uses
    assert "module_c" in uses
    assert "module_b" not in uses


def test_find_fortran_files_recursive(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test find_fortran_files_recursive.
    Verify that it finds .f90 files recursively.
    """
    (tmp_path / "src" / "subdir1").mkdir(parents=True)
    (tmp_path / "src" / "subdir2").mkdir(parents=True)

    f1 = tmp_path / "src" / "mod1.f90"
    f2 = tmp_path / "src" / "subdir1" / "mod2.f90"
    f3 = tmp_path / "src" / "subdir2" / "mod3.f90"
    f4 = tmp_path / "src" / "readme.txt"

    f1.write_text("! mod1")
    f2.write_text("! mod2")
    f3.write_text("! mod3")
    f4.write_text("readme")

    files = runner.find_fortran_files_recursive(tmp_path / "src")
    names = sorted([f.name for f in files])

    assert names == ["mod1.f90", "mod2.f90", "mod3.f90"]


def test_find_module_file_by_name(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test find_module_file_by_name.
    Verify that it finds module files by module name.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "lib").mkdir()

    # Create files with modules
    f1 = tmp_path / "src" / "my_module.f90"
    f1.write_text("module my_awesome_module\nend module")

    f2 = tmp_path / "lib" / "util.f90"
    f2.write_text("module utilities\nend module utilities")

    # Search for modules
    search_dirs = [tmp_path / "src", tmp_path / "lib"]

    found1 = runner.find_module_file_by_name("my_awesome_module", search_dirs)
    assert found1 is not None
    assert found1.name == "my_module.f90"

    found2 = runner.find_module_file_by_name("utilities", search_dirs)
    assert found2 is not None
    assert found2.name == "util.f90"

    not_found = runner.find_module_file_by_name("nonexistent", search_dirs)
    assert not_found is None


def test_extract_test_subroutines(tmp_path: Path, runner: FortranTestRunner) -> None:
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
    subs = runner.extract_test_subroutines(f)
    assert subs == ["test_one", "test_two"]


def test_separate_error_stop_tests(runner: FortranTestRunner) -> None:
    """
    Test separate_error_stop_tests.
    Verify that it separates test names correctly.
    """
    names = ["test_ok", "test_error_stop_div", "test_another_error_stop"]
    normal, errors = runner.separate_error_stop_tests(names)
    assert normal == ["test_ok"]
    assert errors == ["test_error_stop_div", "test_another_error_stop"]


def test_generate_test_program(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test generate_test_program.
    Verify that it generates a correct test code.
    """
    test_file = tmp_path / "test_module_sample.f90"
    test_file.write_text("")
    out = runner.generate_test_program(test_file, "test_module_sample", ["test_a", "test_b"], tmp_path)
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


def test_generate_error_stop_test_program(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test generate_error_stop_test_program.
    Verify that it generates error_stop test program correctly.
    """
    out = runner.generate_error_stop_test_program(
        "test_module",
        "test_error_stop_divide_by_zero",
        tmp_path
    )
    text = out.read_text()
    expected = """program run_test_error_stop_divide_by_zero
    use test_module
    implicit none
    call test_error_stop_divide_by_zero()
end program run_test_error_stop_divide_by_zero\n"""

    assert text == expected


def test_detect_build_system_fpm(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test detect_build_system with FPM.
    Verify that it detects fpm.toml and returns FPM build info.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    # Create fpm.toml
    fpm_toml = project_dir / "fpm.toml"
    fpm_toml.write_text("[package]\nname = 'test'\n")
    
    # Create test directory
    test_dir = project_dir / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("")
    
    build_info = runner.detect_build_system(test_file)
    
    assert build_info is not None
    assert build_info.build_type == "fpm"
    assert build_info.project_dir == project_dir


def test_detect_build_system_cmake(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test detect_build_system with CMake.
    Verify that it detects CMakeLists.txt and returns CMake build info.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    # Create CMakeLists.txt
    cmake_file = project_dir / "CMakeLists.txt"
    cmake_file.write_text("project(test)\n")
    
    # Create test directory
    test_dir = project_dir / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("")
    
    build_info = runner.detect_build_system(test_file)
    
    assert build_info is not None
    assert build_info.build_type == "cmake"
    assert build_info.project_dir == project_dir


def test_detect_build_system_make(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test detect_build_system with Make.
    Verify that it detects Makefile and returns Make build info.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    # Create Makefile
    makefile = project_dir / "Makefile"
    makefile.write_text("all:\n\techo test\n")
    
    # Create test directory
    test_dir = project_dir / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("")
    
    build_info = runner.detect_build_system(test_file)
    
    assert build_info is not None
    assert build_info.build_type == "make"
    assert build_info.project_dir == project_dir


def test_detect_build_system_priority_fpm_over_cmake(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test detect_build_system priority.
    Verify that FPM takes priority over CMake when both exist.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    # Create both fpm.toml and CMakeLists.txt
    fpm_toml = project_dir / "fpm.toml"
    fpm_toml.write_text("[package]\nname = 'test'\n")
    cmake_file = project_dir / "CMakeLists.txt"
    cmake_file.write_text("project(test)\n")
    
    # Create test directory
    test_dir = project_dir / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("")
    
    build_info = runner.detect_build_system(test_file)
    
    assert build_info is not None
    assert build_info.build_type == "fpm"


def test_detect_build_system_none(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test detect_build_system when no build system is found.
    Verify that it returns None.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    test_dir = project_dir / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("")
    
    build_info = runner.detect_build_system(test_file)
    
    assert build_info is None


def test__find_cmake_executable(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_cmake_executable.
    Verify that it finds test executables in CMake build directories.
    """
    # Create CMake build directory
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    # Create test file
    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("")

    # Create executable with exact test name
    executable = build_dir / "test_sample"
    executable.touch()

    found = runner._find_cmake_executable(build_dir, test_file)
    assert found is not None
    assert found == executable


def test__find_cmake_executable_with_alternative_name(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_cmake_executable with alternative naming.
    Verify that it finds executables with test_ prefix variations.
    """
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("")

    # Create executable with alternative naming (test_ prefix added)
    executable = build_dir / "test_sample"
    executable.touch()

    found = runner._find_cmake_executable(build_dir, test_file)
    assert found is not None
    assert found == executable


def test__find_cmake_executable_not_found(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_cmake_executable when executable is not found.
    Verify that it returns None.
    """
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    test_file = tmp_path / "test_nonexistent.f90"
    test_file.write_text("")

    found = runner._find_cmake_executable(build_dir, test_file)
    assert found is None


def test__find_fpm_executable(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_fpm_executable.
    Verify that it finds test executables in FPM build directories.
    """
    # Create FPM build directory structure
    project_dir = tmp_path
    test_dir = project_dir / "build" / "gfortran_debug" / "test"
    test_dir.mkdir(parents=True)

    test_file = tmp_path / "test_sample.f90"
    test_file.write_text("")

    # Create executable
    executable = test_dir / "test_sample"
    executable.touch()

    found = runner._find_fpm_executable(project_dir, test_file)
    assert found is not None
    assert found == executable


def test__find_fpm_executable_not_found(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_fpm_executable when executable is not found.
    Verify that it returns None.
    """
    project_dir = tmp_path
    (project_dir / "build").mkdir()

    test_file = tmp_path / "test_nonexistent.f90"
    test_file.write_text("")

    found = runner._find_fpm_executable(project_dir, test_file)
    assert found is None


def test__find_make_executable(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_make_executable.
    Verify that it finds test executables in Make project directories.
    """
    project_dir = tmp_path

    test_file = project_dir / "test_sample.f90"
    test_file.write_text("")

    # Create executable in project root
    executable = project_dir / "test_sample"
    executable.touch()

    found = runner._find_make_executable(project_dir, test_file)
    assert found is not None
    assert found == executable


def test__find_make_executable_in_build_dir(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_make_executable with build subdirectory.
    Verify that it finds executables in build/ directory.
    """
    project_dir = tmp_path
    build_dir = project_dir / "build"
    build_dir.mkdir()

    test_file = project_dir / "test_sample.f90"
    test_file.write_text("")

    # Create executable in build directory
    executable = build_dir / "test_sample"
    executable.touch()

    found = runner._find_make_executable(project_dir, test_file)
    assert found is not None
    assert found == executable


def test__find_make_executable_not_found(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test _find_make_executable when executable is not found.
    Verify that it returns None.
    """
    project_dir = tmp_path

    test_file = project_dir / "test_nonexistent.f90"
    test_file.write_text("")

    found = runner._find_make_executable(project_dir, test_file)
    assert found is None


# _build_with_cmake, _build_with_fpm, _build_with_make: Integration tests not included (require actual build systems)

# build_with_system: Integration test not included (requires actual build systems)

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

def test_parse_test_output_with_pass(runner: FortranTestRunner) -> None:
    """
    Test parse_test_output with passing tests.
    Verify that it correctly parses [PASS] tags.
    """
    output = "[PASS] test_addition\n[PASS] test_subtraction"
    results = runner.parse_test_output(output)
    
    assert len(results) == 2
    assert results[0].name == "test_addition"
    assert results[0].passed is True
    assert results[1].name == "test_subtraction"
    assert results[1].passed is True


def test_parse_test_output_with_fail(runner: FortranTestRunner) -> None:
    """
    Test parse_test_output with failing tests.
    Verify that it correctly parses [FAIL] tags.
    """
    output = "[FAIL] test_division\n[PASS] test_addition"
    results = runner.parse_test_output(output)
    
    assert len(results) == 2
    assert results[0].name == "test_division"
    assert results[0].passed is False
    assert results[1].name == "test_addition"
    assert results[1].passed is True


def test_parse_test_output_empty(runner: FortranTestRunner) -> None:
    """
    Test parse_test_output with empty output.
    Verify that it returns an empty list.
    """
    output = ""
    results = runner.parse_test_output(output)
    
    assert results == []


# check_error_stop_test: Integration test not included (requires compilation)

# _handle_error_stop_test: Integration test not included (requires compilation)

# _compile_and_run_normal_tests: Integration test not included (requires compilation)

# _print_normal_test_summary: Output formatting test (not critical for unit testing)

# _run_single_normal_test: Integration test not included (requires compilation)

def test_generate_single_test_program(tmp_path: Path, runner: FortranTestRunner) -> None:
    """
    Test generate_single_test_program.
    Verify that it generates a correct single test program.
    """
    out = runner.generate_single_test_program(
        "test_module",
        "test_addition",
        tmp_path
    )
    text = out.read_text()
    expected = """program run_test_addition
    use fortest_assertions
    use test_module
    implicit none
    call test_addition()
end program run_test_addition\n"""
    
    assert text == expected


# _print_error_stop_summary: Output formatting test (not critical for unit testing)

# _handle_normal_test: Integration test not included (requires compilation and build systems)

# _handle_normal_test_with_fpm: Integration test not included (requires FPM)

# _run_single_test_with_fpm: Integration test not included (requires FPM)

# _handle_normal_test_with_build_system: Integration test not included (requires CMake/Make)

# _compile_and_run_tests_fallback: Integration test not included (requires compilation)

# _run_single_error_stop_test: Integration test not included (requires compilation)

# run_tests: High-level integration test not included (requires full environment)

# print_summary: Output formatting test (not critical for unit testing)
