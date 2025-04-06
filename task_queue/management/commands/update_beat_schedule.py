import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from task_queue.models import CrontabSchedule, PeriodicTask

logger = logging.getLogger("task_scheduler")


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
                minute=schedule_config.get("minute", "*"),
                hour=schedule_config.get("hour", "*"),
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
