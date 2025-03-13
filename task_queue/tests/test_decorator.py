import json

from django.test import TestCase

from task_queue.decorators import background_task
from task_queue.models import Task


class BackgroundTaskDecoratorTests(TestCase):
    def test_task_registration(self):
        """Test if a function decorated with @background_task registers a Task."""

        @background_task
        def dummy_task(x, y):
            return x + y

        task = dummy_task.run_async(2, 3)

        self.assertIsInstance(task, Task)
        self.assertEqual(task.status, "pending")
        self.assertEqual(json.loads(task.arguments), {"args": [2, 3], "kwargs": {}})
