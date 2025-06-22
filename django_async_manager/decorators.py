import inspect
from functools import wraps
from typing import Optional, Callable, Union, List
from django_async_manager.models import Task, TASK_REGISTRY


def background_task(
    priority: str = "medium",
    queue: str = "default",
    dependencies: Optional[Union[Task, List[Union[Task, Callable]]]] = None,
    autoretry: bool = True,
    retry_delay: int = 60,
    retry_backoff: float = 2.0,
    max_retries: int = 1,
    timeout: int = 300,
    memory_limit: Optional[int] = None,
) -> Callable:
    """
    Decorator for marking a function as a background task.

    Args:
        priority: Task priority level ("low", "medium", "high", "critical")
        queue: Queue name for task processing
        dependencies: Tasks that must complete before this task runs
        autoretry: Whether to automatically retry failed tasks
        retry_delay: Initial delay between retries in seconds
        retry_backoff: Multiplier for increasing delay between retries
        max_retries: Maximum number of retry attempts
        timeout: Maximum execution time in seconds
        memory_limit: Maximum memory usage in MB (None for no limit)
    """
    valid_priorities = list(Task.PRIORITY_MAPPING.keys())
    if priority not in valid_priorities:
        raise ValueError(
            f"Invalid priority: '{priority}'. Must be one of: {', '.join(valid_priorities)}"
        )

    def decorator(func: Callable) -> Callable:
        TASK_REGISTRY[func.__name__] = f"{func.__module__}.{func.__name__}"

        @wraps(func)
        def wrapper(*args, **kwargs) -> Task:
            dep_list = []
            if dependencies:
                raw = (
                    dependencies
                    if isinstance(dependencies, (list, tuple))
                    else [dependencies]
                )
                for dep in raw:
                    if isinstance(dep, Task):
                        dep_list.append(dep)
                    elif callable(dep):
                        if hasattr(dep, "run_async"):
                            sig = inspect.signature(dep.__wrapped__)
                            if sig.parameters:
                                result = dep.run_async(*args, **kwargs)
                            else:
                                result = dep.run_async()
                        else:
                            try:
                                result = dep(*args, **kwargs)
                            except TypeError:
                                result = dep()
                        if not isinstance(result, Task):
                            raise ValueError(
                                f"Dependency callable must return Task, got {type(result)}"
                            )
                        dep_list.append(result)
                    else:
                        raise ValueError(f"Unsupported dependency type: {type(dep)}")

            task = Task.objects.create(
                name=func.__name__,
                arguments={"args": args, "kwargs": kwargs},
                status="pending",
                priority=Task.PRIORITY_MAPPING.get(
                    priority, Task.PRIORITY_MAPPING["medium"]
                ),
                queue=queue,
                autoretry=autoretry,
                retry_delay=retry_delay,
                retry_backoff=retry_backoff,
                max_retries=max_retries,
                timeout=timeout,
                memory_limit=memory_limit,
            )
            if dep_list:
                task.dependencies.set(dep_list)
            return task

        wrapper.run_async = wrapper
        return wrapper

    return decorator
