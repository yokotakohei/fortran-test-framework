#!/usr/bin/env python3
"""
Module providing implements the core functionality of fortest.
"""

from typing import ClassVar
import glob
import re
import subprocess
import tempfile
from pathlib import Path

from fortest.utilities import deduplicate
from fortest.test_result import Colors, MessageTag, TestResult
from fortest.exit_status import ExitStatus
from fortest.build_system_detector import BuildSystemInfo, BuildSystemDetector
from fortest.module_dependency_resolver import ModuleDependencyResolver
from fortest.test_code_generator import TestCodeGenerator
from fortest.test_result_formatter import TestResultFormatter
from fortest.project_builder import ProjectBuilder


class FortranTestRunner:
    """
    Test runner for Fortran test files.

    The runner first attempts to detect and use a build system (FPM, CMake, or Make).
    When a build system is detected, it handles dependency resolution and compilation.
    If no build system is found, the runner falls back to direct compilation with gfortran.

    Attributes
    ----------
    compiler : str
        Fortran compiler command (used for fallback compilation)
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
        
        # Initialize helper classes
        self.detector: BuildSystemDetector = BuildSystemDetector(verbose)
        self.resolver: ModuleDependencyResolver = ModuleDependencyResolver(verbose)
        self.generator: TestCodeGenerator = TestCodeGenerator(verbose)
        self.formatter: TestResultFormatter = TestResultFormatter(verbose)
        self.builder: ProjectBuilder = ProjectBuilder(compiler, verbose, self.detector, self.resolver, self.generator)


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
            return deduplicate(found)

        # Otherwise search for pattern and normalize/resolve results
        found = []
        for file in glob.glob(pattern, recursive=True):
            if file.endswith(".f90"):
                found.append(Path(file).resolve())
        for file in glob.glob(f"**/{pattern}", recursive=True):
            if file.endswith(".f90"):
                found.append(Path(file).resolve())

        # Deduplicate while preserving order
        return deduplicate(found)


    def _find_build_directories(self, test_file: Path) -> list[Path]:
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
        return self.resolver.find_module_files(test_file, include_assertions)


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
        return self.resolver.extract_module_name(file_path)


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
        return self.resolver.find_fortran_files_recursive(directory, max_depth)


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
        return self.resolver.find_module_file_by_name(module_name, search_dirs)


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
        return self.generator.extract_test_subroutines(test_file)


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
        return self.generator.separate_error_stop_tests(test_subroutines)


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
        return self.generator.generate_test_program(test_file, test_module_name, test_subroutines, output_dir)


    def generate_error_stop_test_program(self,
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
        return self.generator.generate_error_stop_test_program(test_module_name, test_subroutine, output_dir)


    def detect_build_system(self, test_file: Path) -> BuildSystemInfo | None:
        """
        Detect if the project has a build system configuration.

        Priority order: FPM > CMake > Make
        (FPM is Fortran-specific and preferred when available)

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        BuildSystemInfo | None
            Build system information if detected, None otherwise
        """
        return self.detector.detect(test_file)


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
        return self.builder.build_with_system(build_info, test_file)


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
            "-J", str(output_dir),
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
        compile_cmd = [
            self.compiler,
            "-J", str(output_dir),
            "-o", str(executable),
        ]

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
        return self.builder.compile_test(test_file, output_dir)


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
        return self.formatter.parse_test_output(output)


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
        self.formatter.print_normal_test_summary(normal_results)


    def _compile_module_dependencies(self,
        module_files: list[Path],
        test_file: Path,
        output_dir: Path,
    ) -> tuple[list[Path], str | None]:
        """
        Compile module dependencies.

        Parameters
        ----------
        module_files : list[Path]
            List of module files to compile
        test_file : Path
            Path to the test file (for finding build directories)
        output_dir : Path
            Directory for output objects

        Returns
        -------
        tuple[list[Path], str | None]
            Tuple of (compiled_objects, error_message)
            Returns ([], None) on success, ([], error_msg) on failure
        """
        return self.builder.compile_module_dependencies(module_files, test_file, output_dir)


    def _compile_single_module(self,
        module_file: Path,
        build_dirs: list[Path],
        output_dir: Path,
    ) -> Path | None:
        """
        Compile a single module file.

        Parameters
        ----------
        module_file : Path
            Path to the module file
        build_dirs : list[Path]
            Build directories for module search path
        output_dir : Path
            Directory for output object

        Returns
        -------
        Path | None
            Path to compiled object file, or None on failure
        """
        compile_mod_cmd = [self.compiler, "-c", str(module_file)]

        for build_dir in build_dirs:
            compile_mod_cmd.extend(["-I", str(build_dir)])

        output_obj = output_dir / f"{module_file.stem}.o"
        compile_mod_cmd.extend([
            "-J", str(output_dir),
            "-o", str(output_obj),
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
            return output_obj

        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED.value}Compilation error:{Colors.RESET.value}")
            print(f"  Module: {module_file.name}")
            if e.stderr:
                print(f"  Error details:")
                print(e.stderr)
            return None


    def _compile_test_executable(self,
        test_file: Path,
        program_file: Path,
        executable_path: Path,
        compiled_objects: list[Path],
        output_dir: Path,
    ) -> str | None:
        """
        Compile test executable.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        program_file : Path
            Path to the generated program file
        executable_path : Path
            Path for the output executable
        compiled_objects : list[Path]
            List of compiled object files
        output_dir : Path
            Directory for module files

        Returns
        -------
        str | None
            Error message if compilation failed, None on success
        """
        return self.builder.compile_test_executable(test_file, program_file, executable_path, compiled_objects, output_dir)


    def _run_single_normal_test(self,
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
        module_files = self.find_module_files(test_file)
        normal_program = self.generate_single_test_program(
            test_module_name,
            test_subroutine,
            output_dir,
        )

        if self.verbose:
            print(f"Generated test program for {test_subroutine}: {normal_program}")
            print(f"Module dependencies: {[m.name for m in module_files]}")

        # Compile module dependencies
        compiled_objects, error = self._compile_module_dependencies(
            module_files,
            test_file,
            output_dir,
        )

        if error:
            return TestResult(test_subroutine, False, error)

        # Compile test executable
        executable = output_dir / f"{test_subroutine}_normal"
        error = self._compile_test_executable(
            test_file,
            normal_program,
            executable,
            compiled_objects,
            output_dir,
        )

        if error:
            return TestResult(test_subroutine, False, error)

        # Run the test and parse results
        return self._execute_and_parse_normal_test(test_subroutine, executable)


    def _execute_and_parse_normal_test(self,
        test_subroutine: str,
        executable: Path,
    ) -> TestResult:
        """
        Execute a normal test and parse its output.

        Parameters
        ----------
        test_subroutine : str
            Name of the test subroutine
        executable : Path
            Path to the test executable

        Returns
        -------
        TestResult
            Test result
        """
        success, output, returncode = self.run_test_executable(executable)

        if not success:
            return TestResult(
                test_subroutine,
                False,
                f"Test execution failed: {output}",
            )

        results = self.parse_test_output(output)

        if output.strip():
            print(output.rstrip())

        if not results:
            return self._handle_no_test_results(test_subroutine, returncode)

        return results[0] if results else TestResult(test_subroutine, True)


    def _handle_no_test_results(self,
        test_subroutine: str,
        returncode: int,
    ) -> TestResult:
        """
        Handle case where no test results were parsed from output.

        Parameters
        ----------
        test_subroutine : str
            Name of the test subroutine
        returncode : int
            Exit code from test execution

        Returns
        -------
        TestResult
            Test result
        """
        if returncode != 0:
            print(f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} {test_subroutine}")
            print(f"       Test caused error stop or abnormal termination (exit code {returncode})")
            return TestResult(
                test_subroutine,
                False,
                f"Error stop or abnormal termination (exit code {returncode})",
            )

        return TestResult(test_subroutine, True)


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
        return self.generator.generate_single_test_program(test_module_name, test_subroutine, output_dir)


    def _print_error_stop_summary(self, error_stop_results: list[TestResult]) -> None:
        """
        Print summary for error_stop tests.

        Parameters
        ----------
        error_stop_results : list[TestResult]
            List of error_stop test results
        """
        self.formatter.print_error_stop_summary(error_stop_results)


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
        # Check if build system is available
        build_system: BuildSystemInfo | None = self.detect_build_system(test_file)

        if self.verbose:
            if build_system:
                print(f"Detected build system: {build_system.build_type} at {build_system.project_dir}")
            else:
                print("No build system detected")

        # Use build system if available
        if build_system:
            if build_system.build_type == "fpm":
                # FPM supports dynamic test generation
                return self._handle_normal_test_with_fpm(test_file, build_system, output_dir)
            elif build_system.build_type in ("cmake", "make"):
                # CMake and Make use pre-defined tests
                return self._handle_normal_test_with_build_system(test_file, build_system, output_dir)

        # Fallback to direct compilation if no build system is detected
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


    def _handle_normal_test_with_fpm(self,
        test_file: Path,
        build_system: BuildSystemInfo,
        output_dir: Path,
    ) -> list[TestResult]:
        """
        Handle normal test execution using FPM build system.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        build_system : BuildSystemInfo
            Build system information
        output_dir : Path
            Directory for output executable (not used with FPM)

        Returns
        -------
        list[TestResult]
            List of test results
        """
        if self.verbose:
            print(f"Using FPM build system at {build_system.project_dir}")

        # Extract test information
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

        if self.verbose:
            print(f"Found test subroutines: {all_test_subroutines}")

        # Run fpm build to compile all sources and tests
        build_cmd: list[str] = ["fpm", "build"]

        if self.verbose:
            print(f"Building with FPM: {' '.join(build_cmd)}")

        try:
            result = subprocess.run(
                build_cmd,
                cwd=build_system.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            if self.verbose and result.stdout:
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED.value}FPM build failed:{Colors.RESET.value}")
            if e.stderr:
                print(e.stderr)
            if e.stdout:
                print(e.stdout)
            # Return failure for all tests
            return [
                TestResult(test_name, False, f"FPM build failed: {e.stderr}")
                for test_name in all_test_subroutines
            ]

        # Separate normal tests from error_stop tests
        normal_tests, error_stop_tests = self.separate_error_stop_tests(all_test_subroutines)

        all_results: list[TestResult] = []

        # For FPM, we use direct compilation after building dependencies
        # This approach is simpler and more consistent with CMake behavior
        
        # Find FPM build directory for module files
        fpm_build_dirs = self._find_fpm_build_directories(build_system.project_dir)
        
        # Run normal tests using direct compilation
        if normal_tests:
            normal_results: list[TestResult] = self._compile_and_run_normal_tests_with_fpm(
                test_file,
                test_module_name,
                normal_tests,
                output_dir,
                fpm_build_dirs,
            )
            all_results.extend(normal_results)

        # Run error_stop tests individually using direct compilation
        error_stop_results: list[TestResult] = []
        for error_stop_test in error_stop_tests:
            result: TestResult = self._run_single_error_stop_test_with_fpm(
                test_file,
                test_module_name,
                error_stop_test,
                output_dir,
                fpm_build_dirs,
            )
            error_stop_results.append(result)
            all_results.append(result)

        # Print error_stop tests summary if any
        if error_stop_results:
            self._print_error_stop_summary(error_stop_results)

        return all_results


    def _find_fpm_build_directories(self, project_dir: Path) -> list[Path]:
        """
        Find FPM build directories containing module files.

        Parameters
        ----------
        project_dir : Path
            FPM project directory

        Returns
        -------
        list[Path]
            List of build directories
        """
        build_dirs: list[Path] = []
        build_dir: Path = project_dir / "build"
        
        if not build_dir.exists():
            return build_dirs
        
        # Add all FPM build directories
        for gfortran_dir in build_dir.glob("gfortran_*"):
            if gfortran_dir.is_dir():
                build_dirs.append(gfortran_dir)
                # Also add subdirectories that contain .mod files
                for subdir in gfortran_dir.rglob("*"):
                    if subdir.is_dir() and any(subdir.glob("*.mod")):
                        build_dirs.append(subdir)
        
        # Also check dependencies
        deps_dir = build_dir / "dependencies"
        if deps_dir.exists():
            for dep_build in deps_dir.rglob("build/gfortran_*"):
                if dep_build.is_dir():
                    build_dirs.append(dep_build)
                    for subdir in dep_build.rglob("*"):
                        if subdir.is_dir() and any(subdir.glob("*.mod")):
                            build_dirs.append(subdir)
        
        return build_dirs


    def _compile_and_run_normal_tests_with_fpm(self,
        test_file: Path,
        test_module_name: str,
        normal_tests: list[str],
        output_dir: Path,
        fpm_build_dirs: list[Path],
    ) -> list[TestResult]:
        """
        Compile and run normal tests using direct compilation with FPM build artifacts.

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
        fpm_build_dirs : list[Path]
            FPM build directories containing module files

        Returns
        -------
        list[TestResult]
            List of test results
        """
        all_results: list[TestResult] = []

        # Run each normal test individually
        for test_subroutine in normal_tests:
            result: TestResult = self._run_single_normal_test_with_fpm(
                test_file,
                test_module_name,
                test_subroutine,
                output_dir,
                fpm_build_dirs,
            )
            all_results.append(result)

        # Print summary for normal tests if any were run
        if all_results:
            self._print_normal_test_summary(all_results)

        return all_results


    def _run_single_normal_test_with_fpm(self,
        test_file: Path,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
        fpm_build_dirs: list[Path],
    ) -> TestResult:
        """
        Run a single normal test using direct compilation with FPM build artifacts.

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
        fpm_build_dirs : list[Path]
            FPM build directories containing module files

        Returns
        -------
        TestResult
            Test result
        """
        # Generate test driver program (no print_summary to avoid duplicate summaries)
        fortest_assertions: str = FortranTestRunner.ASSERTION_MODULE
        driver_content = f"program run_{test_subroutine}\n"
        driver_content += f"    use {fortest_assertions}\n"
        driver_content += f"    use {test_module_name}\n"
        driver_content += "    implicit none\n"
        driver_content += f"    call {test_subroutine}()\n"
        driver_content += f"end program run_{test_subroutine}\n"
        
        driver_file = output_dir / f"test_driver_{test_subroutine}.f90"

        with open(driver_file, "w") as f:
            f.write(driver_content)

        # Compile test with FPM build directories in include path
        output_exe = output_dir / f"test_{test_subroutine}"
        success, compile_output = self._compile_test_with_fpm_modules(
            driver_file,
            test_file,
            output_exe,
            fpm_build_dirs,
        )

        if not success:
            error_msg = f"Compilation failed:\n{compile_output}"
            print(f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} {test_subroutine}")
            print(f"       {error_msg}")
            return TestResult(test_subroutine, False, error_msg)

        # Run the test
        success, output, exit_code = self.run_test_executable(output_exe)

        # Parse the output to check for assertion failures
        # Even if exit_code == 0, the test may have failed assertions
        has_fail = MessageTag.FAIL.value in output if output else False

        # For normal tests, check both exit code and assertion results
        # Print result immediately
        if success and exit_code == 0 and not has_fail:
            # Test passed
            if output.strip():
                print(output.rstrip())
            return TestResult(test_subroutine, True, "")
        else:
            # Test failed (either error stop or assertion failure)
            if output.strip():
                print(output.rstrip())
            
            if not success or exit_code != 0:
                # Error stop or abnormal termination
                print(f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} {test_subroutine}")
                print(f"       Test caused error stop or abnormal termination (exit code {exit_code})")
                return TestResult(test_subroutine, False, f"Error stop (exit code {exit_code})")
            else:
                # Assertion failure - output already printed above
                return TestResult(test_subroutine, False, "Assertion failed")


    def _run_single_error_stop_test_with_fpm(self,
        test_file: Path,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
        fpm_build_dirs: list[Path],
    ) -> TestResult:
        """
        Run a single error_stop test using direct compilation with FPM build artifacts.

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
        fpm_build_dirs : list[Path]
            FPM build directories containing module files

        Returns
        -------
        TestResult
            Test result
        """
        # Generate test driver program (no print_summary for error_stop tests)
        driver_content = f"program run_{test_subroutine}\n"
        driver_content += f"    use {test_module_name}\n"
        driver_content += "    implicit none\n"
        driver_content += f"    call {test_subroutine}()\n"
        driver_content += f"end program run_{test_subroutine}\n"
        
        driver_file = output_dir / f"test_driver_{test_subroutine}.f90"

        with open(driver_file, "w") as f:
            f.write(driver_content)

        # Compile test with FPM build directories in include path
        output_exe = output_dir / f"test_{test_subroutine}"
        success, compile_output = self._compile_test_with_fpm_modules(
            driver_file,
            test_file,
            output_exe,
            fpm_build_dirs,
        )

        if not success:
            error_msg = f"Compilation failed:\n{compile_output}"
            print(f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} {test_subroutine}")
            print(f"       {error_msg}")
            return TestResult(test_subroutine, False, error_msg)

        # Run the test - for error_stop tests, we expect non-zero exit code
        passed, output, exit_code = self.run_test_executable(output_exe)

        # For error_stop tests, success means the test triggered error stop (exit_code != 0)
        if exit_code != 0:
            # Test correctly triggered error stop - don't print here, will be printed by summary
            return TestResult(test_subroutine, True, "Correctly triggered error stop")
        else:
            # Test did not trigger error stop when it should have - don't print here, will be printed by summary
            return TestResult(test_subroutine, False, "Expected error stop but test completed normally")


    def _compile_test_with_fpm_modules(self,
        driver_file: Path,
        test_file: Path,
        output_exe: Path,
        fpm_build_dirs: list[Path],
    ) -> tuple[bool, str]:
        """
        Compile test using gfortran with FPM build directories.

        Parameters
        ----------
        driver_file : Path
            Path to the test driver file
        test_file : Path
            Path to the test file
        output_exe : Path
            Path to the output executable
        fpm_build_dirs : list[Path]
            FPM build directories containing module files

        Returns
        -------
        tuple[bool, str]
            (success, output)
        """
        # Find module dependencies
        module_files = self.find_module_files(test_file, include_assertions=True)

        # Build compile command with FPM build directories
        compile_cmd = [self.compiler, "-o", str(output_exe)]
        
        # Add include paths for FPM build directories
        for build_dir in fpm_build_dirs:
            compile_cmd.extend(["-I", str(build_dir)])
        
        # Add -J flag to output .mod files to the executable's directory
        output_dir = output_exe.parent
        compile_cmd.extend(["-J", str(output_dir)])
        
        # Add module files
        for mod_file in module_files:
            compile_cmd.append(str(mod_file))
        
        # Add test file and driver
        compile_cmd.append(str(test_file))
        compile_cmd.append(str(driver_file))

        if self.verbose:
            print(f"Compiling: {' '.join(compile_cmd)}")

        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
        )

        return (result.returncode == 0, result.stdout + result.stderr)


    def _handle_normal_test_with_fpm_old(self,
        test_file: Path,
        build_system: BuildSystemInfo,
        output_dir: Path,
    ) -> list[TestResult]:
        """
        OLD: Handle normal test execution using FPM build system.
        This approach tried to use fpm test/run but had issues with auto-executables=false.
        Kept for reference but not used.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        build_system : BuildSystemInfo
            Build system information
        output_dir : Path
            Directory for output executable (not used with FPM)

        Returns
        -------
        list[TestResult]
            List of test results
        """
        if self.verbose:
            print(f"Using FPM build system at {build_system.project_dir}")

        # Extract test information
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

        if self.verbose:
            print(f"Found test subroutines: {all_test_subroutines}")

        # Run fpm build to compile all sources and tests
        build_cmd: list[str] = ["fpm", "build"]

        if self.verbose:
            print(f"Building with FPM: {' '.join(build_cmd)}")

        try:
            result = subprocess.run(
                build_cmd,
                cwd=build_system.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            if self.verbose and result.stdout:
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED.value}FPM build failed:{Colors.RESET.value}")
            if e.stderr:
                print(e.stderr)
            if e.stdout:
                print(e.stdout)
            # Return failure for all tests
            return [
                TestResult(test_name, False, f"FPM build failed: {e.stderr}")
                for test_name in all_test_subroutines
            ]

        # Separate normal tests from error_stop tests
        normal_tests, error_stop_tests = self.separate_error_stop_tests(all_test_subroutines)

        all_results: list[TestResult] = []

        # Run normal tests
        if normal_tests:
            for test_subroutine in normal_tests:
                result = self._run_single_test_with_fpm(
                    test_file,
                    test_module_name,
                    test_subroutine,
                    build_system,
                )
                all_results.append(result)

            # Print summary for normal tests
            if all_results:
                self._print_normal_test_summary(all_results)

        # Run error_stop tests individually
        error_stop_results: list[TestResult] = []
        for error_stop_test in error_stop_tests:
            result = self._run_single_test_with_fpm(
                test_file,
                test_module_name,
                error_stop_test,
                build_system,
                is_error_stop=True,
            )
            error_stop_results.append(result)
            all_results.append(result)

        # Print error_stop tests summary if any
        if error_stop_results:
            self._print_error_stop_summary(error_stop_results)

        return all_results


    def _generate_temp_test_filename(self, test_subroutine: str, test_dir: Path) -> tuple[Path, str]:
        """
        Generate a unique temporary test filename and program name.

        Uses MD5 hash to create short names that comply with Fortran's
        63-character identifier limit.

        Parameters
        ----------
        test_subroutine : str
            Name of the test subroutine
        test_dir : Path
            Directory where the temporary file will be created

        Returns
        -------
        tuple[Path, str]
            Tuple of (temp_file_path, program_name)
        """
        import hashlib

        # Create a short unique hash from the test name
        test_hash = hashlib.md5(test_subroutine.encode()).hexdigest()[:8]
        temp_filename = f"fortest_{test_hash}.f90"
        temp_test_file = test_dir / temp_filename

        # Ensure unique filename (in case of hash collision)
        counter = 0
        while temp_test_file.exists():
            counter += 1
            temp_filename = f"fortest_{test_hash}_{counter}.f90"
            temp_test_file = test_dir / temp_filename

        # Program name must be short due to Fortran's 63-character limit
        temp_program_name = f"fortest_{test_hash}"
        if counter > 0:
            temp_program_name = f"fortest_{test_hash}_{counter}"

        return temp_test_file, temp_program_name


    def _filter_fpm_output(self, output: str) -> str:
        """
        Filter FPM build/progress messages from test output.

        Removes FPM-specific messages while preserving test results
        and assertion details.

        Parameters
        ----------
        output : str
            Raw output from FPM test execution

        Returns
        -------
        str
            Filtered output containing only test results
        """
        return self.formatter.filter_fpm_output(output)


    def _run_single_test_with_fpm(self,
        test_file: Path,
        test_module_name: str,
        test_subroutine: str,
        build_system: BuildSystemInfo,
        is_error_stop: bool = False,
    ) -> TestResult:
        """
        Run a single test using FPM by creating a temporary test program.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        test_module_name : str
            Name of the test module
        test_subroutine : str
            Name of the test subroutine
        build_system : BuildSystemInfo
            Build system information
        is_error_stop : bool
            Whether this is an error_stop test

        Returns
        -------
        TestResult
            Test result
        """
        # Create a temporary test program in the project's app directory
        # We use app/ instead of test/ because auto-tests may be disabled in fpm.toml
        import os
        temp_test_dir = build_system.project_dir / "app"
        temp_test_dir.mkdir(exist_ok=True)

        # Generate unique temporary filename and program name
        temp_test_file, temp_program_name = self._generate_temp_test_filename(
            test_subroutine, temp_test_dir
        )

        # Generate test program content
        fortest_assertions: str = FortranTestRunner.ASSERTION_MODULE
        program_content: str = f"program {temp_program_name}\n"
        program_content += f"    use {fortest_assertions}\n"
        program_content += f"    use {test_module_name}\n"
        program_content += "    implicit none\n"
        program_content += f"    call {test_subroutine}()\n"
        program_content += f"end program {temp_program_name}\n"

        try:
            with open(temp_test_file, "w") as f:
                f.write(program_content)

            if self.verbose:
                print(f"Created temporary test program: {temp_test_file}")

            # Build the test with FPM
            build_cmd: list[str] = ["fpm", "build", temp_program_name, "--flag", "-g"]

            if self.verbose:
                print(f"Building test with FPM: {' '.join(build_cmd)}")

            build_result = subprocess.run(
                build_cmd,
                cwd=build_system.project_dir,
                capture_output=True,
                text=True,
            )

            if build_result.returncode != 0:
                build_output = build_result.stdout if build_result.stdout else build_result.stderr
                if self.verbose:
                    print(f"FPM build failed:\n{build_output}")
                return TestResult(
                    test_subroutine,
                    False,
                    f"FPM build failed: {build_output}",
                )

            # Find the compiled test executable in app/ directory
            build_dir = build_system.project_dir / "build"
            test_executable = None
            
            # FPM puts app executables in build/gfortran_*/app/
            for app_dir in build_dir.glob("gfortran_*/app"):
                candidate = app_dir / temp_program_name
                if candidate.exists():
                    test_executable = candidate
                    break

            if not test_executable or not test_executable.exists():
                error_msg = f"Could not find test executable for {temp_program_name}"
                if self.verbose:
                    print(f"{Colors.YELLOW.value}{error_msg}{Colors.RESET.value}")
                return TestResult(
                    test_subroutine,
                    False,
                    error_msg,
                )

            # Run the test executable directly
            if self.verbose:
                print(f"Running test executable: {test_executable}")

            result = subprocess.run(
                [str(test_executable)],
                cwd=build_system.project_dir,
                capture_output=True,
                text=True,
            )

            # Parse output
            output = result.stdout if result.stdout else result.stderr

            # Filter out FPM build messages in non-verbose mode
            if not self.verbose:
                output = self._filter_fpm_output(output)

            if self.verbose:
                print(f"Test output:\n{output}")

            # For error_stop tests, check return code
            if is_error_stop:
                if result.returncode != 0:
                    # Don't print here - will be printed by _print_error_stop_summary
                    return TestResult(
                        f"{test_subroutine} (error_stop expected)",
                        True,
                        "Correctly triggered error stop",
                    )
                else:
                    # Don't print here - will be printed by _print_error_stop_summary
                    return TestResult(
                        f"{test_subroutine} (error_stop expected)",
                        False,
                        "Expected error stop but test completed normally",
                    )

            # For normal tests, check compilation and execution
            if result.returncode != 0:
                # Check if it's a compilation error
                if "Error" in output or "error" in output:
                    print(f"{Colors.RED.value}Compilation/execution error for {test_subroutine}:{Colors.RESET.value}")
                    print(output)
                    return TestResult(
                        test_subroutine,
                        False,
                        f"Compilation/execution failed: {output}",
                    )
                else:
                    print(f"{Colors.RED.value}{MessageTag.FAIL.value}{Colors.RESET.value} {test_subroutine}")
                    print(f"       Test caused error stop or abnormal termination (exit code {result.returncode})")
                    if output.strip():
                        print(output)
                    return TestResult(
                        test_subroutine,
                        False,
                        f"Error stop or abnormal termination (exit code {result.returncode})",
                    )

            # Print the raw output from the test
            if output.strip():
                print(output.rstrip())

            # Parse output to get test results
            results: list[TestResult] = self.parse_test_output(output)

            # If no results found, check return code
            if not results:
                if result.returncode == 0:
                    return TestResult(test_subroutine, True)
                else:
                    return TestResult(
                        test_subroutine,
                        False,
                        f"Test failed with exit code {result.returncode}",
                    )

            return results[0] if results else TestResult(test_subroutine, True)

        finally:
            # Clean up temporary test file
            if temp_test_file.exists():
                temp_test_file.unlink()


    def _handle_normal_test_with_build_system(self,
        test_file: Path,
        build_system: BuildSystemInfo,
        output_dir: Path,
    ) -> list[TestResult]:
        """
        Handle normal test execution using CMake or Make build system.

        Unlike FPM, CMake and Make typically build all tests at once.
        This method builds the project and attempts to run the test executable.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        build_system : BuildSystemInfo
            Build system information
        output_dir : Path
            Directory for output executable (not used with build systems)

        Returns
        -------
        list[TestResult]
            List of test results
        """
        if self.verbose:
            print(f"Using {build_system.build_type.upper()} build system at {build_system.project_dir}")

        # Extract test information
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

        if self.verbose:
            print(f"Found test subroutines: {all_test_subroutines}")

        # Build the project
        try:
            executable = self.build_with_system(build_system, test_file)
        except subprocess.CalledProcessError as e:
            if self.verbose:
                print(f"{Colors.YELLOW.value}{build_system.build_type.upper()} build failed, falling back to direct compilation{Colors.RESET.value}")
                if e.stderr:
                    print(e.stderr)
            # Fall back to direct compilation
            executable = None

        if not executable or not executable.exists():
            if self.verbose:
                print(f"{Colors.YELLOW.value}Test executable not found, falling back to direct compilation{Colors.RESET.value}")
            # Fall back to direct compilation - call the normal compilation path
            return self._compile_and_run_tests_fallback(test_file, test_module_name, all_test_subroutines, output_dir)

        # Run the test executable
        if self.verbose:
            print(f"Running test executable: {executable}")

        try:
            result = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                cwd=build_system.project_dir,
            )

            output = result.stdout if result.stdout else result.stderr

            if self.verbose:
                print(f"Test output:\n{output}")

            # Check for errors
            if result.returncode != 0:
                print(f"{Colors.RED.value}Test execution failed (exit code {result.returncode}){Colors.RESET.value}")
                if output.strip():
                    print(output)
                return [
                    TestResult(test_name, False, f"Test execution failed: {output}")
                    for test_name in all_test_subroutines
                ]

            # Print the raw output from the test
            if output.strip():
                print(output.rstrip())

            # Parse output to get test results
            results: list[TestResult] = self.parse_test_output(output)

            # Print summary for normal tests
            if results:
                self._print_normal_test_summary(results)
                return results

            # If no results parsed, assume all passed if exit code is 0
            return [TestResult(test_name, True) for test_name in all_test_subroutines]

        except Exception as e:
            error_msg = f"Error running test: {e}"
            print(f"{Colors.RED.value}{error_msg}{Colors.RESET.value}")
            return [
                TestResult(test_name, False, error_msg)
                for test_name in all_test_subroutines
            ]


    def _compile_and_run_tests_fallback(
        self,
        test_file: Path,
        test_module_name: str,
        test_subroutines: list[str],
        output_dir: Path,
    ) -> list[TestResult]:
        """
        Fallback method to compile and run tests using direct compilation.
        Used when build system doesn't produce test executables.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        test_module_name : str
            Name of the test module
        test_subroutines : list[str]
            List of test subroutine names
        output_dir : Path
            Directory for output executable

        Returns
        -------
        list[TestResult]
            List of test results
        """
        # Separate normal tests from error_stop tests
        normal_tests, error_stop_tests = self.separate_error_stop_tests(test_subroutines)

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
        module_files = self.find_module_files(test_file)
        error_program = self.generate_error_stop_test_program(
            test_module_name,
            test_subroutine,
            output_dir,
        )

        # Compile module dependencies
        compiled_objects, error = self._compile_module_dependencies(
            module_files,
            test_file,
            output_dir,
        )

        if error:
            return TestResult(test_subroutine, False, error)

        # Compile test executable
        executable = output_dir / test_subroutine
        error = self._compile_test_executable(
            test_file,
            error_program,
            executable,
            compiled_objects,
            output_dir,
        )

        if error:
            return TestResult(test_subroutine, False, error)

        # Run and check for error stop
        return self._execute_and_check_error_stop(test_subroutine, executable)


    def _execute_and_check_error_stop(self,
        test_subroutine: str,
        executable: Path,
    ) -> TestResult:
        """
        Execute error_stop test and check if it triggered error stop correctly.

        Parameters
        ----------
        test_subroutine : str
            Name of the test subroutine
        executable : Path
            Path to the test executable

        Returns
        -------
        TestResult
            Test result
        """
        _, _, returncode = self.run_test_executable(executable)

        # error stop should cause non-zero return code
        # gfortran can return 1, 2, or other non-zero codes depending on version/platform
        if returncode != 0:
            return TestResult(
                test_subroutine,
                True,
                f"Correctly triggered error stop (exit code {returncode})",
            )

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
                    if self.verbose:
                        print(f"Calling _handle_normal_test for {test_file}")
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
        return self.formatter.print_final_summary(
            self.total_tests,
            self.passed_tests,
            self.failed_tests
        )
