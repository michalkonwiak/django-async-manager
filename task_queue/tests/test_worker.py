import time
from django.test import TestCase
from django.utils.timezone import now
from task_queue.worker import TaskWorker, TASK_REGISTRY
from task_queue.models import Task


def dummy_task(*args, **kwargs):
    return None


def low_priority_task(*args, **kwargs):
    return None


def high_priority_task(*args, **kwargs):
    return None


def timestamp_task(*args, **kwargs):
    return None


def task1_func(*args, **kwargs):
    return None


def task2_func(*args, **kwargs):
    return None


def long_running_task(*args, **kwargs):
    time.sleep(2)
    return "done"


class TaskWorkerTests(TestCase):
    def setUp(self):
        self.worker = TaskWorker()
        TASK_REGISTRY["test_task"] = dummy_task
        TASK_REGISTRY["low_priority"] = low_priority_task
        TASK_REGISTRY["high_priority"] = high_priority_task
        TASK_REGISTRY["timestamp_task"] = timestamp_task
        TASK_REGISTRY["task1"] = task1_func
        TASK_REGISTRY["task2"] = task2_func

    def tearDown(self):
        TASK_REGISTRY.clear()

    def test_worker_processes_pending_task(self):
        """Test if worker picks up and executes a pending task."""
        task = Task.objects.create(
            name="test_task", status="pending", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")

    def test_worker_skips_failed_task(self):
        """Test if worker ignores already failed tasks."""
        task = Task.objects.create(
            name="test_task", status="failed", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")

    def test_worker_processes_highest_priority_task(self):
        """Test if worker picks the highest priority task first."""
        low_priority_task_obj = Task.objects.create(
            name="low_priority",
            status="pending",
            priority=1,
            arguments={"args": [], "kwargs": {}},
        )
        high_priority_task_obj = Task.objects.create(
            name="high_priority",
            status="pending",
            priority=10,
            arguments={"args": [], "kwargs": {}},
        )
        self.worker.process_task()
        high_priority_task_obj.refresh_from_db()
        low_priority_task_obj.refresh_from_db()
        self.assertEqual(high_priority_task_obj.status, "completed")
        self.assertEqual(low_priority_task_obj.status, "pending")

    def test_worker_does_not_process_in_progress_task(self):
        """Test if worker skips tasks that are already in progress."""
        task = Task.objects.create(
            name="test_task", status="in_progress", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")

    def test_worker_processes_multiple_tasks(self):
        """Test if worker processes multiple pending tasks sequentially."""
        task1_obj = Task.objects.create(
            name="task1", status="pending", arguments={"args": [], "kwargs": {}}
        )
        task2_obj = Task.objects.create(
            name="task2", status="pending", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task1_obj.refresh_from_db()
        task2_obj.refresh_from_db()
        self.assertEqual(task1_obj.status, "completed")
        self.assertEqual(task2_obj.status, "pending")
        self.worker.process_task()
        task2_obj.refresh_from_db()
        self.assertEqual(task2_obj.status, "completed")

    def test_worker_updates_task_timestamp(self):
        """Test if worker updates the started_at timestamp before execution"""
        task = Task.objects.create(
            name="timestamp_task",
            status="pending",
            arguments={"args": [], "kwargs": {}},
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertIsNotNone(task.started_at)
        self.assertLessEqual(task.started_at, now())
        self.assertEqual(task.status, "completed")

    def test_worker_timeout_with_retry(self):
        """
        Test that a task exceeding its timeout with retry.
        """
        TASK_REGISTRY["timeout_task"] = long_running_task

        task = Task.objects.create(
            name="timeout_task",
            status="pending",
            arguments={"args": [], "kwargs": {}},
            timeout=1,
            max_retries=2,
            autoretry=True,
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.attempts, 1)
        self.assertIsNotNone(task.scheduled_at)
        self.assertIn("exceeded timeout", task.last_errors[-1])

    def test_worker_timeout_without_retry(self):
        """
        Test that a task exceeding its timeout without retry.
        """
        TASK_REGISTRY["timeout_task"] = long_running_task

        task = Task.objects.create(
            name="timeout_task",
            status="pending",
            arguments={"args": [], "kwargs": {}},
            timeout=1,
            max_retries=1,
            autoretry=True,
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.attempts, 1)
        self.assertIn("exceeded timeout", task.last_errors[-1])
