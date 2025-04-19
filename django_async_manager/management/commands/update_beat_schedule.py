import logging
import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from django_async_manager.models import CrontabSchedule, PeriodicTask

logger = logging.getLogger("django_async_manager.scheduler")

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False


class Command(BaseCommand):
    help = (
        "Update periodic tasks from BEAT_SCHEDULE configuration defined in settings.py"
    )

    def handle(self, *args, **options):
        beat_schedule = getattr(settings, "BEAT_SCHEDULE", {})
        if not beat_schedule:
            self.stdout.write(self.style.WARNING("No BEAT_SCHEDULE found in settings."))
            return

        for name, config in beat_schedule.items():
            schedule_config = config["schedule"]
            crontab, _ = CrontabSchedule.objects.get_or_create(
                hour=schedule_config.get("hour", "*"),
                minute=schedule_config.get("minute", "*"),
                day_of_week=schedule_config.get("day_of_week", "*"),
                day_of_month=schedule_config.get("day_of_month", "*"),
                month_of_year=schedule_config.get("month_of_year", "*"),
            )
            periodic_task, _ = PeriodicTask.objects.update_or_create(
                name=name,
                defaults={
                    "task_name": config["task"],
                    "arguments": config.get("args", []),
                    "kwargs": config.get("kwargs", {}),
                    "crontab": crontab,
                    "enabled": True,
                },
            )
            self.stdout.write(self.style.SUCCESS(f"Updated periodic task: {name}"))
            logger.info("Updated periodic task %s with schedule %s", name, crontab)
