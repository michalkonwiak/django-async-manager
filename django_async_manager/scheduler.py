import time
import logging
from datetime import timedelta
from django.utils.timezone import now
from django.db.models import F
from django_async_manager.models import PeriodicTask, Task

logger = logging.getLogger("django_async_manager.scheduler")


class BeatScheduler:
    def __init__(self, default_interval=30):
        self._schedule = {}
        self.default_interval = default_interval
        self.update_schedule()

    def update_schedule(self):
        """Refresh the schedule from the database with active periodic tasks."""
        logger.debug("Updating schedule from database...")
        active_tasks = {}
        periodic_tasks = PeriodicTask.objects.filter(enabled=True)
        for pt in periodic_tasks:
            try:
                pt.refresh_from_db(fields=["last_run_at"])
                next_run = pt.get_next_run_at()
                active_tasks[pt.id] = {"task": pt, "next_run": next_run}
                logger.debug(
                    "Scheduled task %s (ID: %s), next run at %s (based on last_run_at: %s)",
                    pt.name,
                    pt.id,
                    next_run,
                    pt.last_run_at,
                )
            except Exception as e:
                logger.error(
                    f"Failed to calculate next run time for task {pt.name} (ID: {pt.id}): {e}",
                    exc_info=True,
                )

        self._schedule = active_tasks
        logger.debug("Schedule update complete.")

    def sync_schedule(self):
        """Synchronize the schedule – update schedule entries."""
        self.update_schedule()

    def tick(self):
        """
        Check which tasks are due based on the internal schedule.
        Returns the time of the next scheduled event and a list of tasks due now.
        IMPORTANT: This method DOES NOT save changes to PeriodicTask back to the DB.
                   It only updates the internal _schedule's next_run time.
        """
        current_time = now()
        due_tasks_info = []
        next_times = []

        logger.debug(f"Tick started at {current_time.isoformat()}")

        schedule_items = list(self._schedule.items())

        for pk, sched in schedule_items:
            if pk not in self._schedule:
                logger.warning(
                    f"Task ID {pk} vanished from schedule during tick. Skipping."
                )
                continue

            pt = sched["task"]
            next_run = sched["next_run"]

            logger.debug(f"  Checking task {pt.id} ({pt.name})...")
            logger.debug(f"    current_time: {current_time.isoformat()}")
            logger.debug(f"    next_run:     {next_run.isoformat()}")

            grace_period = timedelta(seconds=1)
            if next_run <= (current_time + grace_period):
                logger.info(
                    f"  Task {pt.id} ({pt.name}) is DUE (next_run: {next_run}, current_time: {current_time})."
                )
                due_tasks_info.append({"task": pt, "run_time": current_time})

                try:
                    base_time_for_next_calc = current_time
                    new_next_run = pt.crontab.get_next_run_time(
                        base_time=base_time_for_next_calc
                    )

                    if pk in self._schedule:
                        self._schedule[pk]["next_run"] = new_next_run
                        logger.debug(
                            f"    Calculated new next run for {pt.name}: {new_next_run}"
                        )
                        next_times.append(new_next_run)
                    else:
                        logger.warning(
                            f"Task ID {pk} vanished before its next run could be updated in memory."
                        )

                except Exception as e:
                    logger.error(
                        f"    Error calculating next run time for {pt.name}: {e}",
                        exc_info=True,
                    )
                    if pk in self._schedule:
                        next_times.append(self._schedule[pk]["next_run"])

            else:
                logger.debug(f"  Task {pt.id} ({pt.name}) is NOT due yet.")
                next_times.append(next_run)

        if next_times:
            next_due = min(next_times)
        else:
            next_due = current_time + timedelta(seconds=self.default_interval)

        logger.debug(
            f"Tick finished. Next check due around: {next_due}. Tasks due now: {len(due_tasks_info)}"
        )
        return next_due, due_tasks_info


def run_scheduler_loop(default_interval=30):
    """Main loop for the scheduler process."""
    logger.info("Starting scheduler loop...")
    scheduler = BeatScheduler(default_interval=default_interval)
    while True:
        try:
            scheduler.sync_schedule()

            next_due, due_tasks_info = scheduler.tick()

            tasks_processed_this_tick = 0
            for task_info in due_tasks_info:
                pt = task_info["task"]
                run_time = task_info["run_time"]

                try:
                    Task.objects.create(
                        name=pt.task_name,
                        arguments={"args": pt.arguments, "kwargs": pt.kwargs},
                        status="pending",
                    )
                    logger.info("Enqueued periodic task: %s (ID: %s)", pt.name, pt.id)
                    tasks_processed_this_tick += 1

                    try:
                        PeriodicTask.objects.filter(pk=pt.pk).update(
                            last_run_at=run_time,
                            total_run_count=F("total_run_count") + 1,
                        )
                        logger.debug(
                            f"Successfully updated last_run_at for PeriodicTask {pt.name} (ID: {pt.id})"
                        )
                    except Exception as update_err:
                        logger.error(
                            f"Failed to update PeriodicTask {pt.name} (ID: {pt.id}) after enqueue: {update_err}",
                            exc_info=True,
                        )

                except Exception as e:
                    logger.error(
                        f"Failed to enqueue task for {pt.name} (ID: {pt.id}): {e}",
                        exc_info=True,
                    )

            current_time_before_sleep = now()
            sleep_duration = max(
                0, (next_due - current_time_before_sleep).total_seconds()
            )

            sleep_duration = max(sleep_duration, 0.1)

            sleep_duration = min(sleep_duration, default_interval)

            logger.debug(
                f"Scheduler sleeping for {sleep_duration:.2f} seconds (next check around {next_due})..."
            )
            time.sleep(sleep_duration)

        except KeyboardInterrupt:
            logger.info("Scheduler loop interrupted by user. Exiting.")
            raise
        except Exception as loop_err:
            logger.exception(
                f"Critical error in scheduler loop: {loop_err}. Restarting loop after 10 seconds."
            )
            time.sleep(10)
