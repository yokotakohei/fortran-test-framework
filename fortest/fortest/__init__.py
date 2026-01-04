"""
fortest - Automated test runner for Fortran.

A simple test discovery and execution framework for Fortran with
automatic test harness generation.
"""

__version__ = "0.1.0"

from fortest.fortran_test_runner import FortranTestRunner
from fortest.fortran_test_executor import FortranTestExecutor

__all__ = ["FortranTestRunner", "FortranTestExecutor"]