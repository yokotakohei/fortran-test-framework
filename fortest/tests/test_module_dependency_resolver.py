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


def test_find_user_modules_recursive_with_transitive_dependencies(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test _find_user_modules_recursive.
    Verify that it recursively finds transitive dependencies in correct compilation order.
    """
    # Create directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create base module (no dependencies)
    base_module = src_dir / "base_module.f90"
    base_module.write_text("module base_module\nend module base_module\n")

    # Create middle module (depends on base_module)
    middle_module = src_dir / "middle_module.f90"
    middle_module.write_text("""module middle_module
    use base_module
end module middle_module
""")

    # Create top module (depends on middle_module)
    top_module = src_dir / "top_module.f90"
    top_module.write_text("""module top_module
    use middle_module
end module top_module
""")

    # Create test file
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    # Test recursive dependency resolution
    used_modules = ["top_module"]
    search_dirs = [src_dir]
    modules: list[Path] = []
    processed: set[Path] = set()

    resolver._find_user_modules_recursive(
        used_modules, search_dirs, test_file, modules, processed
    )

    # Should find all three modules in dependency order (base first)
    module_names = [f.stem for f in modules]
    assert module_names == ["base_module", "middle_module", "top_module"]


def test_find_user_modules_recursive_avoids_circular_dependencies(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test _find_user_modules_recursive with circular dependencies.
    Verify that it handles circular dependencies without infinite recursion.
    """
    # Create directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create module_a (depends on module_b)
    module_a = src_dir / "module_a.f90"
    module_a.write_text("""module module_a
    use module_b
end module module_a
""")

    # Create module_b (depends on module_a - circular!)
    module_b = src_dir / "module_b.f90"
    module_b.write_text("""module module_b
    use module_a
end module module_b
""")

    # Create test file
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.f90"
    test_file.write_text("module test_sample\nend module test_sample\n")

    # Test with circular dependency
    used_modules = ["module_a"]
    search_dirs = [src_dir]
    modules: list[Path] = []
    processed: set[Path] = set()

    # Should not raise an error or hang
    resolver._find_user_modules_recursive(
        used_modules, search_dirs, test_file, modules, processed
    )

    # Should find both modules (order may vary, but both should be present)
    module_names = {f.stem for f in modules}
    assert module_names == {"module_a", "module_b"}
    # Should only find each module once
    assert len(modules) == 2


def test_find_module_files_resolves_transitive_dependencies(
    tmp_path: Path,
    resolver: ModuleDependencyResolver,
) -> None:
    """
    Test find_module_files with transitive dependencies.
    Verify that it finds all dependencies including transitive ones in correct order.
    """
    # Create project layout
    project = tmp_path
    (project / "fortran" / "src").mkdir(parents=True)
    assertions = project / "fortran" / "src" / "module_fortest_assertions.f90"
    assertions.write_text(
        "module fortest_assertions\nend module fortest_assertions\n"
    )

    # Create source modules with dependency chain
    (project / "src").mkdir()
    
    # Base module (no dependencies)
    abstract_solver = project / "src" / "abstract_solver.f90"
    abstract_solver.write_text("module abstract_solver\nend module abstract_solver\n")
    
    # Base class (depends on abstract_solver)
    base_solver = project / "src" / "base_solver.f90"
    base_solver.write_text("""module base_solver
    use abstract_solver
end module base_solver
""")
    
    # Concrete implementation (depends on base_solver)
    ftcs_solver = project / "src" / "ftcs_solver.f90"
    ftcs_solver.write_text("""module ftcs_solver
    use base_solver
end module ftcs_solver
""")

    # Create test file (uses ftcs_solver)
    (project / "test").mkdir()
    test_file = project / "test" / "test_solver.f90"
    test_file.write_text("""module test_solver
    use fortest_assertions
    use ftcs_solver
end module test_solver
""")

    # Test find_module_files
    found = resolver.find_module_files(test_file, include_assertions=True)

    # Should find all modules in correct dependency order
    # Order: assertions, abstract_solver, base_solver, ftcs_solver
    module_names = [f.stem for f in found]
    
    # Verify all modules are found
    assert "module_fortest_assertions" in module_names
    assert "abstract_solver" in module_names
    assert "base_solver" in module_names
    assert "ftcs_solver" in module_names
    
    # Verify correct compilation order (dependencies before dependents)
    assert module_names.index("abstract_solver") < module_names.index("base_solver")
    assert module_names.index("base_solver") < module_names.index("ftcs_solver")
