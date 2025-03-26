import uuid
from typing import Dict, Callable, Any, List

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

    class Meta:
        ordering = ["priority", "created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
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
        """Mark error and increment attempt counter"""
        self.attempts += 1
        if len(self.last_errors) >= 5:
            self.last_errors.pop(0)
        self.last_errors.append(error_message)
        if self.attempts >= self.max_retries:
            self.status = "failed"
        self.save()

    def mark_as_completed(self):
        """Mark task as completed and update timestamps"""
        self.status = "completed"
        self.completed_at = now()
        self.save()

    def can_retry(self):
        """Check if task can be retried"""
        return self.attempts < self.max_retries

    def _has_cycle(self, visited: List["Task"] = None) -> bool:
        """A recursive method to check cycles in dependencies"""
        if visited is None:
            visited = []
        if self in visited:
            return True
        visited.append(self)
        for dep in self.dependencies.all():
            if dep._has_cycle(visited):
                return True
        visited.pop()
        return False
