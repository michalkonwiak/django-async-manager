import logging
import sys
from django.core.management.base import BaseCommand
from django_async_manager.scheduler import run_scheduler_loop
from django_async_manager.worker import WorkerManager

logger = logging.getLogger("django_async_manager.scheduler")

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False


class Command(BaseCommand):
    help = "Run the scheduler and workers for periodic tasks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--default-interval",
            type=int,
            default=30,
            help="Default interval in seconds between scheduler ticks (default: 30)",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Starting scheduler and worker for periodic tasks...")
        )
        logger.info("Starting scheduler and workers for periodic tasks")

        worker_manager = WorkerManager(
            num_workers=1,
            queue="default",
            use_processes=False,
        )
        worker_manager.start_workers()

        default_interval = options.get("default_interval", 30)
        run_scheduler_loop(default_interval=default_interval)
