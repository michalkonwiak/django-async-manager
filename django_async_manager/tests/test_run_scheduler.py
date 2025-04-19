from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase


class RunSchedulerCommandTests(TestCase):
    @patch("django_async_manager.management.commands.run_scheduler.run_scheduler_loop")
    def test_run_scheduler_default(self, mock_run_scheduler_loop):
        """
        Test that calling the run_scheduler command without any options calls run_scheduler_loop.
        """
        call_command("run_scheduler")
        mock_run_scheduler_loop.assert_called_once()

    @patch(
        "django_async_manager.management.commands.run_scheduler.run_scheduler_loop",
        side_effect=KeyboardInterrupt,
    )
    def test_run_scheduler_with_default_interval(self, mock_run_scheduler_loop):
        """
        Test that calling the run_scheduler command with a specified default interval
        still calls run_scheduler_loop. We simulate a KeyboardInterrupt to break the loop.
        """
        with self.assertRaises(KeyboardInterrupt):
            call_command("run_scheduler", "--default-interval", "10")
        mock_run_scheduler_loop.assert_called_once()
