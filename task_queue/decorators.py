from functools import wraps
from typing import Optional, Callable, Union, List

from task_queue.models import Task, TASK_REGISTRY


def background_task(
    dependencies: Optional[Union[Task, List[Task]]] = None,
    autoretry: bool = True,
    retry_delay: int = 60,
    retry_backoff: float = 2.0,
    max_retries: int = 1,
) -> Callable:
    """Decorator for registering background tasks."""

    def decorator(func: Callable) -> Callable:
        TASK_REGISTRY[func.__name__] = func

        @wraps(func)
        def wrapper(*args, **kwargs) -> Task:
            task = Task.objects.create(
                name=func.__name__,
                arguments={"args": args, "kwargs": kwargs},
                status="pending",
                autoretry=autoretry,
                retry_delay=retry_delay,
                retry_backoff=retry_backoff,
                max_retries=max_retries,
            )
            if dependencies:
                deps = (
                    dependencies
                    if isinstance(dependencies, (list, tuple))
                    else [dependencies]
                )
                task.dependencies.set(deps)
            return task

        wrapper.run_async = wrapper
        return wrapper

    return decorator
