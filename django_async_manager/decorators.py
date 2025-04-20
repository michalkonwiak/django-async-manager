from functools import wraps
from typing import Optional, Callable, Union, List

from django_async_manager.models import Task, TASK_REGISTRY


def background_task(
    priority: str = "medium",
    queue: str = "default",
    dependencies: Optional[Union[Task, List[Task]]] = None,
    autoretry: bool = True,
    retry_delay: int = 60,
    retry_backoff: float = 2.0,
    max_retries: int = 1,
    timeout: int = 300,
) -> Callable:
    """Decorator for registering background tasks."""

    def decorator(func: Callable) -> Callable:
        module_name = func.__module__
        func_name = func.__name__
        TASK_REGISTRY[func_name] = f"{module_name}.{func_name}"

        @wraps(func)
        def wrapper(*args, **kwargs) -> Task:
            dep_list = []
            if dependencies:
                raw_deps = (
                    dependencies
                    if isinstance(dependencies, (list, tuple))
                    else [dependencies]
                )
                for dep in raw_deps:
                    if isinstance(dep, Task):
                        dep_list.append(dep)
                    elif callable(dep):
                        dep_task = dep.run_async()
                        dep_list.append(dep_task)
                    else:
                        raise ValueError(f"Unsupported dependency type: {type(dep)}")

            task = Task.objects.create(
                name=func_name,
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
