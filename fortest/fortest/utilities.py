"""
A module providing functions for general purposes.
"""

from typing import Any, TypeVar, Iterable

T = TypeVar("T")


def deduplicate(input_list: Iterable[T]) -> list[T]:
    """
    Returns a list of unique elements while preserving original order.

    Parameters
    ----------
    input_list : Iterable[T]
        The sequence of elements to be filtered.
    
    Returns
    -------
    list[T]
        A new list with unique elements in their original order.
    """
    return list(dict.fromkeys(input_list))