import logging
from django.core.management.base import BaseCommand
from task_queue.worker import WorkerManager

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
        parser.add_argument(
            "--processes",
            action="store_true",
            help="Use multiprocessing instead of threading.",
        )
        parser.add_argument(
            "--queue",
            type=str,
            default="default",
            help="Name of the queue that this worker listens to (default: 'default').",
        )

    def handle(self, *args, **options):
        num_workers = options["num_workers"]
        use_threads = not options["processes"]
        queue = options["queue"]

        logger.info(
            f"Starting {num_workers} {'thread' if use_threads else 'process'} workers on queue '{queue}'..."
        )

        manager = WorkerManager(
            num_workers=num_workers, queue=queue, use_threads=use_threads
        )
        manager.start_workers()
        manager.join_workers()
