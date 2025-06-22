import datetime
from datetime import timedelta
import uuid
from typing import Dict, Callable, Any

from django.db import models
from django.utils.timezone import now

TASK_REGISTRY: Dict[str, Callable[..., Any]] = {}


class Task(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]

    PRIORITY_MAPPING = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    priority = models.IntegerField(
        choices=[(v, k) for k, v in PRIORITY_MAPPING.items()], default=2
    )
    arguments = models.JSONField(help_text="JSON containing function arguments")
    created_at = models.DateTimeField(default=now)
    scheduled_at = models.DateTimeField(
        null=True, blank=True, help_text="Task will run at this time"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    timeout = models.IntegerField(
        default=300, help_text="Max execution time in seconds"
    )
    memory_limit = models.IntegerField(
        null=True, blank=True, help_text="Max memory usage in MB (None for no limit)"
    )
    attempts = models.IntegerField(default=0)
    max_retries = models.IntegerField(
        default=1, help_text="Max number of retries before marking as failed"
    )

    worker_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Identifier of the worker that processed this task",
    )
    dependencies = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="dependent_tasks",
        help_text="Tasks that must be completed before this one runs",
    )
    last_errors = models.JSONField(
        default=list, help_text="Stores last 5 error messages"
    )
    archived = models.BooleanField(
        default=False,
        help_text="If true, this task is archived for performance reasons",
    )
    queue = models.CharField(
        max_length=50,
        default="default",
        help_text="Name of the queue for routing tasks",
    )
    autoretry = models.BooleanField(
        default=True,
        help_text="Automatically retry the job in case of an error",
    )
    retry_delay = models.IntegerField(
        default=60,
        help_text="Initial delay (in seconds) before retrying",
    )
    retry_backoff = models.FloatField(
        default=2.0,
        help_text="Multiplier for exponential increase in delay",
    )

    class Meta:
        app_label = "django_async_manager"
        ordering = ["-priority", "created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["queue"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.status}) - Priority: {self.priority}"

    @property
    def is_ready(self):
        """Checks that the task is ready to execute."""
        if self.dependencies.exists():
            return not self.dependencies.exclude(status="completed").exists()
        return True

    def mark_as_failed(self, error_message):
        """Mark error and increment attempt counter (without autoretry)"""
        from django_async_manager.utils import with_database_lock_handling

        @with_database_lock_handling(logger_name="django_async_manager.worker")
        def _mark_as_failed_inner():
            self.attempts += 1
            if len(self.last_errors) >= 5:
                self.last_errors.pop(0)
            self.last_errors.append(error_message)
            self.status = "failed"
            self.save()

        _mark_as_failed_inner()

    def mark_as_completed(self):
        """Mark a task as completed and update timestamps"""
        from django_async_manager.utils import with_database_lock_handling

        @with_database_lock_handling(logger_name="django_async_manager.worker")
        def _mark_as_completed_inner():
            self.status = "completed"
            self.completed_at = now()
            self.save()

        _mark_as_completed_inner()

    def can_retry(self):
        """Check if task can be retried"""
        return self.attempts < self.max_retries

    def schedule_retry(self, error_message: str) -> None:
        """Planning to retry a task using exponential backoff."""
        from django_async_manager.utils import with_database_lock_handling

        @with_database_lock_handling(logger_name="django_async_manager.worker")
        def _schedule_retry_inner():
            self.attempts += 1
            if len(self.last_errors) >= 5:
                self.last_errors.pop(0)
            self.last_errors.append(error_message)
            if self.attempts < self.max_retries:
                delay_seconds = int(
                    self.retry_delay * (self.retry_backoff ** (self.attempts - 1))
                )
                self.scheduled_at = now() + timedelta(seconds=delay_seconds)
                self.status = "pending"
            else:
                self.status = "failed"
            self.save()

        _schedule_retry_inner()


class CrontabSchedule(models.Model):
    minute = models.CharField(
        max_length=64, default="*", help_text="Minute field, e.g. '*' or '0,15,30,45'"
    )
    hour = models.CharField(
        max_length=64, default="*", help_text="Hour field, e.g. '*' or '0,12'"
    )
    day_of_week = models.CharField(
        max_length=64, default="*", help_text="Day of week field, e.g. '*' or 'mon-fri'"
    )
    day_of_month = models.CharField(
        max_length=64, default="*", help_text="Day of month field, e.g. '*' or '1,15'"
    )
    month_of_year = models.CharField(
        max_length=64,
        default="*",
        help_text="Month of year field, e.g. '*' or '1,6,12'",
    )

    class Meta:
        app_label = "django_async_manager"

    def __str__(self):
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month_of_year} {self.day_of_week}"

    def get_next_run_time(self, base_time=None):
        if base_time is None:
            base_time = now()
        from croniter import croniter

        schedule = f"{self.minute} {self.hour} {self.day_of_month} {self.month_of_year} {self.day_of_week}"
        iter = croniter(schedule, base_time)
        return iter.get_next(datetime.datetime)


class PeriodicTask(models.Model):
    name = models.CharField(
        max_length=255, unique=True, help_text="Unique name for the periodic task."
    )
    task_name = models.CharField(
        max_length=255, help_text="Name of the registered task function to be executed."
    )
    arguments = models.JSONField(
        default=list, help_text="List of positional arguments for the task."
    )
    kwargs = models.JSONField(
        default=dict, help_text="Dictionary of keyword arguments for the task."
    )
    crontab = models.ForeignKey(
        CrontabSchedule, on_delete=models.CASCADE, related_name="periodic_tasks"
    )
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    total_run_count = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "django_async_manager"

    def get_next_run_at(self):
        if self.last_run_at:
            base_time = self.last_run_at
        else:
            base_time = now() - datetime.timedelta(microseconds=1)
        return self.crontab.get_next_run_time(base_time)

    def __str__(self):
        return self.name
