import datetime
from django.test import TestCase
from django.utils.timezone import utc

from django_async_manager.tests.factories import CrontabScheduleFactory


class TestCrontabSchedule(TestCase):
    def setUp(self):
        self.schedule = CrontabScheduleFactory(
            minute="0",
            hour="12",
            day_of_month="*",
            month_of_year="*",
            day_of_week="mon-fri",
        )

    def test_creation(self):
        """Test CrontabSchedule creation using the factory."""
        self.assertIsNotNone(self.schedule.id)
        self.assertEqual(self.schedule.minute, "0")
        self.assertEqual(self.schedule.hour, "12")
        self.assertEqual(self.schedule.day_of_month, "*")
        self.assertEqual(self.schedule.month_of_year, "*")
        self.assertEqual(self.schedule.day_of_week, "mon-fri")

    def test_str_representation(self):
        """Test that __str__ returns the expected string format."""
        expected_str = "0 12 * * mon-fri"
        self.assertEqual(str(self.schedule), expected_str)

    def test_get_next_run_time(self):
        """
        Test that get_next_run_time returns a datetime greater than the base time.
        """
        base_time = datetime.datetime(2025, 4, 4, 10, 15, 0, tzinfo=utc)
        next_run = self.schedule.get_next_run_time(base_time)
        self.assertIsInstance(next_run, datetime.datetime)
        self.assertGreater(next_run, base_time)
