"""
Module for resolving Fortran module dependencies.
"""

import re
from pathlib import Path
from typing import ClassVar


class ModuleDependencyResolver:
    """
    Resolves module dependencies for Fortran test files.

    Analyzes 'use' statements in Fortran files to determine which module
    files need to be compiled before the test file.
    """
    # Fortran intrinsic modules
    INTRINSIC_MODULES: ClassVar[set[str]] = {
        "iso_fortran_env",
        "iso_c_binding",
        "ieee_arithmetic",
        "ieee_exceptions",
        "ieee_features",
    }

    # Maximum number of ancestor directories to search for project/source folders.
    SEARCH_DEPTH_MAX: int = 4

    # List of candidate subdirectories to scan inside each ancestor directory.
    TARGET_SUBDIRS: ClassVar[list[str]] = [
        "src",
        "app",
        "lib",
        "examples",
        "fortran/src",
    ]

    # Module name of fortest assertion
    ASSERTION_MODULE: ClassVar[str] = "fortest_assertions"

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize the module dependency resolver.

        Parameters
        ----------
        verbose : bool, optional
            Enable verbose output, by default False
        """
        self.verbose: bool = verbose


    def find_module_files(
        self,
        test_file: Path,
        include_assertions: bool = True,
    ) -> list[Path]:
        """
        Find module dependencies for a test file by analyzing 'use' statements.

        Note: When FPM is detected, dependency resolution is handled by FPM.
        This method is only used as a fallback for direct compilation.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        include_assertions : bool
            Whether to include fortest_assertions (only for standalone mode)

        Returns
        -------
        list[Path]
            List of module file paths that the test depends on (direct dependencies only)
        """
        modules: list[Path] = []
        test_file_abs: Path = test_file.resolve()

        # Extract module names used in the test file
        used_modules: list[str] = self.extract_use_statements(test_file_abs)

        # Build search directories
        search_dirs: list[Path] = self._build_search_directories(test_file_abs)

        # Find fortest_assertions if needed
        if include_assertions and self.ASSERTION_MODULE in used_modules:
            assertion_module = self._find_assertion_module(search_dirs)
            if assertion_module:
                modules.append(assertion_module)

        # Find user modules
        user_modules = self._find_user_modules(used_modules, search_dirs, test_file_abs)
        modules.extend(user_modules)

        return modules


    def extract_use_statements(self, file_path: Path) -> list[str]:
        """
        Extract module names from 'use' statements in a Fortran file.

        Parameters
        ----------
        file_path : Path
            Path to the Fortran file

        Returns
        -------
        list[str]
            List of module names used in the file (lowercase, unique)
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content: str = f.read()
        except (UnicodeDecodeError, OSError):
            # Skip files with encoding issues or read errors
            if self.verbose:
                print(f"Warning: Could not read {file_path} (encoding issue)")
            return []

        # Remove comments
        content = re.sub(r"!.*$", "", content, flags=re.MULTILINE)

        # Find use statements with flexible whitespace handling:
        # - use module_name
        # - use :: module_name
        # - use, intrinsic :: module_name
        # - use module_name, only: ...
        pattern: str = r"^\s*use\s*(?:,\s*intrinsic\s*)?(?:::\s*)?(\w+)"
        matches: list[str] = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)

        # Normalize to lowercase and remove duplicates
        unique_modules: list[str] = []
        seen: set[str] = set()
        for m in matches:
            name = m.lower()
            if name not in seen:
                seen.add(name)
                unique_modules.append(name)

        return unique_modules


    def extract_module_name(self, file_path: Path) -> str | None:
        """
        Extract module name from a Fortran file.

        Parameters
        ----------
        file_path : Path
            Path to the Fortran file

        Returns
        -------
        str | None
            Module name in lowercase, or None if not found
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content: str = f.read()
        except (UnicodeDecodeError, OSError):
            # Skip files with encoding issues or read errors
            if self.verbose:
                print(f"Warning: Could not read {file_path} (encoding issue)")
            return None

        # Remove comments
        content = re.sub(r"!.*$", "", content, flags=re.MULTILINE)

        # Find module name
        match: re.Match[str] | None = re.search(
            r"\bmodule\s+(\w+)",
            content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower()
        return None


    def find_fortran_files_recursive(self, directory: Path, max_depth: int = 3) -> list[Path]:
        """
        Recursively find all .f90 files in a directory up to max_depth.

        Parameters
        ----------
        directory : Path
            Directory to search
        max_depth : int
            Maximum depth to search (default: 3)

        Returns
        -------
        list[Path]
            List of found .f90 files
        """
        files: list[Path] = []

        def scan_dir(current_dir: Path, depth: int) -> None:
            if depth > max_depth or not current_dir.is_dir():
                return

            try:
                for item in current_dir.iterdir():
                    if item.is_file() and item.suffix == ".f90":
                        files.append(item)
                    elif item.is_dir() and not item.name.startswith('.'):
                        scan_dir(item, depth + 1)
            except PermissionError:
                # Skip directories we can't read
                pass

        scan_dir(directory, 0)
        return files


    def find_module_file_by_name(self, module_name: str, search_dirs: list[Path]) -> Path | None:
        """
        Find a Fortran file that defines the given module.

        First searches the provided search_dirs, then falls back to a broader
        recursive search from the current working directory if not found.

        Parameters
        ----------
        module_name : str
            Name of the module to find
        search_dirs : list[Path]
            Directories to search in

        Returns
        -------
        Path | None
            Path to the module file, or None if not found
        """
        for search_dir in search_dirs:
            # Search recursively in this directory
            for f90_file in self.find_fortran_files_recursive(search_dir):
                file_module = self.extract_module_name(f90_file)
                if file_module == module_name.lower():
                    return f90_file

        # Fallback: search the current working directory tree more broadly
        cwd = Path.cwd()
        if self.verbose:
            print(f"Module {module_name} not found in search_dirs, searching {cwd} recursively as fallback")
        for f90_file in self.find_fortran_files_recursive(cwd, max_depth=6):
            file_module = self.extract_module_name(f90_file)
            if file_module == module_name.lower():
                if self.verbose:
                    print(f"Found {module_name} at {f90_file} via fallback search")
                return f90_file

        return None


    def find_build_directories(self, test_file: Path) -> list[Path]:
        """
        Find build directories that may contain pre-compiled modules (.mod and .o files).

        Note: This is only used for fallback compilation when no build system is detected.
        When FPM is used, module files are managed by FPM itself.

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        list[Path]
            List of build directories found
        """
        build_dirs: list[Path] = []
        current: Path = test_file.resolve().parent

        # Search upward for build directories
        for _ in range(self.SEARCH_DEPTH_MAX):
            # Check for common build directory names
            for build_name in ["build", "Build", "BUILD"]:
                build_dir = current / build_name
                if build_dir.exists() and build_dir.is_dir():
                    build_dirs.append(build_dir)
                    # Also search subdirectories of build/
                    for subdir in build_dir.rglob("*"):
                        if subdir.is_dir() and any(subdir.glob("*.mod")):
                            build_dirs.append(subdir)

            if current == current.parent:
                break
            current = current.parent

        return build_dirs


    def _build_search_directories(self, test_file: Path) -> list[Path]:
        """
        Build list of directories to search for module files.

        Searches upward from test file location, looking for common
        FPM/CMake directory structures (src/, app/, lib/, examples/).

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        list[Path]
            List of directories to search (deduplicated, order-preserved)
        """
        search_dirs: list[Path] = []
        test_file_abs: Path = test_file.resolve()

        # Start from test file's parent and go up
        current: Path = test_file_abs.parent
        for _ in range(self.SEARCH_DEPTH_MAX):
            # Add common source directories
            for subdir in self.TARGET_SUBDIRS:
                candidate = current / subdir
                if candidate.exists() and candidate.is_dir():
                    search_dirs.append(candidate)

            # Also add current directory
            search_dirs.append(current)

            if current == current.parent:
                break

            # Move up one level
            current = current.parent

        # Remove duplicates while preserving order
        seen_dirs: set[Path] = set()
        unique_dirs: list[Path] = []
        for d in search_dirs:
            if d not in seen_dirs:
                seen_dirs.add(d)
                unique_dirs.append(d)

        return unique_dirs


    def _find_assertion_module(self, search_dirs: list[Path]) -> Path | None:
        """
        Find fortest_assertions module file. Falls back to bundled module shipped
        with the fortest package if not found in project search dirs.

        Parameters
        ----------
        search_dirs : list[Path]
            Directories to search in

        Returns
        -------
        Path | None
            Path to the assertion module file, or None if not found
        """
        for search_dir in search_dirs:
            for f90_file in self.find_fortran_files_recursive(search_dir, max_depth=2):
                if f90_file.name != "module_fortest_assertions.f90":
                    continue

                if self.verbose:
                    print(f"Using assertions from: {f90_file}")

                return f90_file

        # Fallback: use bundled module located next to runner.py
        bundled = Path(__file__).resolve().parent / "module_fortest_assertions.f90"
        if bundled.exists():
            if self.verbose:
                print(f"Using bundled assertions from: {bundled}")
            return bundled

        return None


    def _find_user_modules(
        self,
        used_modules: list[str],
        search_dirs: list[Path],
        test_file: Path,
    ) -> list[Path]:
        """
        Find user module files based on 'use' statements.

        Parameters
        ----------
        used_modules : list[str]
            List of module names to find
        search_dirs : list[Path]
            Directories to search in
        test_file : Path
            Path to the test file (to avoid including itself)

        Returns
        -------
        list[Path]
            List of found module files
        """
        modules: list[Path] = []
        test_file_abs: Path = test_file.resolve()

        for module_name in used_modules:
            # Skip intrinsic modules and fortest_assertions
            if module_name in self.INTRINSIC_MODULES or module_name == self.ASSERTION_MODULE:
                continue

            # Find module file for this dependency
            module_file = self.find_module_file_by_name(module_name, search_dirs)

            if not module_file:
                continue

            is_test_file: bool = module_file == test_file_abs
            is_in_modules: bool = module_file in modules

            if is_test_file or is_in_modules:
                continue

            modules.append(module_file)
            if self.verbose:
                print(f"Found dependency: {module_file} (provides {module_name})")

        return modules