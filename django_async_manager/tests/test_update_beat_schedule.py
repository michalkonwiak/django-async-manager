from io import StringIO
from django.test import TestCase, override_settings
from django.core.management import call_command
from django_async_manager.models import PeriodicTask


class UpdateBeatScheduleCommandTests(TestCase):
    @override_settings(BEAT_SCHEDULE={})
    def test_no_beat_schedule(self):
        """
        Test that when BEAT_SCHEDULE is not defined in settings,
        the command outputs a warning message.
        """
        out = StringIO()
        call_command("update_beat_schedule", stdout=out)
        output = out.getvalue()
        self.assertIn("No BEAT_SCHEDULE found in settings.", output)

    @override_settings(
        BEAT_SCHEDULE={
            "add-every-monday-morning": {
                "task": "tasks.add",
                "schedule": {
                    "minute": "30",
                    "hour": "7",
                    "day_of_week": "1",
                    "day_of_month": "*",
                    "month_of_year": "*",
                },
                "args": [16, 16],
                "kwargs": {},
            }
        }
    )
    def test_update_beat_schedule_success(self):
        """
        Test that the command creates/updates a PeriodicTask and its CrontabSchedule
        based on the BEAT_SCHEDULE configuration in settings.
        """
        out = StringIO()
        call_command("update_beat_schedule", stdout=out)
        output = out.getvalue()
        self.assertIn("Updated periodic task: add-every-monday-morning", output)

        pt = PeriodicTask.objects.get(name="add-every-monday-morning")
        self.assertEqual(pt.task_name, "tasks.add")
        self.assertEqual(pt.arguments, [16, 16])
        self.assertEqual(pt.kwargs, {})

        cs = pt.crontab
        self.assertEqual(cs.minute, "30")
        self.assertEqual(cs.hour, "7")
        self.assertEqual(cs.day_of_week, "1")
        self.assertEqual(cs.day_of_month, "*")
        self.assertEqual(cs.month_of_year, "*")

    @override_settings(
        BEAT_SCHEDULE={
            "send-reminders": {
                "task": "tasks.send_reminder_emails",
                "schedule": {
                    "minute": "15",
                    "hour": "9",
                    "day_of_week": "*",
                    "day_of_month": "*",
                    "month_of_year": "*",
                },
                "args": ["user@example.com"],
                "kwargs": {"subject": "Reminder"},
            }
        }
    )
    def test_update_existing_periodic_task(self):
        """
        Test that if a periodic task already exists, the command updates its configuration.
        """
        out1 = StringIO()
        call_command("update_beat_schedule", stdout=out1)
        new_schedule = {
            "task": "tasks.send_reminder_emails",
            "schedule": {
                "minute": "0",
                "hour": "10",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
            },
            "args": ["newuser@example.com"],
            "kwargs": {"subject": "Updated Reminder"},
        }
        with self.settings(BEAT_SCHEDULE={"send-reminders": new_schedule}):
            out2 = StringIO()
            call_command("update_beat_schedule", stdout=out2)
            output2 = out2.getvalue()
            self.assertIn("Updated periodic task: send-reminders", output2)
            pt_updated = PeriodicTask.objects.get(name="send-reminders")
            self.assertEqual(pt_updated.task_name, "tasks.send_reminder_emails")
            self.assertEqual(pt_updated.arguments, ["newuser@example.com"])
            self.assertEqual(pt_updated.kwargs, {"subject": "Updated Reminder"})
            cs = pt_updated.crontab
            self.assertEqual(cs.minute, "0")
            self.assertEqual(cs.hour, "10")
