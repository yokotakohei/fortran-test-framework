#!/usr/bin/env python3
"""
CLI entry for fortest (thin wrapper).
"""

import argparse
import sys
from pathlib import Path

from fortest import __version__ as FORTEST_VERSION
from fortest.exit_status import ExitStatus
from fortest.test_result import Colors
from fortest.fortran_test_runner import FortranTestRunner


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
    parser.add_argument(
        "--version",
        action="version",
        version=f"fortest {FORTEST_VERSION}",
        help="Show program's version number and exit",
    )
    return parser.parse_args()


def main() -> int:
    """
    Main function for CLI.
    """
    try:
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
    
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW.value}Test execution interrupted by user{Colors.RESET.value}")
        return ExitStatus.ERROR.value
    
    except Exception as e:
        print(f"{Colors.RED.value}Error: {e}{Colors.RESET.value}")
        if args.verbose if "args" in locals() else False:
            import traceback
            traceback.print_exc()
        return ExitStatus.ERROR.value


if __name__ == "__main__":
    sys.exit(main())