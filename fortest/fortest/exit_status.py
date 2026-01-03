"""
Module providing exit status enum.
"""
from enum import Enum


class ExitStatus(Enum):
    """
    Enum of exit status
    """
    SUCCESS = 0
    ERROR = 1
