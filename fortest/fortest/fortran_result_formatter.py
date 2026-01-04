"""
Module for formatting and displaying test results.
"""

import re
from fortest.test_result import Colors, MessageTag, TestResult
from fortest.exit_status import ExitStatus


class FortranResultFormatter:
    """
    Formats and displays test results.

    Handles parsing of test output, filtering of build system messages,
    and presentation of test summaries.
    """
    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize the test result formatter.

        Parameters
        ----------
        verbose : bool, optional
            Enable verbose output, by default False
        """
        self._verbose: bool = verbose


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


    def filter_fpm_output(self, output: str) -> str:
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
        # Remove common FPM build/progress messages
        filtered_lines = []
        for line in output.split('\n'):
            # Keep lines with test results
            if "[PASS]" in line or "[FAIL]" in line:
                filtered_lines.append(line)
                continue

            # Keep lines that look like assertion details (indented with whitespace)
            if line.startswith('       '):
                filtered_lines.append(line)
                continue

            # Skip FPM build information lines and common FPM messages
            if any(skip in line for skip in [
                f"fpm build complete",
                f"fpm test complete",
                "+ mkdir",
                "+ gfortran",
                "+ ar",
                "build/gfortran",
                "[100%]",
                "[  0%]",
                "[ 50%]",
                "building",
                "<INFO>",
                "STOP 0",
                " done.",
            ]):
                continue

            # Skip empty lines
            if not line.strip():
                continue

            # Keep other lines (might be test output)
            filtered_lines.append(line)
        return "\n".join(filtered_lines)


    def print_normal_test_summary(self, normal_results: list[TestResult]) -> None:
        """
        Print summary for normal tests.

        Parameters
        ----------
        normal_results : list[TestResult]
            List of normal test results
        """
        # Print individual results
        for result in normal_results:
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
        normal_passed: int = sum(1 for r in normal_results if r.passed)
        normal_failed: int = len(normal_results) - normal_passed

        print()
        print(separator)
        print(f"Normal tests: {len(normal_results)}")
        print(f"{Colors.GREEN.value}{MessageTag.PASS.value}{normal_passed:>4}{Colors.RESET.value}")
        print(f"{Colors.RED.value}{MessageTag.FAIL.value}{normal_failed:>4}{Colors.RESET.value}")
        print(separator)
        print()


    def print_error_stop_summary(self, error_stop_results: list[TestResult]) -> None:
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


    def print_final_summary(
        self,
        total_tests: int,
        passed_tests: int,
        failed_tests: int
    ) -> int:
        """
        Print final test summary.

        Parameters
        ----------
        total_tests : int
            Total number of tests executed
        passed_tests : int
            Number of tests that passed
        failed_tests : int
            Number of tests that failed

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
        print(f"Total tests: {total_tests}")
        print(f"{Colors.GREEN.value}{MessageTag.PASS.value}{passed_tests:>4}{Colors.RESET.value}")
        print(f"{Colors.RED.value}{MessageTag.FAIL.value}{failed_tests:>4}{Colors.RESET.value}")
        print(separator_table)

        if failed_tests == 0 and total_tests > 0:
            print(f"\n{Colors.GREEN.value}{Colors.BOLD.value}All tests passed! ✓{Colors.RESET.value}")
            return ExitStatus.SUCCESS.value
        else:
            print(f"\n{Colors.RED.value}{Colors.BOLD.value}Some tests failed ✗{Colors.RESET.value}")
            return ExitStatus.ERROR.value