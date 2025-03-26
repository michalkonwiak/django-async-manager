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
        """Test that a standalone task  is always marked as ready."""
        task = Task.objects.create(
            name="standalone_task",
            arguments={"args": [], "kwargs": {}},
            status="pending",
        )
        self.assertTrue(task.is_ready)
