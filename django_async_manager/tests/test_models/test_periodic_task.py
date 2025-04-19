import datetime
from django.test import TestCase
from django.utils.timezone import now, utc
from django_async_manager.tests.factories import PeriodicTaskFactory


class TestPeriodicTask(TestCase):
    def setUp(self):
        """
        Set up a periodic task using the factory.
        Set the crontab schedule to "0 0 * * *" (daily at midnight).
        """
        self.pt = PeriodicTaskFactory(
            name="Test Periodic Task",
            task_name="dummy_task",
            arguments=[1, 2],
            kwargs={"a": 10},
            enabled=True,
            total_run_count=0,
        )

        self.pt.crontab.minute = "0"
        self.pt.crontab.hour = "0"
        self.pt.crontab.day_of_month = "*"
        self.pt.crontab.month_of_year = "*"
        self.pt.crontab.day_of_week = "*"
        self.pt.crontab.save()

    def test_creation(self):
        """Test PeriodicTask creation using the factory."""
        self.assertIsNotNone(self.pt.id)
        self.assertEqual(self.pt.name, "Test Periodic Task")
        self.assertEqual(self.pt.task_name, "dummy_task")
        self.assertEqual(self.pt.arguments, [1, 2])
        self.assertEqual(self.pt.kwargs, {"a": 10})
        self.assertTrue(self.pt.enabled)
        self.assertEqual(self.pt.total_run_count, 0)

    def test_get_next_run_at_without_last_run(self):
        """
        Test that if last_run_at is not set, get_next_run_at returns a datetime
        that is greater than or equal to the current time.
        """
        pt = PeriodicTaskFactory(last_run_at=None)
        next_run = pt.get_next_run_at()
        self.assertIsInstance(next_run, datetime.datetime)
        self.assertGreaterEqual(next_run, now())

    def test_get_next_run_at_with_last_run(self):
        """
        For a periodic task with last_run_at set to a known value,
        get_next_run_at should return the next run time based on its crontab.
        For a schedule "0 0 * * *", if last_run_at is April 4, 2025, 00:00 UTC,
        the next run should be April 5, 2025, 00:00 UTC.
        """
        last_run = datetime.datetime(2025, 4, 4, 0, 0, 0, tzinfo=utc)
        self.pt.last_run_at = last_run
        self.pt.save()
        next_run = self.pt.get_next_run_at()
        expected_next_run = datetime.datetime(2025, 4, 5, 0, 0, 0, tzinfo=utc)
        self.assertEqual(next_run, expected_next_run)

    def test_str_representation(self):
        """Test that __str__ returns the unique name of the periodic task."""
        self.assertEqual(str(self.pt), "Test Periodic Task")
