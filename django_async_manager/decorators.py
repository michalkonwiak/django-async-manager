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
) -> Callable:
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
            )
            if dep_list:
                task.dependencies.set(dep_list)
            return task

        wrapper.run_async = wrapper
        return wrapper

    return decorator
