#!/usr/bin/env python3
"""
Module providing implements the core functionality of fortest.
"""

from typing import ClassVar
import glob
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fortest.test_result import Colors, MessageTag, TestResult
from fortest.exit_status import ExitStatus


@dataclass(frozen=True)
class BuildSystemInfo:
    """
    Information about detected build system.

    Attributes
    ----------
    build_type : str
        Type of build system ('cmake', 'fpm', or 'make')
    project_dir : Path
        Root directory of the project
    """
    build_type: str
    project_dir: Path


class FortranTestRunner:
    """
    Test runner for Fortran test files.

    Attributes
    ----------
    compiler : str
        Fortran compiler command
    verbose : bool
        Enable verbose output
    build_dir : Path | None
        Build directory for temporary files
    total_tests : int
        Total number of tests executed
    passed_tests : int
        Number of tests that passed
    failed_tests : int
        Number of tests that failed
    error_stop_tests : int
        Number of error_stop tests
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
    # Limits how far _build_search_directories climbs upward from a test file (default: 4).
    SEARCH_DEPTH_MAX: int = 4

    # List of candidate subdirectories to scan inside each ancestor directory when locating source/module files.
    # Typical values cover common Fortran project layouts (src, app, lib, examples) and the repo's fortran/src.
    TARGET_SUBDIRS: ClassVar[list[str]] = [
        "src",
        "app",
        "lib",
        "examples",
        "fortran/src",
    ]

    # Module name of fortest assertion
    ASSERTION_MODULE: ClassVar[str] = "fortest_assertions"
    
    def __init__(self,
        compiler: str = "gfortran",
        verbose: bool = False,
        build_dir: Path | None = None,
    ) -> None:
        self.compiler: str = compiler
        self.verbose: bool = verbose
        self.build_dir: Path | None = build_dir
        self.total_tests: int = 0
        self.passed_tests: int = 0
        self.failed_tests: int = 0
        self.error_stop_tests: int = 0


    def find_test_files(self, pattern: str) -> list[Path]:
        """
        Find all Fortran test files matching the pattern.

        Parameters
        ----------
        pattern : str
            File pattern, directory path, or specific file path to search for

        Returns
        -------
        list[Path]
            List of test file paths found (resolved and deduplicated)
        """
        # If pattern is a specific file, return it
        p: Path = Path(pattern)
        if p.exists() and p.is_file() and pattern.endswith(".f90"):
            return [p.resolve()]

        # If pattern is a directory, search within it
        if p.exists() and p.is_dir():
            found: list[Path] = []
            for test_pattern in ["test_*.f90", "module_test_*.f90"]:
                for file in p.glob(test_pattern):
                    if file.is_file():
                        found.append(file.resolve())

            # Deduplicate while preserving order
            seen: set[Path] = set()
            unique: list[Path] = []
            for p in found:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)
            return unique

        # Otherwise search for pattern and normalize/resolve results
        found = []
        for file in glob.glob(pattern, recursive=True):
            if file.endswith(".f90"):
                found.append(Path(file).resolve())
        for file in glob.glob(f"**/{pattern}", recursive=True):
            if file.endswith(".f90"):
                found.append(Path(file).resolve())

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for p in found:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return unique


    def _find_build_directories(self, test_file: Path) -> list[Path]:
        """
        Find build directories that may contain pre-compiled modules (.mod and .o files).

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
        search_depth_max: int = FortranTestRunner.SEARCH_DEPTH_MAX
        target_subdirs: list[str] = FortranTestRunner.TARGET_SUBDIRS
        for _ in range(search_depth_max):
            # Add common source directories
            for subdir in target_subdirs:
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
        """
        for search_dir in search_dirs:
            for f90_file in self.find_fortran_files_recursive(search_dir, max_depth=2):
                if f90_file.name != "module_fortest_assertions.f90":
                    continue

                if self.verbose:
                    print(f"Using assertions from: {f90_file}")

                return f90_file

        # Fallback: use bundled module located next to this runner.py
        bundled = Path(__file__).resolve().parent / "module_fortest_assertions.f90"
        if bundled.exists():
            if self.verbose:
                print(f"Using bundled assertions from: {bundled}")
            return bundled

        return None


    def _find_user_modules(self,
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
        intrinsic_modules = FortranTestRunner.INTRINSIC_MODULES

        for module_name in used_modules:
            # Skip intrinsic modules and fortest_assertions
            fortest_assertions: str = FortranTestRunner.ASSERTION_MODULE
            if module_name in intrinsic_modules or module_name == fortest_assertions:
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


    def find_module_files(self,
        test_file: Path,
        include_assertions: bool = True,
    ) -> list[Path]:
        """
        Find module dependencies for a test file by analyzing 'use' statements.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        include_assertions : bool
            Whether to include fortest_assertions (only for standalone mode)

        Returns
        -------
        list[Path]
            List of module file paths that the test depends on
        """
        modules: list[Path] = []
        test_file_abs: Path = test_file.resolve()

        # Extract module names used in the test file
        used_modules: list[str] = self.extract_use_statements(test_file_abs)

        # Build search directories
        search_dirs: list[Path] = self._build_search_directories(test_file_abs)

        # Find fortest_assertions if needed
        fortest_assertions: str = FortranTestRunner.ASSERTION_MODULE
        if include_assertions and fortest_assertions in used_modules:
            assertion_module = self._find_assertion_module(search_dirs)
            if assertion_module:
                modules.append(assertion_module)

        # Find user modules
        user_modules = self._find_user_modules(used_modules, search_dirs, test_file_abs)
        modules.extend(user_modules)

        return modules


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
        with open(file_path, "r") as f:
            content: str = f.read()

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
        with open(file_path, "r") as f:
            content: str = f.read()

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


    def extract_test_subroutines(self, test_file: Path) -> list[str]:
        """
        Extract test subroutine names from a Fortran test file.

        Looks for subroutines that start with "test_".

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        list[str]
            List of test subroutine names in lowercase (unique, order-preserving)
        """
        with open(test_file, "r") as f:
            content: str = f.read()

        # Remove comments
        content = re.sub(r"!.*$", "", content, flags=re.MULTILINE)

        # Match only lines that start a subroutine (avoid "end subroutine ...")
        pattern: str = r"(?mi)^\s*subroutine\s+(test_\w+)\b"
        matches: list[str] = re.findall(pattern, content)

        # Normalize to lowercase and remove duplicates preserving order
        seen: set[str] = set()
        test_subroutines: list[str] = []
        for m in matches:
            name: str = m.lower()
            if name not in seen:
                seen.add(name)
                test_subroutines.append(name)

        if self.verbose:
            print(f"Found test subroutines: {test_subroutines}")

        return test_subroutines


    def separate_error_stop_tests(self,
        test_subroutines: list[str]
    ) -> tuple[list[str], list[str]]:
        """
        Separate normal tests from error_stop tests.

        Parameters
        ----------
        test_subroutines : list[str]
            List of all test subroutine names

        Returns
        -------
        tuple[list[str], list[str]]
            Tuple of (normal_tests, error_stop_tests)
        """
        normal_tests: list[str] = []
        error_stop_tests: list[str] = []

        for test_name in test_subroutines:
            if "error_stop" in test_name:
                error_stop_tests.append(test_name)
            else:
                normal_tests.append(test_name)

        return normal_tests, error_stop_tests


    def generate_test_program(self,
        test_file: Path,
        test_module_name: str,
        test_subroutines: list[str],
        output_dir: Path,
    ) -> Path:
        """
        Generate a main program that calls all test subroutines.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        test_module_name : str
            Name of the test module
        test_subroutines : list[str]
            List of test subroutine names to call
        output_dir : Path
            Directory to write the generated program

        Returns
        -------
        Path
            Path to the generated program file
        """
        fortest_assertions: str = FortranTestRunner.ASSERTION_MODULE
        program_content: str = f"program run_{test_file.stem}\n"
        program_content += f"    use {fortest_assertions}\n"
        program_content += f"    use {test_module_name}\n"
        program_content += "    implicit none\n"

        # Call all test subroutines
        for test_sub in test_subroutines:
            program_content += f"    call {test_sub}()\n"

        program_content += "    call print_summary()\n"
        program_content += f"end program run_{test_file.stem}\n"

        generated_file: Path = output_dir / f"gen_runner_{test_file.name}"
        with open(generated_file, "w") as f:
            f.write(program_content)

        if self.verbose:
            print(f"Generated program:\n{program_content}")

        return generated_file


    def generate_error_stop_test_program(
        self,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
    ) -> Path:
        """
        Generate a standalone program for an error_stop test.

        Parameters
        ----------
        test_module_name : str
            Name of the test module
        test_subroutine : str
            Name of the test subroutine to call
        output_dir : Path
            Directory to write the generated program

        Returns
        -------
        Path
            Path to the generated program file
        """
        program_content: str = f"program run_{test_subroutine}\n"
        program_content += f"    use {test_module_name}\n"
        program_content += "    implicit none\n"
        program_content += f"    call {test_subroutine}()\n"
        program_content += f"end program run_{test_subroutine}\n"

        generated_file: Path = output_dir / f"gen_{test_subroutine}.f90"
        with open(generated_file, "w") as f:
            f.write(program_content)

        if self.verbose:
            print(f"Generated error_stop test program:\n{program_content}")

        return generated_file


    def detect_build_system(self, test_file: Path) -> BuildSystemInfo | None:
        """
        Detect if the project has a build system configuration.

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        BuildSystemInfo | None
            Build system information if detected, None otherwise
        """
        # Start from test file directory and search upwards
        current: Path = test_file.resolve().parent

        while current != current.parent:  # Stop at filesystem root
            # Check for CMakeLists.txt
            if (current / "CMakeLists.txt").exists():
                return BuildSystemInfo("cmake", current)

            # Check for fpm.toml
            if (current / "fpm.toml").exists():
                return BuildSystemInfo("fpm", current)

            # Check for Makefile
            if (current / "Makefile").exists():
                return BuildSystemInfo("make", current)

            current = current.parent

        return None


    def _find_cmake_executable(self, build_dir: Path, test_file: Path) -> Path | None:
        """
        Find test executable in CMake build directory.

        Parameters
        ----------
        build_dir : Path
            CMake build directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        test_stem: str = test_file.stem
        possible_names: list[str] = [
            test_stem,
            f"test_{test_stem.replace('test_', '')}",
            # fallback for examples
            "test_sample_module",
        ]

        for name in possible_names:
            executable: Path = build_dir / name
            if executable.exists():
                return executable

        if self.verbose:
            print(f"Warning: Could not find test executable in {build_dir}")
        return None


    def _find_fpm_executable(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Find test executable in FPM build directory.

        Parameters
        ----------
        project_dir : Path
            FPM project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        build_dir: Path = project_dir / "build"
        test_stem: str = test_file.stem

        for test_dir in build_dir.glob("gfortran_*/test"):
            executable: Path = test_dir / test_stem
            if executable.exists():
                return executable

        if self.verbose:
            print(f"Warning: Could not find test executable in {build_dir}")
        return None


    def _find_make_executable(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Find test executable in Make build directory.

        Parameters
        ----------
        project_dir : Path
            Make project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        test_stem: str = test_file.stem
        possible_paths: list[Path] = [
            project_dir / test_stem,
            project_dir / "build" / test_stem,
            project_dir / f"test_{test_stem.replace('test_', '')}",
        ]

        for executable in possible_paths:
            if executable.exists():
                return executable

        if self.verbose:
            print(f"Warning: Could not find test executable")
        return None


    def _build_with_cmake(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Build the project using CMake.

        Parameters
        ----------
        project_dir : Path
            CMake project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        build_dir: Path = project_dir / "build"
        build_dir.mkdir(exist_ok=True)

        # Run cmake configuration
        subprocess.run(
            ["cmake", ".."],
            cwd=build_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        # Build
        subprocess.run(
            ["make"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        return self._find_cmake_executable(build_dir, test_file)


    def _build_with_fpm(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Build the project using FPM (Fortran Package Manager).

        Parameters
        ----------
        project_dir : Path
            FPM project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        subprocess.run(
            ["fpm", "build"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        return self._find_fpm_executable(project_dir, test_file)


    def _build_with_make(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Build the project using Make.

        Parameters
        ----------
        project_dir : Path
            Make project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        subprocess.run(
            ["make"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        return self._find_make_executable(project_dir, test_file)


    def build_with_system(self, build_info: BuildSystemInfo, test_file: Path) -> Path | None:
        """
        Build the project using the detected build system.

        Parameters
        ----------
        build_info : BuildSystemInfo
            Build system information from detect_build_system
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        build_type: str = build_info.build_type
        project_dir: Path = build_info.project_dir

        if self.verbose:
            print(f"Detected {build_type} build system in {project_dir}")

        try:
            if build_type == "cmake":
                return self._build_with_cmake(project_dir, test_file)
            elif build_type == "fpm":
                return self._build_with_fpm(project_dir, test_file)
            elif build_type == "make":
                return self._build_with_make(project_dir, test_file)

        except subprocess.CalledProcessError as e:
            print(
                f"{Colors.RED.value}Build failed with {build_type}"
                f"{Colors.RESET.value}"
            )
            if self.verbose:
                print(e.stderr)
            return None
        except Exception as e:
            if self.verbose:
                print(f"Error during build: {e}")
            return None

        return None


    def _is_standalone_program(self, test_file: Path) -> bool:
        """
        Check if a test file is a standalone program (not a module).

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        bool
            True if the file contains a program statement or is an error_stop test
        """
        with open(test_file, "r") as f:
            content: str = f.read()
        is_program: re.Match[str] | None = re.search(
            r"\bprogram\s+\w+",
            content,
            re.IGNORECASE,
        )
        return "error_stop" in test_file.name.lower() or is_program is not None


    def _compile_standalone_program(self, test_file: Path, output_dir: Path) -> Path | None:
        """
        Compile a standalone Fortran program.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        Path | None
            Path to the compiled executable, or None if compilation failed
        """
        executable: Path = output_dir / test_file.stem
        compile_cmd: list[str] = [
            self.compiler,
            "-o",
            str(executable),
            str(test_file),
        ]

        if self.verbose:
            print(f"Compiling error_stop test: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return executable
        except subprocess.CalledProcessError as e:
            print(
                f"{Colors.RED.value}Compilation failed for {test_file}"
                f"{Colors.RESET.value}"
            )
            print(e.stderr)
            return None


    def _compile_module_test(self, test_file: Path, output_dir: Path) -> Path | None:
        """
        Compile a module-based test file with its dependencies.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        Path | None
            Path to the compiled executable, or None if compilation failed
        """
        # Extract test information
        test_module_name: str | None = self.extract_module_name(test_file)
        if not test_module_name:
            print(
                f"{Colors.YELLOW.value}Warning: Could not find module in "
                f"{test_file}{Colors.RESET.value}"
            )
            return None

        test_subroutines: list[str] = self.extract_test_subroutines(test_file)
        if not test_subroutines:
            print(
                f"{Colors.YELLOW.value}Warning: No test subroutines found in "
                f"{test_file}{Colors.RESET.value}"
            )
            return None

        # Find module dependencies (including assertions for standalone mode)
        module_files: list[Path] = self.find_module_files(test_file, include_assertions=True)

        # Generate main program
        main_program: Path = self.generate_test_program(
            test_file,
            test_module_name,
            test_subroutines,
            output_dir,
        )

        # Compile all files
        executable = output_dir / test_file.stem
        compile_cmd = [self.compiler, "-o", str(executable)]

        # Add all module files in dependency order
        compile_cmd.extend([str(f) for f in module_files])
        compile_cmd.append(str(test_file))
        compile_cmd.append(str(main_program))

        if self.verbose:
            print(f"Compiling: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return executable
        except subprocess.CalledProcessError as e:
            print(
                f"{Colors.RED.value}Compilation failed for {test_file}"
                f"{Colors.RESET.value}"
            )
            print(e.stderr)
            return None


    def compile_test(self, test_file: Path, output_dir: Path) -> Path | None:
        """
        Compile a Fortran test file with its dependencies.

        First tries to use a detected build system (CMake, FPM, Make),
        then falls back to direct compilation with gfortran.

        Parameters
        ----------
        test_file : Path
            Path to the test file to compile
        output_dir : Path
            Directory for output executable

        Returns
        -------
        Path | None
            Path to the compiled executable, or None if compilation failed
        """
        # Try to detect and use build system first
        build_info: BuildSystemInfo | None = self.detect_build_system(test_file)
        if build_info is not None:
            executable_built: Path | None = self.build_with_system(build_info, test_file)
            if executable_built is not None:
                return executable_built

            # If build system detected but failed, fall back to direct compilation
            if self.verbose:
                print("Falling back to direct compilation with gfortran")

        # Check if this is a standalone program or module-based test
        if self._is_standalone_program(test_file):
            return self._compile_standalone_program(test_file, output_dir)
        else:
            return self._compile_module_test(test_file, output_dir)


    def run_test_executable(self, executable: Path) -> tuple[bool, str, int]:
        """
        Run a compiled test executable.

        Parameters
        ----------
        executable : Path
            Path to the executable to run

        Returns
        -------
        tuple[bool, str, int]
            Tuple of (success, output, returncode)
        """
        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30,
            )
            return True, result.stdout, result.returncode
        except subprocess.TimeoutExpired:
            return False, "Test timed out", -1
        except Exception as e:
            return False, str(e), -1


    def parse_test_output(self, output: str) -> list[TestResult]:
        """
        Parse the output from a test run.

        Parameters
        ----------
        output : str
            Standard output from the test executable

        Returns
        -------
        list[TestResult]
            List of parsed test results
        """
        results: list[TestResult] = []
        lines: list[str] = output.strip().split("\n")

        for line in lines:
            # Remove ANSI color codes first
            clean: str = re.sub(r"\x1b\[[0-9;]*m", "", line).rstrip()

            # Skip Fortran summary lines like "[PASS]   9" or "[FAIL]   0"
            if re.search(rf"{re.escape(MessageTag.PASS.value)}\s*\d+\s*$", clean) \
            or re.search(rf"{re.escape(MessageTag.FAIL.value)}\s*\d+\s*$", clean):
                continue

            if MessageTag.PASS.value in clean:
                test_name: str = clean.split(MessageTag.PASS.value, 1)[1].strip()
                results.append(TestResult(test_name, True))
            elif MessageTag.FAIL.value in clean:
                test_name: str = clean.split(MessageTag.FAIL.value, 1)[1].strip()
                results.append(TestResult(test_name, False))

        return results


    def check_error_stop_test(self, test_file: Path, output_dir: Path) -> list[TestResult]:
        """
        Handle tests that are expected to call error stop.

        These tests should terminate with error stop, which is detected
        by non-zero exit code.

        Parameters
        ----------
        test_file : Path
            Path to the error_stop test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        list[TestResult]
            List containing the test result
        """
        executable: Path | None = self.compile_test(test_file, output_dir)

        if executable is None:
            return [TestResult(str(test_file), False, "Compilation failed")]

        output: str
        returncode: int
        _, output, returncode = self.run_test_executable(executable)

        results: list[TestResult] = []

        # error stop should cause non-zero return code (usually 2 for gfortran)
        if returncode != 0:
            # Check if it's the expected error stop
            if (returncode == 2 or
                "ERROR STOP" in output.upper() or
                "error stop" in output.lower()):
                results.append(TestResult(
                    f"{test_file.name} (error_stop expected)",
                    True,
                    "Correctly triggered error stop",
                ))
                self.error_stop_tests += 1
            else:
                results.append(TestResult(
                    f"{test_file.name} (error_stop expected)",
                    False,
                    f"Unexpected error (exit code {returncode}): {output}",
                ))
        else:
            results.append(TestResult(
                f"{test_file.name} (error_stop expected)",
                False,
                "Expected error stop but test completed normally",
            ))

        return results


    def _handle_error_stop_test(self, test_file: Path, output_dir: Path) -> list[TestResult]:
        """
        Handle error_stop test execution and printing.

        Parameters
        ----------
        test_file : Path
            Path to the error_stop test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        list[TestResult]
            List of test results
        """
        results: list[TestResult] = self.check_error_stop_test(
            test_file,
            output_dir,
        )

        # Print results for error_stop tests
        for result in results:
            if result.passed:
                print(
                    f"{Colors.GREEN.value}{MessageTag.PASS.value}{Colors.RESET.value} "
                    f"{result.name}"
                )
                if result.message:
                    print(f"       {result.message}")
            else:
                print(
                    f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} "
                    f"{result.name}"
                )
                if result.message:
                    print(f"       {result.message}")

        return results


    def _compile_and_run_normal_tests(self,
        test_file: Path,
        test_module_name: str,
        normal_tests: list[str],
        output_dir: Path,
    ) -> list[TestResult]:
        """
        Compile and run normal (non-error_stop) tests.
        
        Each test is run individually to prevent error stop in one test
        from preventing execution of subsequent tests.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        test_module_name : str
            Name of the test module
        normal_tests : list[str]
            List of normal test subroutine names
        output_dir : Path
            Directory for output executable

        Returns
        -------
        list[TestResult]
            List of test results
        """
        all_results: list[TestResult] = []
        
        # Run each normal test individually
        for test_subroutine in normal_tests:
            result: TestResult = self._run_single_normal_test(
                test_file,
                test_module_name,
                test_subroutine,
                output_dir,
            )
            all_results.append(result)
        
        # Print summary for normal tests if any were run
        if all_results:
            self._print_normal_test_summary(all_results)
        
        return all_results


    def _print_normal_test_summary(self, normal_results: list[TestResult]) -> None:
        """
        Print summary for normal tests.

        Parameters
        ----------
        normal_results : list[TestResult]
            List of normal test results
        """
        separator: str = "=" * 50
        normal_passed: int = sum(1 for r in normal_results if r.passed)
        normal_failed: int = len(normal_results) - normal_passed

        print()
        print(separator)
        print(f"Normal tests: {len(normal_results)}")
        print(f"{Colors.GREEN.value}{MessageTag.PASS.value}{normal_passed:>4}{Colors.RESET.value}")
        print(f"{Colors.RED.value}{MessageTag.FAIL.value}{normal_failed:>4}{Colors.RESET.value}")
        print(separator)
        print()


    def _run_single_normal_test(
        self,
        test_file: Path,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
    ) -> TestResult:
        """
        Run a single normal test.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        test_module_name : str
            Name of the test module
        test_subroutine : str
            Name of the test subroutine
        output_dir : Path
            Directory for output executable

        Returns
        -------
        TestResult
            Test result
        """
        # Find module dependencies
        module_files: list[Path] = self.find_module_files(test_file)

        # Generate standalone program for this test
        normal_program: Path = self.generate_single_test_program(
            test_module_name,
            test_subroutine,
            output_dir,
        )

        if self.verbose:
            print(f"Generated program for {test_subroutine}:")
            with open(normal_program, 'r') as f:
                print(f.read())

        # Find build directories for pre-compiled modules
        build_dirs: list[Path] = self._find_build_directories(test_file)

        # Compile module dependencies that don't have pre-compiled versions
        compiled_objects: list[Path] = []
        for module_file in module_files:
            compile_mod_cmd: list[str] = [
                self.compiler,
                "-c",
                str(module_file),
            ]
            # Add build directories to module search path
            for build_dir in build_dirs:
                compile_mod_cmd.extend(["-I", str(build_dir)])
            # Output to temp directory
            compile_mod_cmd.extend([
                "-J", str(output_dir),
                "-o", str(output_dir / f"{module_file.stem}.o"),
            ])

            if self.verbose:
                print(f"Compiling module dependency: {' '.join(compile_mod_cmd)}")
            try:
                subprocess.run(
                    compile_mod_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                compiled_objects.append(output_dir / f"{module_file.stem}.o")
            except subprocess.CalledProcessError as e:
                return TestResult(
                    test_subroutine,
                    False,
                    f"Failed to compile dependency {module_file.name}: {e.stderr}",
                )

        # Compile test file and main program
        executable: Path = output_dir / f"{test_subroutine}_normal"
        compile_cmd: list[str] = [
            self.compiler,
            "-o", str(executable),
        ]
        # Add build directories to module search path
        for build_dir in build_dirs:
            compile_cmd.extend(["-I", str(build_dir)])
        # Add temp directory for newly compiled modules
        compile_cmd.extend(["-I", str(output_dir), "-J", str(output_dir)])
        # Add compiled module objects
        compile_cmd.extend([str(obj) for obj in compiled_objects])
        compile_cmd.append(str(test_file))
        compile_cmd.append(str(normal_program))

        if self.verbose:
            print(f"Compiling normal test {test_subroutine}: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            return TestResult(
                test_subroutine,
                False,
                f"Compilation failed: {e.stderr}",
            )

        # Run the test
        success: bool
        output: str
        returncode: int
        success, output, returncode = self.run_test_executable(executable)

        if not success:
            return TestResult(
                test_subroutine,
                False,
                f"Test execution failed: {output}",
            )

        # Parse output to get test results
        results: list[TestResult] = self.parse_test_output(output)
        
        # Print the raw output from the test (includes details like "xx vs yy")
        # Only print if output is non-empty after stripping
        if output.strip():
            print(output.rstrip())
        
        # If output parsing failed to find results, check return code
        if not results:
            # If error stop occurred (non-zero return code), treat as failure
            if returncode != 0:
                print(f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} {test_subroutine}")
                print(f"       Test caused error stop or abnormal termination (exit code {returncode})")
                return TestResult(
                    test_subroutine,
                    False,
                    f"Error stop or abnormal termination (exit code {returncode})",
                )
            # Otherwise no assertions were found, treat as passed
            return TestResult(test_subroutine, True)
        
        # Return the first result (should only be one per test)
        return results[0] if results else TestResult(test_subroutine, True)


    def generate_single_test_program(
        self,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
    ) -> Path:
        """
        Generate a standalone program for a single normal test.

        Parameters
        ----------
        test_module_name : str
            Name of the test module
        test_subroutine : str
            Name of the test subroutine to call
        output_dir : Path
            Directory to write the generated program

        Returns
        -------
        Path
            Path to the generated program file
        """
        fortest_assertions: str = FortranTestRunner.ASSERTION_MODULE
        program_content: str = f"program run_{test_subroutine}\n"
        program_content += f"    use {fortest_assertions}\n"
        program_content += f"    use {test_module_name}\n"
        program_content += "    implicit none\n"
        program_content += f"    call {test_subroutine}()\n"
        program_content += f"end program run_{test_subroutine}\n"

        generated_file: Path = output_dir / f"gen_{test_subroutine}.f90"
        with open(generated_file, "w") as f:
            f.write(program_content)

        if self.verbose:
            print(f"Generated program for {test_subroutine}:\n{program_content}")

        return generated_file


    def _print_error_stop_summary(self, error_stop_results: list[TestResult]) -> None:
        """
        Print summary for error_stop tests.

        Parameters
        ----------
        error_stop_results : list[TestResult]
            List of error_stop test results
        """
        # Count pass/fail for error_stop tests
        error_stop_passed: int = sum(1 for r in error_stop_results if r.passed)
        error_stop_failed: int = len(error_stop_results) - error_stop_passed

        # Print individual results
        for result in error_stop_results:
            if result.passed:
                print(
                    f"{Colors.GREEN.value}{MessageTag.PASS.value}{Colors.RESET.value} "
                    f"{result.name}"
                )
            else:
                print(
                    f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} "
                    f"{result.name}"
                )
                if result.message:
                    print(f"       {result.message}")

        separator: str = "=" * 50
        print()
        print(separator)
        print(f"error_stop tests: {len(error_stop_results)}")
        print(f"{Colors.GREEN.value}{MessageTag.PASS.value}{error_stop_passed:>4}{Colors.RESET.value}")
        print(f"{Colors.RED.value}{MessageTag.FAIL.value}{error_stop_failed:>4}{Colors.RESET.value}")
        print(separator)
        print()


    def _handle_normal_test(self, test_file: Path, output_dir: Path) -> list[TestResult]:
        """
        Handle normal test execution and printing.
        Separates error_stop tests and runs them individually.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        list[TestResult]
            List of test results
        """
        # Extract module and test information
        test_module_name: str | None = self.extract_module_name(test_file)
        if not test_module_name:
            print(
                f"{Colors.YELLOW.value}Warning: Could not find module in "
                f"{test_file}{Colors.RESET.value}"
            )
            return []

        all_test_subroutines: list[str] = self.extract_test_subroutines(test_file)
        if not all_test_subroutines:
            print(
                f"{Colors.YELLOW.value}Warning: No test subroutines found in "
                f"{test_file}{Colors.RESET.value}"
            )
            return []

        # Separate normal tests from error_stop tests
        normal_tests, error_stop_tests = self.separate_error_stop_tests(all_test_subroutines)

        all_results: list[TestResult] = []

        # Run normal tests together
        if normal_tests:
            normal_results: list[TestResult] = self._compile_and_run_normal_tests(
                test_file,
                test_module_name,
                normal_tests,
                output_dir,
            )
            all_results.extend(normal_results)

        # Run error_stop tests individually
        error_stop_results: list[TestResult] = []
        for error_stop_test in error_stop_tests:
            result: TestResult = self._run_single_error_stop_test(
                test_file,
                test_module_name,
                error_stop_test,
                output_dir,
            )
            error_stop_results.append(result)
            all_results.append(result)

        # Print error_stop tests summary if any
        if error_stop_results:
            self._print_error_stop_summary(error_stop_results)

        return all_results


    def _run_single_error_stop_test(
        self,
        test_file: Path,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
    ) -> TestResult:
        """
        Run a single error_stop test.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        test_module_name : str
            Name of the test module
        test_subroutine : str
            Name of the error_stop test subroutine
        output_dir : Path
            Directory for output executable

        Returns
        -------
        TestResult
            Test result
        """
        # Find module dependencies
        module_files: list[Path] = self.find_module_files(test_file)

        # Generate standalone program for this error_stop test
        error_program: Path = self.generate_error_stop_test_program(
            test_module_name,
            test_subroutine,
            output_dir,
        )

        # Find build directories for pre-compiled modules
        build_dirs: list[Path] = self._find_build_directories(test_file)

        # Compile module dependencies that don't have pre-compiled versions
        compiled_objects: list[Path] = []
        for module_file in module_files:
            compile_mod_cmd: list[str] = [
                self.compiler,
                "-c",
                str(module_file),
            ]
            # Add build directories to module search path
            for build_dir in build_dirs:
                compile_mod_cmd.extend(["-I", str(build_dir)])
            # Output to temp directory
            compile_mod_cmd.extend([
                "-J", str(output_dir),
                "-o", str(output_dir / f"{module_file.stem}.o"),
            ])

            if self.verbose:
                print(f"Compiling module dependency: {' '.join(compile_mod_cmd)}")
            try:
                subprocess.run(
                    compile_mod_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                compiled_objects.append(output_dir / f"{module_file.stem}.o")
            except subprocess.CalledProcessError as e:
                return TestResult(
                    test_subroutine,
                    False,
                    f"Failed to compile dependency {module_file.name}: {e.stderr}",
                )

        # Compile test file and main program
        executable: Path = output_dir / test_subroutine
        compile_cmd: list[str] = [
            self.compiler,
            "-o", str(executable),
        ]
        # Add build directories to module search path
        for build_dir in build_dirs:
            compile_cmd.extend(["-I", str(build_dir)])
        # Add temp directory for newly compiled modules
        compile_cmd.extend(["-I", str(output_dir), "-J", str(output_dir)])
        # Add compiled module objects
        compile_cmd.extend([str(obj) for obj in compiled_objects])
        compile_cmd.append(str(test_file))
        compile_cmd.append(str(error_program))

        if self.verbose:
            print(f"Compiling error_stop test {test_subroutine}: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            return TestResult(
                test_subroutine,
                False,
                f"Compilation failed: {e.stderr}",
            )

        # Run and check for error stop
        _, _, returncode = self.run_test_executable(executable)

        # error stop should cause non-zero return code
        # gfortran can return 1, 2, or other non-zero codes depending on version/platform
        if returncode != 0:
            return TestResult(
                test_subroutine,
                True,
                f"Correctly triggered error stop (exit code {returncode})",
            )
        else:
            return TestResult(
                test_subroutine,
                False,
                "Expected error stop but test completed normally",
            )


    def run_tests(self, test_files: list[Path]) -> None:
        """
        Run all test files.

        Parameters
        ----------
        test_files : list[Path]
            List of test file paths to execute
        """
        if not test_files:
            print(f"{Colors.YELLOW.value}No test files found{Colors.RESET.value}")
            return

        print(f"{Colors.BOLD.value}Running Fortran tests...{Colors.RESET.value}\n")

        # Create temporary directory for executables
        separator: str = "-" * 60
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir: Path = Path(tmpdir)

            for test_file in test_files:
                print(separator)
                print(f"{Colors.BLUE.value}Testing: {test_file}{Colors.RESET.value}")

                # Check if this is an error_stop test
                if "error_stop" in test_file.name.lower():
                    results: list[TestResult] = self._handle_error_stop_test(
                        test_file,
                        output_dir,
                    )
                else:
                    # Normal test
                    results = self._handle_normal_test(test_file, output_dir)

                # Update statistics
                for result in results:
                    self.total_tests += 1
                    if result.passed:
                        self.passed_tests += 1
                    else:
                        self.failed_tests += 1

                # Blank line between test files
                print()


    def print_summary(self) -> int:
        """
        Print final test summary.

        Returns
        -------
        int
            Exit code (0 if all tests passed, 1 otherwise)
        """
        separator: str = "-" * 60
        separator_table: str = "=" * 50

        print(separator)
        print("All tests completed.")
        print(separator_table)
        print(f"Total tests: {self.total_tests}")
        print(f"{Colors.GREEN.value}{MessageTag.PASS.value}{self.passed_tests:>4}{Colors.RESET.value}")
        print(f"{Colors.RED.value}{MessageTag.FAIL.value}{self.failed_tests:>4}{Colors.RESET.value}")
        print(separator_table)

        if self.failed_tests == 0 and self.total_tests > 0:
            print(f"\n{Colors.GREEN.value}{Colors.BOLD.value}All tests passed! ✓{Colors.RESET.value}")
            return ExitStatus.SUCCESS.value
        else:
            print(f"\n{Colors.RED.value}{Colors.BOLD.value}Some tests failed ✗{Colors.RESET.value}")
            return ExitStatus.ERROR.value
