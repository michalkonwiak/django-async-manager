import datetime
from datetime import timedelta
import types
from django.test import TestCase
from django.utils.timezone import now, utc
from unittest.mock import patch, MagicMock

from django_async_manager.models import Task
from django_async_manager.scheduler import BeatScheduler, run_scheduler_loop
from django_async_manager.tests.factories import PeriodicTaskFactory


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

        with patch.object(BeatScheduler, "check_missed_tasks"):
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

    def test_check_missed_tasks(self):
        """
        Test that check_missed_tasks identifies and processes tasks that were missed.
        """
        past_time = now() - timedelta(hours=3)
        missed_task = PeriodicTaskFactory(
            name="Missed Task",
            task_name="dummy_module.dummy_function",
            enabled=True,
            last_run_at=past_time,
        )

        next_run = past_time + timedelta(minutes=30)

        with patch.object(
            missed_task.crontab, "get_next_run_time", return_value=next_run
        ):
            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_function = MagicMock()
                mock_function.run_async = None
                mock_module.dummy_function = mock_function
                mock_import.return_value = mock_module

                with patch(
                    "django_async_manager.utils.with_database_lock_handling",
                    lambda *args, **kwargs: lambda func: func,
                ):
                    self.scheduler.check_missed_tasks()

                    mock_import.assert_called_with("dummy_module")
                    mock_function.assert_called_once()

                    missed_task.refresh_from_db()
                    self.assertGreater(missed_task.last_run_at, past_time)

    def test_tick(self):
        """
        Test the tick method:
          - If a task is due (next_run is less than current time),
            tick should return it in due_tasks_info, update the internal schedule next_run,
            but NOT modify the database.
        """
        fixed_now = datetime.datetime(2025, 4, 6, 16, 3, 0, tzinfo=utc)
        with patch("django_async_manager.scheduler.now", return_value=fixed_now):
            self.scheduler._schedule[self.periodic_task.id]["next_run"] = (
                fixed_now - timedelta(minutes=1)
            )
            before_total = self.periodic_task.total_run_count

            next_due, due_tasks_info = self.scheduler.tick()

            tasks = [info["task"] for info in due_tasks_info]
            self.assertIn(self.periodic_task, tasks)

            self.periodic_task.refresh_from_db()
            self.assertEqual(self.periodic_task.total_run_count, before_total)

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
            task_name="dummy_task.dummy_task",
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

        dummy_module = types.SimpleNamespace()

        def stub_run_async(*args, **kwargs):
            return Task.objects.create(
                name=self.periodic_task.task_name,
                arguments={"args": [], "kwargs": {}},
                status="pending",
            )

        stub_run_async.run_async = stub_run_async
        dummy_module.dummy_task = stub_run_async

        with patch("time.sleep", side_effect=fake_sleep):
            with patch("importlib.import_module", return_value=dummy_module):
                with self.assertRaises(KeyboardInterrupt):
                    run_scheduler_loop()

        tasks_created = Task.objects.filter(name=self.periodic_task.task_name)
        self.assertGreaterEqual(tasks_created.count(), 1)
