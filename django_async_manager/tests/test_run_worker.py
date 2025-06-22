from unittest.mock import patch, MagicMock
from django.core.management import call_command
from django.test import TestCase


class RunWorkerCommandTests(TestCase):
    @patch("django_async_manager.management.commands.run_worker.WorkerManager")
    def test_run_worker_single_worker(self, mock_worker_manager):
        """Test if run_worker starts a single worker by default"""
        mock_instance = MagicMock()
        mock_worker_manager.return_value = mock_instance

        call_command("run_worker")

        mock_worker_manager.assert_called_once_with(
            num_workers=1, queue="default", use_processes=False
        )
        mock_instance.start_workers.assert_called_once()
        mock_instance.join_workers.assert_called_once()

    @patch("django_async_manager.management.commands.run_worker.WorkerManager")
    def test_run_worker_multiple_workers(self, mock_worker_manager):
        """Test if run_worker starts multiple workers when specified"""
        mock_instance = MagicMock()
        mock_worker_manager.return_value = mock_instance

        call_command("run_worker", "--num-workers", "3")

        mock_worker_manager.assert_called_once_with(
            num_workers=3, queue="default", use_processes=False
        )
        mock_instance.start_workers.assert_called_once()
        mock_instance.join_workers.assert_called_once()

    @patch("django_async_manager.management.commands.run_worker.WorkerManager")
    def test_run_worker_process_management(self, mock_worker_manager):
        """Test if run_worker properly manages multiple workers with processes"""
        mock_instance = MagicMock()
        mock_worker_manager.return_value = mock_instance

        call_command("run_worker", "--num-workers", "2", "--processes")

        mock_worker_manager.assert_called_once_with(
            num_workers=2, queue="default", use_processes=True
        )
        mock_instance.start_workers.assert_called_once()
        mock_instance.join_workers.assert_called_once()

    @patch("django_async_manager.management.commands.run_worker.WorkerManager")
    def test_run_worker_custom_queue(self, mock_worker_manager):
        """Test if run_worker passes the custom queue parameter to WorkerManager"""
        mock_instance = MagicMock()
        mock_worker_manager.return_value = mock_instance

        call_command("run_worker", "--queue", "critical")

        mock_worker_manager.assert_called_once_with(
            num_workers=1, queue="critical", use_processes=False
        )
        mock_instance.start_workers.assert_called_once()
        mock_instance.join_workers.assert_called_once()
