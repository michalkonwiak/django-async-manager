import logging
import random
import time
from functools import wraps
from typing import Callable, TypeVar, Any

from django.db import OperationalError

T = TypeVar("T")

logger = logging.getLogger("django_async_manager.utils")


def with_database_lock_handling(
    max_retries: int = 5,
    max_sleep_time: float = 10.0,
    logger_name: str = "django_async_manager.utils",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that handles database locks by retrying the operation with exponential backoff.

    Args:
        max_retries: Maximum number of retries before giving up
        max_sleep_time: Maximum sleep time in seconds
        logger_name: Name of the logger to use

    Returns:
        A decorator function that wraps the original function with database lock handling
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            local_logger = logging.getLogger(logger_name)
            retry_count = 0

            while retry_count < max_retries:
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e):
                        retry_count += 1
                        if retry_count < max_retries:
                            sleep_time = min(
                                (2**retry_count) * 0.1 + (random.random() * 0.1),
                                max_sleep_time,
                            )
                            func_name = (
                                func.__name__
                                if hasattr(func, "__name__")
                                else "function"
                            )
                            local_logger.warning(
                                f"Database locked during {func_name}, retrying in {sleep_time:.2f} seconds "
                                f"(attempt {retry_count}/{max_retries})"
                            )
                            time.sleep(sleep_time)
                        else:
                            func_name = (
                                func.__name__
                                if hasattr(func, "__name__")
                                else "function"
                            )
                            local_logger.error(
                                f"Max retries exceeded for database lock during {func_name}, continuing without saving"
                            )
                            return None  # type: ignore
                    else:
                        func_name = (
                            func.__name__ if hasattr(func, "__name__") else "function"
                        )
                        local_logger.exception(f"Error during {func_name}")
                        raise
                except Exception as e:
                    func_name = (
                        func.__name__ if hasattr(func, "__name__") else "function"
                    )
                    local_logger.exception(f"Unexpected error during {func_name}: {e}")
                    raise

            return None  # type: ignore

        return wrapper

    return decorator
