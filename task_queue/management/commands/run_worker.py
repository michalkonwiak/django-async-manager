import logging
import multiprocessing
from django.core.management.base import BaseCommand
from task_queue.worker import TaskWorker

logger = logging.getLogger("task_worker")


class Command(BaseCommand):
    help = "Launch multiple workers for processing tasks in background"

    def add_arguments(self, parser):
        parser.add_argument(
            "--num-workers",
            type=int,
            default=1,
            help="Number of worker processes to start (default: 1)",
        )

    def handle(self, *args, **options):
        num_workers = options["num_workers"]
        logger.info(f"Starting {num_workers} worker(s)...")

        processes = []
        for i in range(num_workers):
            process = multiprocessing.Process(target=self.start_worker, args=(i,))
            process.start()
            processes.append(process)

        for process in processes:
            process.join()

    def start_worker(self, worker_id):
        """Run single worker"""
        logger.info(f"Worker {worker_id} started")
        worker = TaskWorker()
        worker.run()
