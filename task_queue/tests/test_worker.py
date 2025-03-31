from django.test import TestCase
from django.utils.timezone import now
from task_queue.worker import TaskWorker, TASK_REGISTRY
from task_queue.models import Task


def dummy_task(*args, **kwargs):
    pass


class TaskWorkerTests(TestCase):
    def setUp(self):
        self.worker = TaskWorker()
        TASK_REGISTRY["test_task"] = dummy_task
        TASK_REGISTRY["low_priority"] = dummy_task
        TASK_REGISTRY["high_priority"] = dummy_task
        TASK_REGISTRY["timestamp_task"] = dummy_task
        TASK_REGISTRY["task1"] = dummy_task
        TASK_REGISTRY["task2"] = dummy_task

    def tearDown(self):
        TASK_REGISTRY.clear()

    def test_worker_processes_pending_task(self):
        """Test if worker picks up and executes a pending task"""
        task = Task.objects.create(
            name="test_task", status="pending", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")

    def test_worker_skips_failed_task(self):
        """Test if worker ignores already failed tasks"""
        task = Task.objects.create(
            name="test_task", status="failed", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")

    def test_worker_processes_highest_priority_task(self):
        """Test if worker picks the highest priority task first"""
        low_priority_task = Task.objects.create(
            name="low_priority",
            status="pending",
            priority=1,
            arguments={"args": [], "kwargs": {}},
        )
        high_priority_task = Task.objects.create(
            name="high_priority",
            status="pending",
            priority=10,
            arguments={"args": [], "kwargs": {}},
        )
        self.worker.process_task()
        high_priority_task.refresh_from_db()
        low_priority_task.refresh_from_db()
        self.assertEqual(high_priority_task.status, "completed")
        self.assertEqual(low_priority_task.status, "pending")

    def test_worker_does_not_process_in_progress_task(self):
        """Test if worker skips tasks that are already in progress"""
        task = Task.objects.create(
            name="test_task", status="in_progress", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")

    def test_worker_processes_multiple_tasks(self):
        """Test if worker processes multiple pending tasks sequentially"""
        task1 = Task.objects.create(
            name="task1", status="pending", arguments={"args": [], "kwargs": {}}
        )
        task2 = Task.objects.create(
            name="task2", status="pending", arguments={"args": [], "kwargs": {}}
        )
        self.worker.process_task()
        task1.refresh_from_db()
        task2.refresh_from_db()
        self.assertEqual(task1.status, "completed")
        self.assertEqual(task2.status, "pending")
        self.worker.process_task()
        task2.refresh_from_db()
        self.assertEqual(task2.status, "completed")

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
