from functools import wraps
from typing import Optional, Callable

from task_queue.models import Task, TASK_REGISTRY


def background_task(parent_task: Optional[Task] = None) -> Callable:
    """Decorator for registering background tasks."""

    def decorator(func: Callable) -> Callable:
        TASK_REGISTRY[func.__name__] = func

        @wraps(func)
        def wrapper(*args, **kwargs) -> Task:
            task = Task.objects.create(
                name=func.__name__,
                arguments={"args": args, "kwargs": kwargs},
                status="pending",
                parent_task=parent_task,
            )
            return task

        wrapper.run_async = wrapper
        return wrapper

    return decorator
