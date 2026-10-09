from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from todos.models import Todo


class TodoModelTests(TestCase):
    def test_str_is_the_title(self):
        self.assertEqual(str(Todo(title="Buy milk")), "Buy milk")

    def test_new_todo_is_not_done(self):
        self.assertFalse(Todo.objects.create(title="Buy milk").done)

    def test_list_is_oldest_first(self):
        newer = Todo.objects.create(title="Newer")
        older = Todo.objects.create(title="Older")
        # created_at is set by itself, so move "Older" back in time to be sure.
        Todo.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        self.assertEqual(list(Todo.objects.all()), [older, newer])
