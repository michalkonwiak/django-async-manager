import factory
import uuid
from django.utils.timezone import now, timedelta
from faker import Faker

from task_queue.models import Task

faker = Faker()


class TaskFactory(factory.django.DjangoModelFactory):
    """Factory to create Task instances for testing."""

    class Meta:
        model = Task

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.LazyAttribute(lambda _: faker.sentence(nb_words=4))
    status = factory.Iterator(
        ["pending", "in_progress", "completed", "failed", "canceled"]
    )
    priority = factory.LazyAttribute(
        lambda _: faker.random_element(list(Task.PRIORITY_MAPPING.values()))
    )
    arguments = factory.LazyAttribute(lambda _: {"arg": faker.word()})
    created_at = factory.LazyFunction(now)
    scheduled_at = factory.LazyFunction(
        lambda: now() + timedelta(hours=faker.random_int(1, 48))
    )
    started_at = None
    completed_at = None
    timeout = factory.LazyAttribute(lambda _: faker.random_int(100, 500))
    attempts = 0
    max_retries = factory.LazyAttribute(lambda _: faker.random_int(3, 5))
    worker_id = factory.LazyAttribute(
        lambda _: faker.uuid4() if faker.boolean(chance_of_getting_true=50) else None
    )
    last_errors = factory.LazyAttribute(lambda _: [])
    archived = False

    @factory.post_generation
    def dependencies(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for dependency in extracted:
                self.dependencies.add(dependency)

    @classmethod
    def from_string_priority(cls, **kwargs):
        if "priority" in kwargs and isinstance(kwargs["priority"], str):
            kwargs["priority"] = Task.PRIORITY_MAPPING.get(kwargs["priority"], 2)
        return cls.create(**kwargs)
