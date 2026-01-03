#!/usr/bin/env python3
"""
CLI entry for fortest (thin wrapper).
"""

import argparse
import sys
from pathlib import Path

from fortest.exit_status import ExitStatus
from fortest.test_result import Colors
from fortest.runner import FortranTestRunner


def get_arguments() -> argparse.Namespace:
    """
    Gets and returns command line arguments.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="fortest - Automated test runner for Fortran",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    Main function for CLI.
    """
    args = get_arguments()
    runner = FortranTestRunner(
        compiler=args.compiler,
        verbose=args.verbose,
        build_dir=args.build_dir,
    )
    test_files = runner.find_test_files(args.pattern)
    if not test_files:
        print(
            f"{Colors.YELLOW.value}No test files matching '{args.pattern}' found"
            f"{Colors.RESET.value}"
        )
        return ExitStatus.ERROR.value
    
    runner.run_tests(test_files)

    return runner.print_summary()


if __name__ == "__main__":
    sys.exit(main())