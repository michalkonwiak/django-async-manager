[![PyPI Version](https://img.shields.io/pypi/v/django-async-manager.svg)](https://pypi.org/project/django-async-manager/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/django-async-manager)](https://pypi.org/project/django-async-manager/)
[![Django Version](https://img.shields.io/badge/django-3.2%2B-green.svg)](https://www.djangoproject.com/)
[![CI](https://github.com/michalkonwiak/django-async-manager/actions/workflows/ci.yaml/badge.svg)](https://github.com/michalkonwiak/django-async-manager/actions/workflows/ci.yaml)
[![Development Status](https://img.shields.io/badge/status-beta-orange.svg)](https://pypi.org/project/django-async-manager/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/django-async-manager.svg)](https://pypi.org/project/django-async-manager/)
[![Last Commit](https://img.shields.io/github/last-commit/michalkonwiak/django-async-manager)](https://github.com/michalkonwiak/django-async-manager/commits/master)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![GitHub Stars](https://img.shields.io/github/stars/michalkonwiak/django-async-manager?style=social)](https://github.com/michalkonwiak/django-async-manager)

# Django Async Manager

Django library for managing asynchronous tasks with scheduling and dependency management.

## Features

- **Background Tasks**: Run Django functions asynchronously in the background
- **Task Scheduling**: Schedule tasks to run at specific times using cron-like syntax
- **Task Dependencies**: Define dependencies between tasks to ensure proper execution order
- **Priority Queues**: Assign priorities to tasks and process them accordingly
- **Automatic Retries**: Configure automatic retries with exponential backoff for failed tasks
- **Multiple Workers**: Run multiple workers using threads or processes
- **Task Timeouts**: Set timeouts for long-running tasks
- **Memory Management**: Set memory limits for tasks to prevent resource exhaustion
- **Monitoring**: Track task status, execution time, and errors

## Installation

### From PyPI

```bash
pip install django-async-manager
```

## Quick Start

1. Add `'django_async_manager'` to your `INSTALLED_APPS` in settings.py:

```python
INSTALLED_APPS = [
    # ...
    'django_async_manager',
    # ...
]
```

2. Run migrations to create the necessary database tables:

```bash
python manage.py migrate django_async_manager
```

3. Define a background task:

```python
from django_async_manager.decorators import background_task

@background_task(priority="high", max_retries=3)
def process_data(user_id, data):
    # Your long-running code here
    return result
```

4. Call the task asynchronously:

```python
# This will create a task and return immediately
task = process_data.run_async(user_id=123, data={"key": "value"})

# You can check the task status later
print(f"Task status: {task.status}")
```

5. Start a worker to process tasks:

```bash
python manage.py run_worker --num-workers=2
```

## Scheduling Periodic Tasks

1. Define your schedule in settings.py:

```python
BEAT_SCHEDULE = {
    'daily-report': {
        'task': 'myapp.tasks.generate_daily_report',
        'schedule': {
            'hour': '0',  # Run at midnight
            'minute': '0',
        },
        'args': [],
        'kwargs': {'send_email': True},
    },
}
```

2. Update the schedule in the database:

```bash
python manage.py update_beat_schedule
```

3. Start the scheduler:

```bash
python manage.py run_scheduler
```

## Advanced Usage

### Task Dependencies

```python
# Create a dependent task that will only run after task1 and task2 are completed
dependent_task = generate_report.run_async(dependencies=[task1, task2])
```

### Task Queues

```python
@background_task(queue="email")
def send_email(to, subject, body):
    # Send email logic
    pass

# Start a worker for the email queue
# python manage.py run_worker --queue=email
```

### Worker Execution Modes

By default, workers run in thread mode, but you can also run them as separate processes:

```bash
# Run workers in thread mode (default)
python manage.py run_worker --num-workers=2 --queue=default

# Run workers in process mode
python manage.py run_worker --num-workers=2 --processes --queue=default
```

Thread mode is more memory-efficient but may be affected by Python's Global Interpreter Lock (GIL). Process mode provides true parallelism but uses more memory.

### Timeout Configuration

```python
@background_task(timeout=60)  # 60 seconds timeout
def process_large_file(file_path):
    # Process file
    pass
```

### Memory Limit Configuration

You can set memory limits for tasks to prevent them from consuming too much memory:

```python
@background_task(memory_limit=256)  # 256 MB memory limit
def memory_intensive_task(data):
    # Process data
    pass
```

**Important**: Memory limits are only supported when using processes, not threads. If you specify a memory limit for a task that runs in a thread-based worker, the limit will be ignored and a warning will be logged.

To use memory limits effectively, make sure to run your workers in process mode:

```bash
# Run workers in process mode to enable memory limits
python manage.py run_worker --num-workers=2 --processes
```

If a task exceeds its memory limit, it will be terminated and can be configured to retry automatically:

```python
@background_task(
    memory_limit=512,         # 512 MB memory limit
    max_retries=3,            # Retry up to 3 times
    retry_delay=60            # Wait 60 seconds before first retry
)
def process_large_dataset(dataset_id):
    # Process large dataset
    pass
```

### Task Priority

You can assign different priority levels to tasks:

```python
@background_task(priority="high")  # Options: "low", "medium", "high", "critical"
def important_task():
    # High priority operation
    pass
```

Tasks are processed in order of priority, with higher priority tasks being executed first.

### Retry Configuration

You can configure automatic retries for failed tasks:

```python
@background_task(
    max_retries=3,           # Maximum number of retry attempts
    retry_delay=60,          # Initial delay between retries in seconds
    retry_backoff=2.0        # Multiplier for increasing delay between retries
)
def unreliable_operation():
    # Operation that might fail
    pass
```

With the above configuration, retries would occur after 60s, 120s, and 240s (with exponential backoff).

### Decorator Parameters Reference

The `@background_task` decorator accepts the following parameters:

```python
@background_task(
    priority="medium",       # Task priority: "low", "medium", "high", "critical"
    queue="default",         # Queue name for task processing
    dependencies=None,       # Tasks that must complete before this task runs
    autoretry=True,          # Whether to automatically retry failed tasks
    retry_delay=60,          # Initial delay between retries in seconds
    retry_backoff=2.0,       # Multiplier for increasing delay between retries
    max_retries=1,           # Maximum number of retry attempts
    timeout=300,             # Maximum execution time in seconds
    memory_limit=None,       # Maximum memory usage in MB (None for no limit)
)
def my_task():
    # Task implementation
    pass
```

## Logging Configuration

Django Async Manager uses Python's standard logging module to log information about task execution, scheduling, and errors. By default, the package configures basic logging for its management commands to ensure logs are visible even without explicit configuration.

### Default Loggers

The package uses the following loggers:

- `django_async_manager.worker`: For worker-related logs (task execution, errors)
- `django_async_manager.scheduler`: For scheduler-related logs (periodic tasks, scheduling)

### Customizing Logging

To customize logging in your project, add the following configuration to your Django settings:

```python
LOGGING = {
    # Your existing logging configuration...

    "formatters": {
        "verbose": {
            "format": "{asctime} - {levelname} - {name} - {message}",
            "style": "{",
        },
        # Other formatters...
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "django_async_manager.log",  # Customize the path as needed
            "formatter": "verbose",
        },
        # Other handlers...
    },
    "loggers": {
        "django_async_manager.worker": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django_async_manager.scheduler": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Other loggers...
    },
}
```

This configuration will ensure that logs from Django Async Manager are properly captured and displayed in your project.

## License

MIT License
