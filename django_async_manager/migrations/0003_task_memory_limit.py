from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_async_manager", "0002_task_django_asyn_queue_de1c17_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="memory_limit",
            field=models.IntegerField(
                blank=True,
                help_text="Max memory usage in MB (None for no limit)",
                null=True,
            ),
        ),
    ]
