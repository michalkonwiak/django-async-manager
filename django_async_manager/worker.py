import logging
import importlib
import multiprocessing
import threading
import time
import traceback
import psutil
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, TimeoutError

from django.db import transaction
from django.db.models import Q, Count, F
from django.utils.timezone import now
from django_async_manager.models import Task, TASK_REGISTRY

logger = logging.getLogger("django_async_manager.worker")


class TimeoutException(Exception):
    """Raised when a task exceeds its allowed execution time."""

    pass


class MemoryLimitExceeded(Exception):
    """Raised when a task exceeds its allowed memory limit."""

    pass


def _execute_task_in_process(func_path, args, kwargs, memory_limit=None):
    """
    Helper function executed IN THE CHILD PROCESS.
    Imports the module, finds the original function, and executes it.
    Also monitors memory usage if a limit is set.
    """
    try:
        from django import db

        db.connections.close_all()

        memory_exceeded = False
        memory_usage = 0.0

        if memory_limit is not None:
            process = psutil.Process()
            memory_check_interval = 0.5
            stop_monitoring = threading.Event()

            def monitor_memory():
                nonlocal memory_exceeded, memory_usage
                while not stop_monitoring.is_set():
                    current_memory = process.memory_info().rss / (1024 * 1024)
                    memory_usage = current_memory

                    if current_memory > memory_limit:
                        logger.warning(
                            f"Task {func_path} exceeded memory limit of {memory_limit} MB (used {current_memory:.2f} MB)"
                        )
                        memory_exceeded = True
                        stop_monitoring.set()
                        return

                    time.sleep(memory_check_interval)

            monitor_thread = threading.Thread(target=monitor_memory)
            monitor_thread.daemon = True
            monitor_thread.start()

        module_name, func_name = func_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        target_func_or_decorator = getattr(module, func_name)

        if hasattr(target_func_or_decorator, "__wrapped__"):
            func_to_run = target_func_or_decorator.__wrapped__
        else:
            func_to_run = target_func_or_decorator
            logger.warning(
                f"Running function {func_path} which might not be decorated as expected."
            )

        if func_to_run is None or not callable(func_to_run):
            error_msg = f"Function {func_path} is not callable"
            logger.error(error_msg)
            raise TypeError(error_msg)

        result = func_to_run(*args, **kwargs)

        if memory_limit is not None:
            stop_monitoring.set()
            if hasattr(monitor_thread, "join"):
                monitor_thread.join(timeout=1.0)

            if memory_exceeded:
                raise MemoryLimitExceeded(
                    f"Task {func_path} exceeded memory limit of {memory_limit} MB (used {memory_usage:.2f} MB)"
                )

        return result
    except Exception as e:
        logger.debug(f"Exception in child process for {func_path}: {e}", exc_info=True)
        raise e


def execute_task(
    func_path: str,
    args,
    kwargs,
    timeout: int,
    use_threads=False,
    memory_limit=None,
    executor=None,
):
    """
    Submits the task execution (defined by func_path) to either a ThreadPoolExecutor or ProcessPoolExecutor.
    Handles timeouts and exceptions from the child process.

    Args:
        func_path: The import path to the function to execute
        args: Positional arguments to pass to the function
        kwargs: Keyword arguments to pass to the function
        timeout: Maximum execution time in seconds
        use_threads: If True, use ThreadPoolExecutor, otherwise use ProcessPoolExecutor
        memory_limit: Maximum memory usage in MB (None for no limit)
        executor: An existing executor to use (if None, a new one will be created)
    """
    try:
        module_name, func_name = func_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        if not hasattr(module, func_name):
            raise AttributeError(
                f"Function {func_name} not found in module {module_name}"
            )

        func = getattr(module, func_name)
        if func is None or not callable(func):
            raise TypeError(
                f"Function {func_name} in module {module_name} is not callable"
            )
    except (ValueError, ImportError, AttributeError, TypeError) as e:
        logger.error(
            f"Invalid function path or function not found: {func_path}. Error: {e}"
        )
        raise ValueError(
            f"Invalid function path or function not found: {func_path}. Error: {e}"
        )

    if executor is None:
        executor_class = ThreadPoolExecutor if use_threads else ProcessPoolExecutor
        executor_context = executor_class(max_workers=1)
        executor = executor_context.__enter__()
        should_exit_context = True
    else:
        executor_context = None
        should_exit_context = False

    try:
        # For thread-based execution, memory limits are not supported
        # For process-based execution, memory limits are monitored in the child process
        if use_threads:
            if memory_limit is not None:
                logger.warning(
                    f"Memory limit of {memory_limit} MB specified for task {func_path} but memory limits are not supported with threads. "
                    f"The limit will be ignored. Use processes (use_threads=False) for memory limiting."
                )
            future = executor.submit(_execute_task_in_process, func_path, args, kwargs)
        else:
            future = executor.submit(
                _execute_task_in_process, func_path, args, kwargs, memory_limit
            )

        try:
            start_time = time.time()
            result = future.result(timeout=timeout)

            execution_time = time.time() - start_time
            logger.debug(f"Task {func_path} completed in {execution_time:.2f} seconds")
            return result
        except TimeoutError:
            execution_time = time.time() - start_time
            logger.warning(
                f"Task {func_path} exceeded timeout of {timeout} seconds (ran for {execution_time:.2f} seconds)"
            )
            raise TimeoutException(
                f"Task {func_path} exceeded timeout of {timeout} seconds (ran for {execution_time:.2f} seconds)"
            )
        except MemoryLimitExceeded as e:
            raise e
        except Exception as e:
            logger.error(f"Task {func_path} failed with exception: {e}")
            raise e
    finally:
        if should_exit_context and executor_context is not None:
            executor_context.__exit__(None, None, None)


