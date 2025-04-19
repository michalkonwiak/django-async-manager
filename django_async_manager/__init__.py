default_app_config = "django_async_manager.apps.DjangoAsyncManagerConfig"


def get_background_task():
    from django_async_manager.decorators import background_task

    return background_task


def get_task():
    from django_async_manager.models import Task

    return Task


def get_crontab_schedule():
    from django_async_manager.models import CrontabSchedule

    return CrontabSchedule


def get_periodic_task():
    from django_async_manager.models import PeriodicTask

    return PeriodicTask
