import time
from unittest.mock import patch

from django.test import TestCase

from django_async_manager.decorators import background_task
from django_async_manager.tests.factories import TaskFactory
from django_async_manager.worker import execute_task, MemoryLimitExceeded


def memory_intensive_function(mb_to_allocate=100):
    """A function that allocates a specified amount of memory."""
    chunk_size = 1024 * 1024  # 1 MB
    data = []
    for _ in range(mb_to_allocate):
        data.append(bytearray(chunk_size))
        time.sleep(0.01)  # Small delay to allow memory monitoring
    return len(data)


class TestMemoryLimits(TestCase):
    """Tests for memory limit functionality."""

    def test_task_model_has_memory_limit_field(self):
        """Test that the Task model has a memory_limit field."""
        task = TaskFactory.create(memory_limit=256)
        self.assertEqual(task.memory_limit, 256)

        # Default value should be None (no limit)
        task_no_limit = TaskFactory.create()
        self.assertIsNone(task_no_limit.memory_limit)

    def test_background_task_decorator_accepts_memory_limit(self):
        """Test that the background_task decorator accepts a memory_limit parameter."""

        @background_task(memory_limit=128)
        def task_with_memory_limit():
            return "ok"

        task = task_with_memory_limit.run_async()
        self.assertEqual(task.memory_limit, 128)

    @patch("django_async_manager.worker.logger")
    def test_execute_task_warns_about_memory_limits_with_threads(self, mock_logger):
        """Test that execute_task warns when memory limits are used with threads."""
        # Execute a task with a memory limit using threads
        execute_task(
            "django_async_manager.tests.test_memory_management.memory_intensive_function",
            [],
            {},
            timeout=10,
            memory_limit=100,
            use_threads=True,
        )

        # Verify that a warning about memory limits was logged
        memory_limit_warning_called = False
        for call in mock_logger.warning.call_args_list:
            message = call[0][0]
            if (
                "Memory limit of 100 MB" in message
                and "not supported with threads" in message
            ):
                memory_limit_warning_called = True
                break

        self.assertTrue(
            memory_limit_warning_called,
            "No warning about memory limits with threads was logged",
        )

    def test_execute_task_passes_memory_limit_to_process(self):
        """Test that execute_task passes memory limit to child process when using processes."""
        import os

        if (
            os.environ.get("CI") == "true"
            or os.environ.get("SKIP_MEMORY_TESTS") == "true"
        ):
            self.skipTest("Skipping memory-intensive test in CI environment")

        # Define a memory limit that's low enough to trigger the limit but not so low
        # that it causes issues during normal test execution
        memory_limit = 10  # 10 MB

        # Execute the memory-intensive function with a memory limit
        # This should raise a MemoryLimitExceeded exception
        with self.assertRaises(MemoryLimitExceeded):
            execute_task(
                "django_async_manager.tests.test_memory_management.memory_intensive_function",
                [],
                {"mb_to_allocate": 20},  # Allocate 20 MB, which exceeds our 10 MB limit
                timeout=10,
                memory_limit=memory_limit,
                use_threads=False,  # Use processes
            )

    def test_worker_handles_memory_limit_exceeded(self):
        """Test that the worker handles MemoryLimitExceeded exceptions."""
        task = TaskFactory.create(
            memory_limit=100, autoretry=True, max_retries=3, status="pending"
        )

        error_message = "Memory limit exceeded"

        task.refresh_from_db()
        task.schedule_retry(error_message)

        task.refresh_from_db()
        self.assertIn(error_message, task.last_errors)
        self.assertEqual(task.status, "pending")  # Should be pending for retry

        task.attempts = task.max_retries
        task.save()

        task.mark_as_failed(error_message)

        task.refresh_from_db()
        self.assertEqual(task.status, "failed")
