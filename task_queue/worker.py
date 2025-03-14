import logging
import multiprocessing
import threading
import time
from django.utils.timezone import now
from task_queue.models import Task

logger = logging.getLogger("task_worker")


class TaskWorker:
    """Worker for fetching and executing tasks"""

    def __init__(self, use_threads=True):
        self.use_threads = use_threads

    def process_task(self):
        """Fetch and execute a single task."""
        task = Task.objects.filter(status="pending").order_by("-priority").first()
        if not task:
            return

        # Locking
        task.status = "in_progress"
        task.started_at = now()
        task.save()

        try:
            func = globals().get(task.name)
            if func:
                args = task.arguments.get("args", [])
                kwargs = task.arguments.get("kwargs", {})
                func(*args, **kwargs)

            task.mark_as_completed()
        except Exception as e:
            task.mark_as_failed(str(e))

    def run(self):
        """Continuous processing of tasks."""
        logger.info(
            "Worker started using %s", "threads" if self.use_threads else "processes"
        )
        while True:
            self.process_task()
            time.sleep(2)


class WorkerManager:
    """Manages multiple workers, supporting both multiprocessing and threading."""

    def __init__(self, num_workers=1, use_threads=True):
        self.num_workers = num_workers
        self.use_threads = use_threads
        self.workers = []

    def start_workers(self):
        """Start worker processes or threads."""
        logger.info(
            f"Starting {self.num_workers} {'thread' if self.use_threads else 'process'} workers"
        )
        for i in range(self.num_workers):
            worker = TaskWorker(use_threads=self.use_threads)
            if self.use_threads:
                thread = threading.Thread(target=worker.run, daemon=True)
                thread.start()
                self.workers.append(thread)
            else:
                process = multiprocessing.Process(target=worker.run)
                process.start()
                self.workers.append(process)

    def join_workers(self):
        """Wait for all workers to complete."""
        for worker in self.workers:
            worker.join()
