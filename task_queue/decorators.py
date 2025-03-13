import json
from functools import wraps
from task_queue.models import Task


def background_task(func):
    """Decorator for registering background tasks."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        task = Task.objects.create(
            name=func.__name__,
            arguments=json.dumps({"args": args, "kwargs": kwargs}),
            status="pending",
        )
        return task

    wrapper.run_async = wrapper
    return wrapper
