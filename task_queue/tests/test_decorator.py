from django.test import TestCase
from task_queue.decorators import background_task
from task_queue.models import Task


class BackgroundTaskDecoratorTests(TestCase):
    def test_task_registration(self):
        """Test if a function decorated with @background_task registers a Task."""

        @background_task()
        def dummy_task(x, y):
            return x + y

        task = dummy_task.run_async(2, 3)
        self.assertIsInstance(task, Task)
        self.assertEqual(task.status, "pending")
        args = task.arguments.get("args")
        self.assertEqual(list(args) if isinstance(args, tuple) else args, [2, 3])
        self.assertEqual(task.arguments.get("kwargs"), {})

    def test_task_dependency_registration(self):
        """Test that task registered with a dependency is correctly linked."""

        @background_task()
        def parent_task(x):
            return x

        parent = parent_task.run_async(10)
        self.assertIsInstance(parent, Task)
        self.assertEqual(parent.status, "pending")

        @background_task(dependencies=parent)
        def child_task(y):
            return y

        child = child_task.run_async(20)
        self.assertIsInstance(child, Task)
        self.assertIn(parent, list(child.dependencies.all()))
        self.assertFalse(child.is_ready)

        parent.mark_as_completed()
        child.refresh_from_db()
        self.assertTrue(child.is_ready)

    def test_is_ready_property_without_parent(self):
        """Test that a standalone task is always marked as ready."""
        task = Task.objects.create(
            name="standalone_task",
            arguments={"args": [], "kwargs": {}},
            status="pending",
        )
        self.assertTrue(task.is_ready)

    def test_autoretry_configuration(self):
        """Test that a task registered with custom autoretry parameters is created with expected settings."""

        @background_task(
            autoretry=False, retry_delay=30, retry_backoff=3.0, max_retries=5
        )
        def autoretry_task(x):
            return x

        task = autoretry_task.run_async(42)
        self.assertFalse(task.autoretry)
        self.assertEqual(task.retry_delay, 30)
        self.assertEqual(task.retry_backoff, 3.0)
        self.assertEqual(task.max_retries, 5)

    def test_default_autoretry_configuration(self):
        """Test that default autoretry settings are applied if none are provided."""

        @background_task()
        def default_task(x):
            return x

        task = default_task.run_async(99)
        self.assertTrue(task.autoretry)
        self.assertEqual(task.retry_delay, 60)
        self.assertEqual(task.retry_backoff, 2.0)
        self.assertEqual(task.max_retries, 1)

    def test_timeout_value_set_by_decorator(self):
        """Test that the timeout parameter provided in the decorator is correctly set on the task."""

        @background_task(timeout=600)
        def task_with_timeout():
            return "done"

        task = task_with_timeout.run_async()
        self.assertEqual(task.timeout, 600)
