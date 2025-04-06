import logging
import multiprocessing
import threading
import time
from concurrent.futures import ProcessPoolExecutor

from django.db import transaction
from django.db.models import Q, Count, F
from django.utils.timezone import now
from task_queue.models import Task, TASK_REGISTRY

logger = logging.getLogger("task_worker")


class TimeoutException(Exception):
    """Raised when a task exceeds its allowed execution time."""

    pass


def execute_task(func, args, kwargs, timeout):
    """
    Execute a function in a separate process using a ProcessPoolExecutor with a given timeout.

    Uses the per-task timeout value passed from the Task instance.
    """
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise TimeoutException(f"Task exceeded timeout of {timeout} seconds")


class TaskWorker:
    """Worker for fetching and executing tasks"""

    def __init__(self, worker_id: str, use_threads=True):
        self.worker_id = worker_id
        self.use_threads = use_threads

    def process_task(self) -> None:
        try:
            with transaction.atomic():
                task_qs = (
                    Task.objects.filter(status="pending")
                    .annotate(
                        total_dependencies=Count("dependencies"),
                        completed_dependencies=Count(
                            "dependencies", filter=Q(dependencies__status="completed")
                        ),
                    )
                    .filter(
                        Q(total_dependencies=0)
                        | Q(total_dependencies=F("completed_dependencies"))
                    )
                    .filter(Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=now()))
                    .order_by("-priority", "created_at")
                )

                task = task_qs.select_for_update(skip_locked=True).first()
                if not task:
                    return

                if not task.worker_id:
                    task.worker_id = str(task.id)
                task.status = "in_progress"
                task.started_at = now()
                task.save()
        except Exception:
            logger.exception("Error during processing task")
            return

        task.refresh_from_db()

        try:
            func = TASK_REGISTRY.get(task.name)
            if not func:
                error_msg = f"Task function '{task.name}' has not been registered."
                logger.error(error_msg)
                task.mark_as_failed(error_msg)
                return

            args = task.arguments.get("args", [])
            kwargs = task.arguments.get("kwargs", {})
            execute_task(func, args, kwargs, task.timeout)
            task.mark_as_completed()
        except TimeoutException as te:
            logger.exception(f"Timeout: Task {task.id} exceeded time limit.")
            if task.autoretry and task.can_retry():
                task.schedule_retry(str(te))
            else:
                task.mark_as_failed(str(te))
        except Exception as e:
            logger.exception(f"Error during task execution {task.id}: {e}")
            if task.autoretry and task.can_retry():
                task.schedule_retry(str(e))
            else:
                task.mark_as_failed(str(e))

    def run(self) -> None:
        """Continuous processing of tasks."""
        logger.info(
            "Worker %s started using %s",
            self.worker_id,
            "threads" if self.use_threads else "processes",
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

    def start_workers(self) -> None:
        """Start worker processes or threads."""
        logger.info(
            f"Starting {self.num_workers} {'thread' if self.use_threads else 'process'} workers"
        )
        for i in range(self.num_workers):
            worker_id = f"worker-{i + 1}"
            worker = TaskWorker(worker_id=worker_id, use_threads=self.use_threads)
            if self.use_threads:
                thread = threading.Thread(target=worker.run, daemon=True)
                thread.start()
                self.workers.append(thread)
            else:
                process = multiprocessing.Process(target=worker.run)
                process.start()
                self.workers.append(process)

    def join_workers(self) -> None:
        """Wait for all workers to complete."""
        for worker in self.workers:
            worker.join()
