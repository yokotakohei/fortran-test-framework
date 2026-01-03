"""
Tests for fortest/test_result.py
"""
import pytest
from fortest.test_result import Colors, MessageTag, TestResult


def test_colors_values():
    assert Colors.RED.value.startswith("\033[")
    assert Colors.RESET.value == "\033[0m"


def test_message_tags():
    assert MessageTag.PASS.value == "[PASS]"
    assert MessageTag.FAIL.value == "[FAIL]"


def test_testresult_container():
    tr = TestResult("mytest", True, "ok")
    assert tr.name == "mytest"
    assert tr.passed is True
    assert tr.message == "ok"
