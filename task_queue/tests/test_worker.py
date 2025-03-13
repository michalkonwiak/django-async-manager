from django.test import TestCase
from task_queue.worker import TaskWorker
from task_queue.models import Task


class TaskWorkerTests(TestCase):
    def setUp(self):
        self.worker = TaskWorker()

    def test_worker_processes_pending_task(self):
        """Test if worker picks up and executes a pending task"""
        task = Task.objects.create(name="test_task", status="pending", arguments={})

        self.worker.process_task()

        task.refresh_from_db()
        self.assertEqual(task.status, "completed")

    def test_worker_skips_failed_task(self):
        """Test if worker ignores already failed tasks"""
        task = Task.objects.create(name="test_task", status="failed", arguments={})

        self.worker.process_task()
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")
