"""
Tests for ModuleDependencyResolver class.
Tests are ordered according to method definitions in module_dependency_resolver.py.
"""

from pathlib import Path

import pytest

from fortest.module_dependency_resolver import ModuleDependencyResolver


def write_file(path: Path, content: str) -> None:
    """
    Helper function to write test files.
    """
    path.write_text(content)


@pytest.fixture
def resolver() -> ModuleDependencyResolver:
    """
    Create a ModuleDependencyResolver instance for testing
    """
    return ModuleDependencyResolver(verbose=False)


def test_find_module_files_finds_assertions_and_user_modules(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test find_module_files.
    Verify that it finds assertion and modules.
    """
    # Create project layout
    project = tmp_path
    (project / "fortran" / "src").mkdir(parents=True)
    assertions = project / "fortran" / "src" / "module_fortest_assertions.f90"
    assertions.write_text(
        "module fortest_assertions\nend module fortest_assertions\n"
    )

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

    found = resolver.find_module_files(test_file)

    # Should find both assertions and user module
    found_names = sorted([p.name for p in found])
    assert found_names == ["module_fortest_assertions.f90", "module_sample.f90"]


def test_extract_use_statements(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
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
    uses = resolver.extract_use_statements(f)

    # Should find all use statements (lowercase, unique), comment should be ignored
    assert uses == [
        "iso_fortran_env",
        "module_a",
        "iso_c_binding",
        "module_b",
        "module_d",
    ]


def test_extract_use_statements_with_comments(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
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
    uses = resolver.extract_use_statements(f)

    # module_b should not be in the list (it's commented out)
    assert "module_a" in uses
    assert "module_c" in uses
    assert "module_b" not in uses


def test_extract_module_name(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test extract_module_name.
    Verify that it extracts a module name as lower case.
    """
    f = tmp_path / "test_mod.f90"
    write_file(f, "  module My_Module \n end module My_Module \n")
    name = resolver.extract_module_name(f)
    assert name == "my_module"


def test_extract_module_name_no_module(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test extract_module_name when no module is defined.
    Verify that it returns None.
    """
    f = tmp_path / "program.f90"
    write_file(f, "program main\nend program main\n")
    name = resolver.extract_module_name(f)
    assert name is None


def test_find_fortran_files_recursive(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
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

    files = resolver.find_fortran_files_recursive(tmp_path / "src")
    names = sorted([f.name for f in files])

    assert names == ["mod1.f90", "mod2.f90", "mod3.f90"]


def test_find_module_file_by_name(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
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

    found1 = resolver.find_module_file_by_name("my_awesome_module", search_dirs)
    assert found1 is not None
    assert found1.name == "my_module.f90"

    found2 = resolver.find_module_file_by_name("utilities", search_dirs)
    assert found2 is not None
    assert found2.name == "util.f90"


def test_find_assertion_module(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test _find_assertion_module.
    Verify that it finds module_fortest_assertions.f90.
    """
    # Create directory with assertions module
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    assertions_file = src_dir / "module_fortest_assertions.f90"
    assertions_file.write_text(
        "module fortest_assertions\nend module fortest_assertions\n"
    )

    search_dirs = [src_dir]
    found = resolver._find_assertion_module(search_dirs)

    assert found is not None
    assert found.name == "module_fortest_assertions.f90"
    assert found == assertions_file


def test_find_user_modules(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
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
    found_modules = resolver._find_user_modules(used_modules, search_dirs, test_file)

    # Should find only user modules
    found_names = {f.stem for f in found_modules}
    assert found_names == {"module_a", "module_b"}