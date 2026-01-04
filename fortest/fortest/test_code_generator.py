"""
Module for generating test programs for Fortran tests.
"""

import re
from pathlib import Path
from typing import ClassVar


class TestCodeGenerator:
    """
    Generates Fortran test programs.

    Creates wrapper programs that call test subroutines and handle
    different test types (normal tests vs error_stop tests).
    """
    # Module name of fortest assertion
    ASSERTION_MODULE: ClassVar[str] = "fortest_assertions"

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize the test code generator.

        Parameters
        ----------
        verbose : bool, optional
            Enable verbose output, by default False
        """
        self._verbose: bool = verbose


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

        if self._verbose:
            print(f"Found test subroutines: {test_subroutines}")

        return test_subroutines


    def separate_error_stop_tests(
        self,
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


    def generate_test_program(
        self,
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
        program_content += f"    use {self.ASSERTION_MODULE}\n"
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

        if self._verbose:
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

        if self._verbose:
            print(f"Generated error_stop test program:\n{program_content}")

        return generated_file


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
        program_content: str = f"program run_{test_subroutine}\n"
        program_content += f"    use {self.ASSERTION_MODULE}\n"
        program_content += f"    use {test_module_name}\n"
        program_content += "    implicit none\n"
        program_content += f"    call {test_subroutine}()\n"
        program_content += f"end program run_{test_subroutine}\n"

        generated_file: Path = output_dir / f"gen_{test_subroutine}.f90"
        with open(generated_file, "w") as f:
            f.write(program_content)

        if self._verbose:
            print(f"Generated program for {test_subroutine}:\n{program_content}")

        return generated_file