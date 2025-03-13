from unittest.mock import patch, MagicMock
from django.core.management import call_command
from django.test import TestCase


class RunWorkerCommandTests(TestCase):
    @patch("multiprocessing.Process")
    def test_run_worker_single_worker(self, mock_process):
        """Test if run_worker starts a single worker by default"""
        mock_instance = MagicMock()
        mock_process.return_value = mock_instance

        call_command("run_worker")

        mock_process.assert_called_once_with(
            target=mock_process.call_args[1]["target"], args=(0,)
        )
        mock_instance.start.assert_called_once()
        mock_instance.join.assert_called_once()

    @patch("multiprocessing.Process")
    def test_run_worker_multiple_workers(self, mock_process):
        """Test if run_worker starts multiple workers when specified"""
        mock_instance = MagicMock()
        mock_process.return_value = mock_instance

        call_command("run_worker", "--num-workers", "3")

        self.assertEqual(mock_process.call_count, 3)
        self.assertEqual(mock_instance.start.call_count, 3)
        self.assertEqual(mock_instance.join.call_count, 3)

    @patch("multiprocessing.Process")
    def test_run_worker_process_management(self, mock_process):
        """Test if run_worker properly manages multiple processes"""
        mock_instance = MagicMock()
        mock_process.return_value = mock_instance

        call_command("run_worker", "--num-workers", "2")

        self.assertEqual(mock_process.call_count, 2)
        self.assertEqual(mock_instance.start.call_count, 2)
        self.assertEqual(mock_instance.join.call_count, 2)