class TaskWorker:
    """Worker for fetching and executing tasks"""

    def __init__(
        self, worker_id: str, queue: str = "default", use_threads=True, max_workers=1
    ):
        self.worker_id = worker_id
        self.queue = queue
        self.use_threads = use_threads
        self.max_workers = max_workers

        executor_class = ThreadPoolExecutor if self.use_threads else ProcessPoolExecutor
        self.executor = executor_class(max_workers=self.max_workers)

    def process_task(self) -> None:
        from django_async_manager.utils import with_database_lock_handling

        task = None

        @with_database_lock_handling(
            max_retries=3, logger_name="django_async_manager.worker"
        )
        def _acquire_task():
            nonlocal task
            with transaction.atomic():
                task_qs = (
                    Task.objects.filter(status="pending", queue=self.queue)
                    .annotate(
                        total_dependencies=Count("dependencies"),
                        completed_dependencies=Count(
                            "dependencies",
                            filter=Q(dependencies__status="completed"),
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
                    return False

                if not task.worker_id:
                    task.worker_id = self.worker_id

                task.status = "in_progress"
                task.started_at = now()
                task.attempts = F("attempts") + 1
                task.save(
                    update_fields=["status", "started_at", "worker_id", "attempts"]
                )
                return True

        if not _acquire_task():
            return

        if not task:
            logger.debug("No task acquired after lock attempts.")
            return

        try:
            task.refresh_from_db()
        except Task.DoesNotExist:
            logger.warning(f"Task {task.id} disappeared before execution could start.")
            return

        try:
            if "." in task.name:
                func_path = task.name
            else:
                func_path = TASK_REGISTRY.get(task.name)

            if not func_path:
                error_msg = f"Task function '{task.name}' has not been registered."
                logger.error(error_msg)
                task.mark_as_failed(error_msg)
                return

            if "." not in func_path:
                error_msg = f"Invalid function path format: {func_path}"
                logger.error(error_msg)
                task.mark_as_failed(error_msg)
                return

            args = task.arguments.get("args", [])
            kwargs = task.arguments.get("kwargs", {})

            execute_task(
                func_path,
                args,
                kwargs,
                task.timeout,
                use_threads=self.use_threads,
                memory_limit=task.memory_limit,
                executor=self.executor,
            )

            task.mark_as_completed()
            logger.info(f"Task {task.id} ({task.name}) completed successfully.")

        except (TimeoutException, MemoryLimitExceeded) as e:
            error_type = (
                "TimeoutException"
                if isinstance(e, TimeoutException)
                else "MemoryLimitExceeded"
            )
            logger.warning(
                f"{error_type}: Task {task.id} ({task.name}) exceeded {'time' if isinstance(e, TimeoutException) else 'memory'} limit."
            )
            task.refresh_from_db()
            if task.autoretry and task.can_retry():
                logger.info(
                    f"Scheduling retry for task {task.id} that exceeded {'time' if isinstance(e, TimeoutException) else 'memory'} limit"
                )
                error_details = traceback.format_exc()
                logger.error(
                    f"Scheduling retry for task {task.id}. Error:\n{error_details}"
                )
                task.schedule_retry(error_details)
            else:
                logger.error(
                    f"Marking task {task.id} as failed (no retries left or autoretry=False)."
                )
                error_details = traceback.format_exc()
                logger.error(
                    f"Marking task {task.id} as failed. Error:\n{error_details}"
                )
                task.mark_as_failed(error_details)
        except Exception as e:
            logger.exception(
                f"Exception during task execution {task.id} ({task.name}): {e}"
            )
            try:
                task.refresh_from_db()
                if task.autoretry and task.can_retry():
                    logger.info(f"Scheduling retry for failed task {task.id}")
                    error_details = traceback.format_exc()
                    logger.error(
                        f"Scheduling retry for failed task {task.id}. Error:\n{error_details}"
                    )
                    task.schedule_retry(error_details)
                else:
                    error_details = traceback.format_exc()
                    logger.error(
                        f"Marking task {task.id} as failed (no retries left or autoretry=False). Error:\n{error_details}"
                    )
                    task.mark_as_failed(error_details)
            except Task.DoesNotExist:
                logger.error(
                    f"Task {task.id} disappeared after failing, cannot update status."
                )
            except Exception as update_err:
                logger.error(
                    f"Failed to update status for failed task {task.id}. Error: {update_err}",
                    exc_info=True,
                )

    def shutdown(self) -> None:
        """Shutdown the worker and clean up resources."""
        logger.info(f"Shutting down worker {self.worker_id}")
        if hasattr(self, "executor") and self.executor is not None:
            self.executor.shutdown(wait=True)
            self.executor = None

    def run(self) -> None:
        """Continuous processing of tasks."""
        try:
            while True:
                try:
                    self.process_task()
                except Exception:
                    logger.exception(
                        f"Worker {self.worker_id} encountered critical error in process_task loop. Restarting loop."
                    )
                time.sleep(2)
        finally:
            # Ensure executor is shut down properly
            self.shutdown()


class WorkerManager:
    """
    Manages multiple workers, supporting both threading and multiprocessing for the manager loop.

    The concurrency model works as follows:
    1. WorkerManager creates multiple TaskWorker instances (either in threads or processes)
    2. Each TaskWorker has its own executor (ThreadPoolExecutor or ProcessPoolExecutor)
    3. The executor is used to run individual tasks

    This allows for two levels of concurrency:
    - Level 1: Multiple TaskWorkers running in parallel (controlled by num_workers)
    - Level 2: Each TaskWorker can execute tasks using its executor (controlled by max_workers_per_task)
    """

    def __init__(
        self,
        num_workers=1,
        queue="default",
        use_processes=False,
        max_workers_per_task=1,
    ):
        """
        Initialize a WorkerManager.

        Args:
            num_workers: Number of worker instances to create
            queue: Queue name to process
            use_processes: If True, create workers as separate processes; if False, use threads
            max_workers_per_task: Number of workers in each TaskWorker's executor pool
        """
        self.num_workers = num_workers
        self.queue = queue
        self.use_processes = use_processes
        self.max_workers_per_task = max_workers_per_task
        self.workers = []

    def start_workers(self) -> None:
        """Start worker runners (either threads or processes)."""
        logger.info(
            f"Starting {self.num_workers} worker managers (each running TaskWorker loop) using "
            f"{'processes' if self.use_processes else 'threads'} for queue '{self.queue}'."
        )
        for i in range(self.num_workers):
            worker_id = f"worker-{self.queue}-{i + 1}"

            use_threads_for_tasks = self.use_processes

            worker_instance = TaskWorker(
                worker_id=worker_id,
                queue=self.queue,
                use_threads=use_threads_for_tasks,
                max_workers=self.max_workers_per_task,
            )

            if not self.use_processes:
                thread = threading.Thread(
                    target=worker_instance.run, name=worker_id, daemon=True
                )
                thread.start()
                self.workers.append(thread)
                logger.info(f"Started worker {worker_id} in a new thread.")
            else:
                process = multiprocessing.Process(
                    target=worker_instance.run, name=worker_id
                )
                process.start()
                self.workers.append(process)
                logger.info(f"Started worker {worker_id} in a new process.")

    def join_workers(self) -> None:
        """Wait for all worker runners (threads or processes) to complete."""
        logger.info(f"Waiting for {len(self.workers)} worker managers to finish...")
        for worker_runner in self.workers:
            worker_runner.join()
        logger.info("All worker managers have finished.")
