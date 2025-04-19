from django.test import TestCase
from django.utils.timezone import now, timedelta

from django_async_manager.models import Task
from django_async_manager.tests.factories import TaskFactory


class TestTask(TestCase):
    def setUp(self):
        """Set up common test data for Task model tests."""
        self.task = TaskFactory.create(
            status="pending",
            priority=Task.PRIORITY_MAPPING["medium"],
            arguments={"key": "value"},
        )

    def test_task_creation(self):
        """Test task creation using the factory."""
        self.assertIsInstance(self.task, Task)
        self.assertEqual(self.task.status, "pending")
        self.assertEqual(self.task.priority, Task.PRIORITY_MAPPING["medium"])
        self.assertEqual(self.task.arguments, {"key": "value"})
        self.assertIsNotNone(self.task.id)

    def test_default_values(self):
        """Test default values assigned by the factory."""
        self.assertEqual(self.task.attempts, 0)
        self.assertEqual(self.task.last_errors, [])
        self.assertFalse(self.task.archived)

    def test_schedule_retry(self):
        """Test scheduling a retry with exponential backoff."""
        initial_attempts = self.task.attempts
        self.task.schedule_retry("Retry error")
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempts, initial_attempts + 1)
        self.assertIn("Retry error", self.task.last_errors)
        if self.task.attempts < self.task.max_retries:
            self.assertEqual(self.task.status, "pending")
            self.assertTrue(self.task.scheduled_at > now())
        else:
            self.assertEqual(self.task.status, "failed")

    def test_mark_as_completed(self):
        """Test marking task as completed."""
        self.task.mark_as_completed()
        self.assertEqual(self.task.status, "completed")
        self.assertIsNotNone(self.task.completed_at)

    def test_can_retry(self):
        """Test retry logic."""
        self.assertTrue(self.task.can_retry())
        self.task.attempts = self.task.max_retries
        self.assertFalse(self.task.can_retry())

    def test_scheduled_task(self):
        """Test if a task is scheduled for a future time."""
        future_task = TaskFactory.create(scheduled_at=now() + timedelta(hours=3))
        self.assertTrue(future_task.scheduled_at > now())

    def test_task_ordering(self):
        """Test priority-based task ordering."""
        TaskFactory.from_string_priority(priority="high")
        TaskFactory.from_string_priority(priority="low")
        TaskFactory.from_string_priority(priority="critical")

        tasks = Task.objects.order_by("-priority")
        self.assertEqual(tasks[0].priority, Task.PRIORITY_MAPPING["critical"])
        self.assertEqual(tasks[1].priority, Task.PRIORITY_MAPPING["high"])
        self.assertEqual(tasks[2].priority, Task.PRIORITY_MAPPING["medium"])
        self.assertEqual(tasks[3].priority, Task.PRIORITY_MAPPING["low"])

    def test_foreign_key_dependency(self):
        """Test parent-child task relationships."""
        parent_task = TaskFactory.create(name="Parent Task")
        child_task = TaskFactory.create(name="Child Task")
        child_task.dependencies.add(parent_task)

        self.assertEqual(child_task.dependencies.count(), 1)
        self.assertIn(parent_task, child_task.dependencies.all())
        self.assertEqual(parent_task.dependent_tasks.count(), 1)
        self.assertEqual(parent_task.dependent_tasks.first(), child_task)

    def test_task_archiving(self):
        """Test task archiving functionality."""
        self.task.archived = True
        self.task.save()
        self.assertTrue(Task.objects.get(id=self.task.id).archived)

    def test_indexing(self):
        """Test model indexes."""
        indexes = [index.fields for index in Task._meta.indexes]
        self.assertIn(["status"], indexes)
        self.assertIn(["priority"], indexes)

    def test_str_representation(self):
        """Test __str__ representation of the Task model."""
        self.assertEqual(
            str(self.task),
            f"{self.task.name} ({self.task.status}) - Priority: {self.task.priority}",
        )
