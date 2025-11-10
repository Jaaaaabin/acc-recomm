"""
Simple time measurement decorator with colored output.
"""

import time
import functools
from typing import Callable, TypeVar, Any, cast
from pathlib import Path

T = TypeVar("T")

# ANSI color codes (works in most terminals)
COLOR_GREEN = "\033[92m"
COLOR_BLUE = "\033[94m"
COLOR_YELLOW = "\033[93m"
COLOR_RESET = "\033[0m"

def measure_runtime(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that measures and prints the execution time of a function,
    including the source file where it is defined.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time

        filename = Path(func.__code__.co_filename).name

        print(
            "Function {}'{}'{} in file {}'{}'{} completed in {}{:.2f}{} seconds".format(
                COLOR_YELLOW, func.__name__, COLOR_RESET,
                COLOR_BLUE, filename, COLOR_RESET,
                COLOR_GREEN, elapsed, COLOR_RESET
            )
        )

        return result

    return cast(Callable[..., T], wrapper)
