from django.test import TestCase
from django.utils.timezone import now, timedelta
from unittest.mock import patch, MagicMock

from django_async_manager.decorators import background_task
from django_async_manager.models import Task
from django_async_manager.tests.factories import TaskFactory
from django_async_manager.worker import execute_task, TimeoutException


def dummy_task_function():
    return "ok"


def sample_function_for_execution(a, b):
    return a + b


class TestExecuteTask(TestCase):
    """Tests for the execute_task function."""

    @patch("django_async_manager.worker.ThreadPoolExecutor")
    @patch("django_async_manager.worker.ProcessPoolExecutor")
    def test_execute_task_with_threads(
        self, mock_process_executor, mock_thread_executor
    ):
        """Test that execute_task uses ThreadPoolExecutor when use_threads=True."""
        mock_future = MagicMock()
        mock_future.result.return_value = 5
        mock_thread_executor.return_value.__enter__.return_value.submit.return_value = (
            mock_future
        )

        result = execute_task(
            "django_async_manager.tests.test_worker.sample_function_for_execution",
            [2, 3],
            {},
            timeout=10,
            use_threads=True,
        )

        self.assertEqual(result, 5)
        mock_thread_executor.assert_called_once()
        mock_process_executor.assert_not_called()

    @patch("django_async_manager.worker.ThreadPoolExecutor")
    @patch("django_async_manager.worker.ProcessPoolExecutor")
    def test_execute_task_with_processes(
        self, mock_process_executor, mock_thread_executor
    ):
        """Test that execute_task uses ProcessPoolExecutor when use_threads=False."""
        mock_future = MagicMock()
        mock_future.result.return_value = 5
        mock_process_executor.return_value.__enter__.return_value.submit.return_value = mock_future

        result = execute_task(
            "django_async_manager.tests.test_worker.sample_function_for_execution",
            [2, 3],
            {},
            timeout=10,
            use_threads=False,
        )

        self.assertEqual(result, 5)
        mock_process_executor.assert_called_once()
        mock_thread_executor.assert_not_called()

    @patch("importlib.import_module")
    def test_function_existence_validation(self, mock_import_module):
        """Test that execute_task validates function existence before execution."""
        mock_module = MagicMock()
        mock_module.non_existent_function = None
        mock_import_module.return_value = mock_module

        with self.assertRaises(ValueError):
            execute_task("some_module.non_existent_function", [], {}, timeout=10)

    @patch("django_async_manager.worker.ProcessPoolExecutor")
    def test_timeout_handling(self, mock_executor):
        """Test that execute_task handles timeouts correctly."""
        from concurrent.futures import TimeoutError

        mock_future = MagicMock()
        mock_future.result.side_effect = TimeoutError()
        mock_executor.return_value.__enter__.return_value.submit.return_value = (
            mock_future
        )

        with self.assertRaises(TimeoutException) as context:
            execute_task(
                "django_async_manager.tests.test_worker.sample_function_for_execution",
                [2, 3],
                {},
                timeout=1,
            )

        self.assertIn("ran for", str(context.exception))


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

    def test_background_task_decorator_default_queue(self):
        """Test that the background_task decorator creates a task with the default queue."""

        @background_task()
        def dummy(x):
            return x

        task = dummy.run_async(5)
        self.assertEqual(task.queue, "default")

    def test_background_task_decorator_custom_queue(self):
        """Test that the background_task decorator creates a task with a custom queue."""

        @background_task(queue="config")
        def dummy_custom():
            return "ok"

        task = dummy_custom.run_async()
        self.assertEqual(task.queue, "config")
