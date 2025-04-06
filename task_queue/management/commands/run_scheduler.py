import logging
from django.core.management.base import BaseCommand
from task_queue.scheduler import run_scheduler_loop

logger = logging.getLogger("task_scheduler")


class Command(BaseCommand):
    help = "Run the periodic task scheduler"

    def add_arguments(self, parser):
        parser.add_argument(
            "--default-interval",
            type=int,
            default=30,
            help="Default interval (in seconds) to refresh the schedule when no tasks are in queue.",
        )

    def handle(self, *args, **options):
        default_interval = options["default_interval"]
        logger.info(
            "Starting scheduler with default interval %s seconds...", default_interval
        )
        run_scheduler_loop()
