#!/usr/bin/env python3
"""
fortest - Automated test runner for Fortran

Usage:
    fortest                          # Run all test_*.f90 files
    fortest path/to/test_file.f90    # Run specific test file
    fortest module_*.f90             # Run all module test files
    fortest -v                       # Verbose mode
"""

import argparse
import glob
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from importlib import resources
from pathlib import Path


@dataclass
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


class Colors(Enum):
    """
    ANSI color codes for terminal output.
    """
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class MessageTag(Enum):
    """
    Test result message tags.
    """
    PASS = "[PASS]"
    FAIL = "[FAIL]"


class TestResult:
    """
    Container for test execution results.

    Attributes
    ----------
    name : str
        Name of the test
    passed : bool
        Whether the test passed
    message : str
        Additional message about the test result
    """
    def __init__(
        self,
        name: str,
        passed: bool,
        message: str = "",
    ) -> None:
        self.name: str = name
        self.passed: bool = passed
        self.message: str = message


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
    def __init__(
        self,
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


    def find_module_files(self,
        test_file: Path,
        output_dir: Path | None = None,
    ) -> list[Path]:
        """
        Find module dependencies for a test file.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        output_dir : Path | None
            Temporary directory where module files can be extracted

        Returns
        -------
        list[Path]
            List of module file paths that the test depends on
        """
        modules: list[Path] = []

        # Convert test_file to absolute path to determine project root
        test_file_abs: Path = test_file.resolve()

        # Try to find project root (contains fortest/ directory)
        project_root: Path | None = None
        current: Path = test_file_abs.parent
        while current != current.parent:  # Stop at filesystem root
            if (current / "fortest").exists():
                project_root = current
                break
            current = current.parent

        # Check for bundled assertions module (from package)
        try:
            fortest_pkg = resources.files("fortest")
            assertions_resource = fortest_pkg / "module_fortest_assertions.f90"

            # Read the content and write to output directory
            if hasattr(assertions_resource, "read_text") and output_dir is not None:
                content = assertions_resource.read_text(encoding="utf-8")
                temp_module_path = output_dir / "module_fortest_assertions.f90"
                temp_module_path.write_text(content, encoding="utf-8")
                modules.append(temp_module_path)
        except (ImportError, AttributeError, TypeError, Exception):
            # Fallback: look in project root if not installed as package
            if project_root is None:
                project_root = Path.cwd()

            fortest_module: Path = project_root / "fortest" / "module_fortest_assertions.f90"
            if fortest_module.exists():
                modules.append(fortest_module)

        # Check for other module dependencies in examples/ (recursively)
        if project_root is None:
            project_root = Path.cwd()
        examples_dir: Path = project_root / "examples"
        if examples_dir.exists():
            for mod_file in examples_dir.rglob("module_*.f90"):
                if mod_file.resolve() != test_file_abs:
                    modules.append(mod_file)

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


    def separate_error_stop_tests(
        self,
        test_subroutines: list[str],
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
        program_content: str = f"program run_{test_file.stem}\n"
        program_content += "    use fortest_assertions\n"
        program_content += f"    use {test_module_name}\n"
        program_content += "    implicit none\n\n"

        # Call all test subroutines
        for test_sub in test_subroutines:
            program_content += f"    call {test_sub}()\n"

        program_content += "\n    call print_summary()\n"
        program_content += f"end program run_{test_file.stem}\n"

        generated_file: Path = output_dir / f"gen_runner_{test_file.name}"
        with open(generated_file, "w") as f:
            f.write(program_content)

        if self.verbose:
            print(f"Generated program:\n{program_content}")

        return generated_file


    def generate_error_stop_test_program(
        self,
        test_file: Path,
        test_module_name: str,
        test_subroutine: str,
        output_dir: Path,
    ) -> Path:
        """
        Generate a standalone program for an error_stop test.

        Parameters
        ----------
        test_file : Path
            Path to the test file
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
        program_content += "    implicit none\n\n"
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
                # Build with CMake
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
                
                # Find the test executable
                # Try common naming patterns
                test_stem: str = test_file.stem
                possible_names: list[str] = [
                    test_stem,
                    f"test_{test_stem.replace('test_', '')}",
                    "test_sample_module",  # fallback for examples
                ]
                
                for name in possible_names:
                    executable: Path = build_dir / name
                    if executable.exists():
                        return executable
                
                if self.verbose:
                    print(f"Warning: Could not find test executable in {build_dir}")
                return None
                
            elif build_type == "fpm":
                # Build with FPM
                subprocess.run(
                    ["fpm", "build"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                
                # FPM puts test executables in build/gfortran_*/test/
                build_dir = project_dir / "build"
                for test_dir in build_dir.glob("gfortran_*/test"):
                    test_stem = test_file.stem
                    executable = test_dir / test_stem
                    if executable.exists():
                        return executable
                
                if self.verbose:
                    print(f"Warning: Could not find test executable in {build_dir}")
                return None
                
            elif build_type == "make":
                # Build with Make
                subprocess.run(
                    ["make"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                
                # Look for test executable in common locations
                test_stem = test_file.stem
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
        
        # Check if this is an error_stop test (standalone program)
        with open(test_file, "r") as f:
            content: str = f.read()
        is_program: re.Match[str] | None = re.search(
            r"\bprogram\s+\w+",
            content,
            re.IGNORECASE,
        )

        if "error_stop" in test_file.name.lower() or is_program:
            # Compile as standalone program
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

        # Find module dependencies
        module_files: list[Path] = self.find_module_files(test_file, output_dir)

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


    def run_test_executable(
        self,
        executable: Path,
    ) -> tuple[bool, str, int]:
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
                timeout=30,
            )
            return True, result.stdout, result.returncode
        except subprocess.TimeoutExpired:
            return False, "Test timed out", -1
        except Exception as e:
            return False, str(e), -1


    def parse_test_output(
        self,
        output: str,
    ) -> list[TestResult]:
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


    def check_error_stop_test(
        self,
        test_file: Path,
        output_dir: Path,
    ) -> list[TestResult]:
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


    def _handle_error_stop_test(
        self,
        test_file: Path,
        output_dir: Path,
    ) -> list[TestResult]:
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
            # Find module dependencies
            module_files: list[Path] = self.find_module_files(test_file, output_dir)

            # Generate main program for normal tests
            main_program: Path = self.generate_test_program(
                test_file,
                test_module_name,
                normal_tests,
                output_dir,
            )

            # Compile all files
            executable: Path = output_dir / f"{test_file.stem}_normal"
            compile_cmd: list[str] = [self.compiler, "-o", str(executable)]
            compile_cmd.extend([str(f) for f in module_files])
            compile_cmd.append(str(test_file))
            compile_cmd.append(str(main_program))

            if self.verbose:
                print(f"Compiling normal tests: {' '.join(compile_cmd)}")

            try:
                subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                success: bool
                output: str
                success, output, _ = self.run_test_executable(executable)

                if not success:
                    print(f"{Colors.RED.value}Test execution failed{Colors.RESET.value}")
                    print(output)
                else:
                    # Print the test output (includes colored PASS/FAIL)
                    print(output)
                    all_results.extend(self.parse_test_output(output))

            except subprocess.CalledProcessError as e:
                print(
                    f"{Colors.RED.value}Compilation failed for normal tests"
                    f"{Colors.RESET.value}"
                )
                print(e.stderr)

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
        module_files: list[Path] = self.find_module_files(test_file, output_dir)

        # Generate standalone program for this error_stop test
        error_program: Path = self.generate_error_stop_test_program(
            test_file,
            test_module_name,
            test_subroutine,
            output_dir,
        )

        # Compile
        executable: Path = output_dir / test_subroutine
        compile_cmd: list[str] = [self.compiler, "-o", str(executable)]
        compile_cmd.extend([str(f) for f in module_files])
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
        _, output, returncode = self.run_test_executable(executable)

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


    def run_tests(
        self,
        test_files: list[Path],
    ) -> None:
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
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir: Path = Path(tmpdir)

            for test_file in test_files:
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


    def print_summary(
        self,
    ) -> int:
        """
        Print final test summary.

        Returns
        -------
        int
            Exit code (0 if all tests passed, 1 otherwise)
        """
        separator: str = "=" * 50

        print("All tests completed.")
        print(separator)
        print(f"Total tests: {self.total_tests}")
        print(f"{Colors.GREEN.value}{MessageTag.PASS.value}{self.passed_tests:>4}{Colors.RESET.value}")
        print(f"{Colors.RED.value}{MessageTag.FAIL.value}{self.failed_tests:>4}{Colors.RESET.value}")
        print(separator)

        if self.failed_tests == 0 and self.total_tests > 0:
            print(f"\n{Colors.GREEN.value}{Colors.BOLD.value}All tests passed! ✓{Colors.RESET.value}")
            return 0
        else:
            print(f"\n{Colors.RED.value}{Colors.BOLD.value}Some tests failed ✗{Colors.RESET.value}")
            return 1


def get_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed command line arguments
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="fortest - Automated test runner for Fortran",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fortest                              # Run all test_*.f90 files
  fortest examples/module_test_sample.f90  # Run specific test file
  fortest "module_test_*.f90"          # Run all module test files
  fortest -v                           # Verbose output
        """,
    )
    parser.add_argument(
        "pattern",
        nargs="?",
        default="test_*.f90",
        help="Test file pattern or specific file (default: test_*.f90)",
    )
    parser.add_argument(
        "--compiler",
        default="gfortran",
        help="Fortran compiler to use (default: gfortran)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        help="Build directory (default: temporary directory)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for ftest runner.

    Returns
    -------
    int
        Exit code
    """
    args: argparse.Namespace = get_arguments()

    runner: FortranTestRunner = FortranTestRunner(
        compiler=args.compiler,
        verbose=args.verbose,
        build_dir=args.build_dir,
    )

    test_files: list[Path] = runner.find_test_files(args.pattern)

    if not test_files:
        print(
            f"{Colors.YELLOW.value}No test files matching '{args.pattern}' found"
            f"{Colors.RESET.value}"
        )
        return 1

    runner.run_tests(test_files)
    return runner.print_summary()


if __name__ == "__main__":
    sys.exit(main())
