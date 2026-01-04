"""
Tests for TestResultFormatter class.
Tests are ordered according to method definitions in test_result_formatter.py.
"""

import pytest

from fortest.test_result_formatter import TestResultFormatter


@pytest.fixture
def formatter() -> TestResultFormatter:
    """
    Create a TestResultFormatter instance for testing.
    """
    return TestResultFormatter(verbose=False)


def test_parse_test_output_with_pass(formatter: TestResultFormatter) -> None:
    """
    Test parse_test_output with passing tests.
    Verify that it correctly parses [PASS] tags.
    """
    output = "[PASS] test_addition\n[PASS] test_subtraction"
    results = formatter.parse_test_output(output)

    assert len(results) == 2
    assert results[0].name == "test_addition"
    assert results[0].passed is True
    assert results[1].name == "test_subtraction"
    assert results[1].passed is True


def test_parse_test_output_with_fail(formatter: TestResultFormatter) -> None:
    """
    Test parse_test_output with failing tests.
    Verify that it correctly parses [FAIL] tags.
    """
    output = "[FAIL] test_division\n[PASS] test_addition"
    results = formatter.parse_test_output(output)

    assert len(results) == 2
    assert results[0].name == "test_division"
    assert results[0].passed is False
    assert results[1].name == "test_addition"
    assert results[1].passed is True


def test_parse_test_output_empty(formatter: TestResultFormatter) -> None:
    """
    Test parse_test_output with empty output.
    Verify that it returns an empty list.
    """
    output = ""
    results = formatter.parse_test_output(output)

    assert results == []


def test_filter_fpm_output(formatter: TestResultFormatter) -> None:
    """
    Test _filter_fpm_output.
    Verify that it filters FPM build messages while preserving test results.
    """
    # Test with FPM build messages and test results
    raw_output = """[  0%] fortest_test_12345678
[ 50%] fortest_test_12345678  done.
<INFO> Building project...
[PASS] Addition should work correctly
       Expected: 5
       Got: 5
[FAIL] Subtraction should work correctly
       Expected: 3
       Got: 2
STOP 0
fpm build complete"""

    filtered = formatter.filter_fpm_output(raw_output)

    # Should contain test results
    assert "[PASS] Addition should work correctly" in filtered
    assert "[FAIL] Subtraction should work correctly" in filtered
    assert "       Expected: 5" in filtered
    assert "       Expected: 3" in filtered

    # Should not contain FPM messages
    assert "[  0%]" not in filtered
    assert "[ 50%]" not in filtered
    assert "done." not in filtered
    assert "<INFO>" not in filtered
    assert "STOP 0" not in filtered
    assert "fpm build complete" not in filtered


def test_filter_fpm_output_empty(formatter: TestResultFormatter) -> None:
    """
    Test _filter_fpm_output with only FPM messages.
    Verify that output becomes empty when there are no test results.
    """
    raw_output = """[  0%] Building...
[ 50%] Compiling...
[100%] Linking...
fpm build complete"""

    filtered = formatter.filter_fpm_output(raw_output)

    # Should be empty (only whitespace)
    assert filtered.strip() == ""


def test_filter_fpm_output_preserves_other_output(
    formatter: TestResultFormatter,
) -> None:
    """
    Test _filter_fpm_output preserves non-FPM output.
    Verify that custom test output is preserved.
    """
    raw_output = """[  0%] Building...
[PASS] Test passed
Debug: Custom debug message
Another custom message
fpm build complete"""

    filtered = formatter.filter_fpm_output(raw_output)

    # Should preserve test results and custom messages
    assert "[PASS] Test passed" in filtered
    assert "Debug: Custom debug message" in filtered
    assert "Another custom message" in filtered

    # Should not contain FPM messages
    assert "[  0%]" not in filtered
    assert "fpm build complete" not in filtered