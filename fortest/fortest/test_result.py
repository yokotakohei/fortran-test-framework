#!/usr/bin/env python3
"""
Module defining test result structures and enums.
"""

from enum import Enum


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
    # Prevent pytest from collecting this as a test class (it has an __init__)
    __test__ = False
    def __init__(self,
        name: str,
        passed: bool,
        message: str = "",
    ) -> None:
        self.name: str = name
        self.passed: bool = passed
        self.message: str = message
