from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.db import OperationalError

from django_async_manager.utils import with_database_lock_handling


class TestDatabaseLockHandling(TestCase):
    """Tests for the with_database_lock_handling decorator."""

    def test_successful_execution(self):
        """Test that the decorator allows successful function execution."""
        mock_function = MagicMock(return_value="success")
        decorated_function = with_database_lock_handling()(mock_function)

        result = decorated_function("arg1", kwarg1="value1")

        self.assertEqual(result, "success")
        mock_function.assert_called_once_with("arg1", kwarg1="value1")

    @patch("time.sleep")
    def test_database_lock_retry_success(self, mock_sleep):
        """Test that the decorator retries on database lock and succeeds."""
        mock_function = MagicMock(
            side_effect=[OperationalError("database is locked"), "success"]
        )
        decorated_function = with_database_lock_handling(max_retries=3)(mock_function)

        result = decorated_function()

        self.assertEqual(result, "success")
        self.assertEqual(mock_function.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("time.sleep")
    def test_database_lock_max_retries_exceeded(self, mock_sleep):
        """Test that the decorator returns None after max retries."""
        mock_function = MagicMock(side_effect=OperationalError("database is locked"))
        decorated_function = with_database_lock_handling(max_retries=2)(mock_function)

        result = decorated_function()

        self.assertIsNone(result)
        self.assertEqual(mock_function.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("logging.getLogger")
    def test_non_lock_operational_error(self, mock_get_logger):
        """Test that non-lock OperationalError is re-raised."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_function = MagicMock(side_effect=OperationalError("some other error"))
        decorated_function = with_database_lock_handling()(mock_function)

        with self.assertRaises(OperationalError):
            decorated_function()

        mock_function.assert_called_once()
        mock_logger.exception.assert_called_once()

    @patch("logging.getLogger")
    def test_other_exception(self, mock_get_logger):
        """Test that other exceptions are re-raised."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_function = MagicMock(side_effect=ValueError("test error"))
        decorated_function = with_database_lock_handling()(mock_function)

        with self.assertRaises(ValueError):
            decorated_function()

        mock_function.assert_called_once()
        mock_logger.exception.assert_called_once()

    @patch("time.sleep")
    @patch("random.random", return_value=0.5)
    def test_exponential_backoff(self, mock_random, mock_sleep):
        """Test that exponential backoff is applied correctly."""
        mock_function = MagicMock(
            side_effect=[
                OperationalError("database is locked"),
                OperationalError("database is locked"),
                "success",
            ]
        )
        decorated_function = with_database_lock_handling(max_retries=5)(mock_function)

        result = decorated_function()

        self.assertEqual(result, "success")
        self.assertEqual(mock_function.call_count, 3)
        # First retry: (2^1) * 0.1 + (0.5 * 0.1) = 0.25
        # Second retry: (2^2) * 0.1 + (0.5 * 0.1) = 0.45
        mock_sleep.assert_any_call(0.25)
        mock_sleep.assert_any_call(0.45)
