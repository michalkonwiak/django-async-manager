import time
import logging
from datetime import timedelta
from django.utils.timezone import now
from task_queue.models import PeriodicTask, Task

logger = logging.getLogger("task_scheduler")


class BeatScheduler:
    def __init__(self):
        self._schedule = {}
        self.update_schedule()

    def update_schedule(self):
        """Refresh the schedule from the database with active periodic tasks."""
        periodic_tasks = PeriodicTask.objects.filter(enabled=True)
        for pt in periodic_tasks:
            next_run = pt.get_next_run_at()
            self._schedule[pt.id] = {"task": pt, "next_run": next_run}
            logger.debug("Scheduled task %s, next run at %s", pt.name, next_run)

    def sync_schedule(self):
        """Synchronize the schedule – update schedule entries."""
        self.update_schedule()

    def tick(self):
        """Check which tasks are due and update their schedule."""
        current_time = now()
        due_tasks = []
        next_times = []
        for sched in self._schedule.values():
            pt = sched["task"]
            next_run = sched["next_run"]
            if next_run <= current_time:
                due_tasks.append(pt)
                pt.last_run_at = current_time
                pt.total_run_count += 1
                pt.save()
                new_next_run = pt.get_next_run_at()
                sched["next_run"] = new_next_run
            next_times.append(sched["next_run"])
        if next_times:
            next_due = min(next_times)
        else:
            next_due = current_time + timedelta(seconds=30)
        return next_due, due_tasks


def run_scheduler_loop():
    scheduler = BeatScheduler()
    while True:
        scheduler.sync_schedule()
        next_due, due_tasks = scheduler.tick()
        for pt in due_tasks:
            Task.objects.create(
                name=pt.task_name,
                arguments={"args": pt.arguments, "kwargs": pt.kwargs},
                status="pending",
                timeout=300,
            )
            logger.info("Enqueued periodic task: %s", pt.name)
        sleep_duration = max(0, (next_due - now()).total_seconds())
        time.sleep(sleep_duration)
