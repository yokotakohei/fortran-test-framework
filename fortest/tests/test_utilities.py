"""
Tests of fortest/utilities.py
Tests are ordered according to method definitions in runner.py.
"""

import pytest

import fortest.utilities as utils


def test_deduplicate():
    """
    Tests deduplicate.
    Verify that it deduplicates list.
    """
    test_list: list[str] = ["a", "b", "b", "c", "z", "d", "z", "d"]
    correct: list[str] = ["a", "b", "c", "z", "d"]
    expected: list[str] = utils.deduplicate(test_list)

    assert expected == correct