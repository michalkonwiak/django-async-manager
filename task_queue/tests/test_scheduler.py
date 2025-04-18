import datetime
from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now, utc
from unittest.mock import patch

from task_queue.models import Task
from task_queue.scheduler import BeatScheduler, run_scheduler_loop
from task_queue.tests.factories import PeriodicTaskFactory


class TestBeatScheduler(TestCase):
    def setUp(self):
        base_time = datetime.datetime(2025, 4, 6, 16, 0, 0, tzinfo=utc)
        self.periodic_task = PeriodicTaskFactory(
            name="Test Task",
            task_name="dummy_task",
            arguments=[1, 2],
            kwargs={"key": "value"},
            enabled=True,
            total_run_count=0,
        )
        self.periodic_task.crontab.minute = "2"
        self.periodic_task.crontab.hour = "16"
        self.periodic_task.crontab.day_of_month = "*"
        self.periodic_task.crontab.month_of_year = "*"
        self.periodic_task.crontab.day_of_week = "*"
        self.periodic_task.crontab.save()
        self.periodic_task.last_run_at = base_time
        self.periodic_task.save()
        self.scheduler = BeatScheduler()

    def tearDown(self):
        self.scheduler = None

    def test_update_schedule(self):
        """
        Test that update_schedule fetches active periodic tasks from the database
        and stores them in _schedule.
        """
        self.scheduler.update_schedule()
        self.assertIn(self.periodic_task.id, self.scheduler._schedule)
        sched_entry = self.scheduler._schedule[self.periodic_task.id]
        self.assertEqual(sched_entry["task"].id, self.periodic_task.id)
        self.assertIsInstance(sched_entry["next_run"], datetime.datetime)

    def test_sync_schedule(self):
        """
        After deactivating a task (enabled=False), the schedule should update.
        """
        self.scheduler.update_schedule()
        self.assertIn(self.periodic_task.id, self.scheduler._schedule)
        self.periodic_task.enabled = False
        self.periodic_task.save()
        self.scheduler._schedule.clear()
        self.scheduler.sync_schedule()
        self.assertNotIn(self.periodic_task.id, self.scheduler._schedule)
        self.periodic_task.enabled = True
        self.periodic_task.save()
        self.scheduler._schedule.clear()
        self.scheduler.sync_schedule()
        self.assertIn(self.periodic_task.id, self.scheduler._schedule)

    def test_tick(self):
        """
        Test the tick method:
          - If a task is due (next_run is less than current time),
            tick should update last_run_at, increment total_run_count,
            and compute a new next_run based on the new last_run_at.
        """
        fixed_now = datetime.datetime(2025, 4, 6, 16, 3, 0, tzinfo=utc)
        with patch("task_queue.scheduler.now", return_value=fixed_now):
            self.scheduler._schedule[self.periodic_task.id]["next_run"] = (
                fixed_now - timedelta(minutes=1)
            )
            before_total = self.periodic_task.total_run_count

            next_due, due_tasks = self.scheduler.tick()

            self.assertIn(self.periodic_task, due_tasks)
            self.periodic_task.refresh_from_db()
            self.assertEqual(self.periodic_task.total_run_count, before_total + 1)
            expected_next = self.periodic_task.crontab.get_next_run_time(fixed_now)
            self.assertEqual(
                self.scheduler._schedule[self.periodic_task.id]["next_run"],
                expected_next,
            )
            self.assertGreaterEqual(next_due, fixed_now)


class TestRunSchedulerLoop(TestCase):
    def setUp(self):
        past_time = now() - timedelta(minutes=10)
        self.periodic_task = PeriodicTaskFactory(
            name="Loop Task",
            task_name="dummy_task",
            arguments=[],
            kwargs={},
            enabled=True,
            last_run_at=past_time,
            total_run_count=0,
        )
        Task.objects.all().delete()

    def tearDown(self):
        Task.objects.all().delete()

    def test_run_scheduler_loop_single_iteration(self):
        """
        Test run_scheduler_loop by patching time.sleep so that after one iteration
        the scheduler raises KeyboardInterrupt. Then, verify that a Task entry was created.
        """
        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt("Break loop after one iteration")

        with patch("time.sleep", side_effect=fake_sleep):
            with self.assertRaises(KeyboardInterrupt):
                run_scheduler_loop()

        tasks_created = Task.objects.filter(name=self.periodic_task.task_name)
        self.assertGreaterEqual(tasks_created.count(), 1)
