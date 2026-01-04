"""
Test execution logic for Fortran tests.
"""

import subprocess
import tempfile
from pathlib import Path

from fortest.test_result import TestResult
from fortest.build_system_detector import BuildSystemDetector, BuildSystemInfo
from fortest.module_dependency_resolver import ModuleDependencyResolver
from fortest.fortran_test_generator import FortranTestGenerator
from fortest.fortran_result_formatter import FortranResultFormatter
from fortest.project_builder import ProjectBuilder


class FortranTestExecutor:
    """
    Executes Fortran tests and manages test execution logic.
    
    Handles both normal tests and error_stop tests, coordinates with
    build systems or falls back to direct compilation.
    """

    def __init__(
        self,
        compiler: str,
        verbose: bool,
        detector: BuildSystemDetector,
        resolver: ModuleDependencyResolver,
        generator: FortranTestGenerator,
        formatter: FortranResultFormatter,
        builder: ProjectBuilder,
    ) -> None:
        """
        Initialize TestExecutor.
        
        Parameters
        ----------
        compiler : str
            Fortran compiler command
        verbose : bool
            Enable verbose output
        detector : BuildSystemDetector
            Build system detector instance
        resolver : ModuleDependencyResolver
            Module dependency resolver instance
        generator : TestCodeGenerator
            Test code generator instance
        formatter : TestResultFormatter
            Test result formatter instance
        builder : ProjectBuilder
            Project builder instance
        """
        self._compiler = compiler
        self._verbose = verbose
        self._detector = detector
        self._resolver = resolver
        self._generator = generator
        self._formatter = formatter
        self._builder = builder


    def is_standalone_program(self, test_file: Path) -> bool:
        """
        Check if test file is a standalone program.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        
        Returns
        -------
        bool
            True if standalone program or error_stop test
        """
        content = test_file.read_text().lower()
        
        # Check if it contains 'program' statement
        if "program " in content:
            return True
        
        # Check if filename contains 'error_stop'
        if "error_stop" in test_file.name.lower():
            return True
        
        return False


    def run_test_executable(self, executable: Path) -> tuple[bool, str, int]:
        """
        Run test executable and capture output.
        
        Parameters
        ----------
        executable : Path
            Path to executable
        
        Returns
        -------
        tuple[bool, str, int]
            (success, output, exit_code)
        """
        if self._verbose:
            print(f"Running: {executable}")
        
        try:
            result = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            
            if self._verbose:
                print(f"Exit code: {result.returncode}")
                if output:
                    print(f"Output:\n{output}")
            
            return success, output, result.returncode
        
        except subprocess.TimeoutExpired:
            return False, "Test execution timed out", -1
        except Exception as e:
            return False, f"Failed to run test: {e}", -1


    def check_error_stop_test(self, test_file: Path, output_dir: Path) -> list[TestResult]:
        """
        Check error_stop test execution.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        list[TestResult]
            List of test results
        """
        if self._verbose:
            print(f"\nChecking error_stop test: {test_file}")
        
        # Compile the standalone test
        executable, error = self._builder.compile_test(test_file, output_dir)
        
        if error:
            return [TestResult(
                name=test_file.stem,
                passed=False,
                message=f"Compilation failed:\n{error}",
            )]
        
        # Execute and check
        result = self._execute_and_check_error_stop(test_file.stem, executable)
        return [result]


    def _execute_and_check_error_stop(
        self,
        test_name: str,
        executable: Path,
    ) -> TestResult:
        """
        Execute test and verify error stop was triggered.
        
        Parameters
        ----------
        test_name : str
            Name of the test
        executable : Path
            Path to test executable
        
        Returns
        -------
        TestResult
            Test result
        """
        success, output, exit_code = self.run_test_executable(executable)
        
        # For error_stop tests, we expect failure (non-zero exit code)
        if exit_code != 0:
            return TestResult(
                name=test_name,
                passed=True,
                message=f"Successfully triggered error stop (exit code: {exit_code})",
            )
        else:
            return TestResult(
                name=test_name,
                passed=False,
                message=f"Expected error stop but test exited normally (exit code: {exit_code})",
            )


    def _handle_error_stop_test(self, test_file: Path, output_dir: Path) -> list[TestResult]:
        """
        Handle error_stop test execution.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        list[TestResult]
            List of test results
        """
        # Extract test subroutines
        test_subroutines = self._generator.extract_test_subroutines(test_file)
        
        if not test_subroutines:
            if self._verbose:
                print(f"No test subroutines found in {test_file}")
            return []
        
        # Separate error_stop tests
        _, error_stop_test_names = self._generator.separate_error_stop_tests(test_subroutines)
        
        if not error_stop_test_names:
            if self._verbose:
                print(f"No error_stop tests found in {test_file}")
            return []
        
        results = []
        module_name = test_file.stem
        
        for test_name in error_stop_test_names:
            if self._verbose:
                print(f"\nRunning error_stop test: {test_name}")
            
            result = self._run_single_error_stop_test(
                test_file,
                module_name,
                test_name,
                output_dir,
            )
            results.append(result)
        
        return results


    def _run_single_error_stop_test(
        self,
        test_file: Path,
        module_name: str,
        test_name: str,
        output_dir: Path,
    ) -> TestResult:
        """
        Run a single error_stop test.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        module_name : str
            Name of test module
        test_name : str
            Name of test subroutine
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        TestResult
            Test result
        """
        # Generate test program
        program_file = self._generator.generate_error_stop_test_program(
            module_name,
            test_name,
            output_dir,
        )
        
        # Compile
        executable, error = self._builder.compile_test(
            test_file,
            output_dir,
            program_file=program_file,
        )
        
        if error:
            return TestResult(
                name=test_name,
                passed=False,
                message=f"Compilation failed:\n{error}",
            )
        
        # Execute and check
        return self._execute_and_check_error_stop(test_name, executable)


    def _compile_and_run_normal_tests(
        self,
        test_file: Path,
        module_name: str,
        test_subroutines: list[str],
        output_dir: Path,
    ) -> list[TestResult]:
        """
        Compile and run normal (non-error_stop) tests.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        module_name : str
            Name of test module
        test_subroutines : list[str]
            List of test subroutine names
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        list[TestResult]
            List of test results
        """
        if not test_subroutines:
            return []
        
        results = []
        
        for test_name in test_subroutines:
            if self._verbose:
                print(f"\nRunning test: {test_name}")
            
            result = self._run_single_normal_test(
                test_file,
                module_name,
                test_name,
                output_dir,
            )
            results.append(result)
        
        return results


    def _run_single_normal_test(
        self,
        test_file: Path,
        module_name: str,
        test_name: str,
        output_dir: Path,
    ) -> TestResult:
        """
        Run a single normal test.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        module_name : str
            Name of test module
        test_name : str
            Name of test subroutine
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        TestResult
            Test result
        """
        # Generate test program that calls the single test
        program_file = self._generator.generate_single_test_program(
            module_name,
            test_name,
            output_dir,
        )
        
        # Compile the test
        executable, error = self._builder.compile_test(
            test_file,
            output_dir,
            program_file=program_file,
        )
        
        if error:
            return TestResult(
                name=test_name,
                passed=False,
                message=f"Compilation failed:\n{error}",
            )
        
        # Run the test
        success, output, exit_code = self.run_test_executable(executable)
        
        # Parse output
        parsed_results = self._formatter.parse_test_output(output)
        
        if parsed_results:
            return parsed_results[0]
        
        # If no parsed results, check exit code
        if success:
            return TestResult(
                name=test_name,
                passed=True,
                message="Test completed successfully",
            )
        else:
            return TestResult(
                name=test_name,
                passed=False,
                message=f"Test failed with exit code {exit_code}\n{output}",
            )


    def _handle_normal_test(self, test_file: Path, output_dir: Path) -> list[TestResult]:
        """
        Handle normal (non-error_stop) test execution.
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        list[TestResult]
            List of test results
        """
        # Extract test subroutines
        test_subroutines = self._generator.extract_test_subroutines(test_file)
        
        if not test_subroutines:
            if self._verbose:
                print(f"No test subroutines found in {test_file}")
            return []
        
        # Separate normal and error_stop tests
        normal_test_names, _ = self._generator.separate_error_stop_tests(test_subroutines)
        
        if not normal_test_names:
            if self._verbose:
                print(f"No normal tests found in {test_file}")
            return []
        
        module_name = test_file.stem
        
        # Compile and run tests
        return self._compile_and_run_normal_tests(
            test_file,
            module_name,
            normal_test_names,
            output_dir,
        )


    def handle_test_file(
        self,
        test_file: Path,
        output_dir: Path,
    ) -> tuple[list[TestResult], list[TestResult]]:
        """
        Handle a single test file (both normal and error_stop tests).
        
        Parameters
        ----------
        test_file : Path
            Path to test file
        output_dir : Path
            Directory for build artifacts
        
        Returns
        -------
        tuple[list[TestResult], list[TestResult]]
            (normal_results, error_stop_results)
        """
        # Check if standalone program
        if self.is_standalone_program(test_file):
            # Handle as error_stop test
            error_results = self.check_error_stop_test(test_file, output_dir)
            return [], error_results
        
        # Handle as module-based test
        normal_results = self._handle_normal_test(test_file, output_dir)
        error_results = self._handle_error_stop_test(test_file, output_dir)
        
        return normal_results, error_results
