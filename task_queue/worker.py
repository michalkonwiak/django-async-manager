import json
import time
from django.utils.timezone import now
from task_queue.models import Task


class TaskWorker:
    """Worker for fetching and executing tasks"""

    def process_task(self):
        task = Task.objects.filter(status="pending").order_by("-priority").first()
        if not task:
            return

        task.status = "in_progress"
        task.started_at = now()
        task.save()

        try:
            func = globals().get(task.name)
            if func:
                args = json.loads(task.arguments)["args"]
                kwargs = json.loads(task.arguments)["kwargs"]
                func(*args, **kwargs)

            task.status = "completed"
            task.completed_at = now()
        except Exception as e:
            task.mark_as_failed(str(e))

        task.save()

    def run(self):
        """Continuous processing tasks"""
        while True:
            self.process_task()

            # Checking per 5 seconds
            time.sleep(5)
