# Generated by Django 4.2 on 2025-03-26 21:41

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("task_queue", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="task",
            name="parent_task",
        ),
        migrations.AddField(
            model_name="task",
            name="dependencies",
            field=models.ManyToManyField(
                blank=True,
                help_text="Tasks that must be completed before this one runs",
                related_name="dependent_tasks",
                to="task_queue.task",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="max_retries",
            field=models.IntegerField(
                default=1, help_text="Max number of retries before marking as failed"
            ),
        ),
    ]
