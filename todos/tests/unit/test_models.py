from datetime import timedelta

from django.core.exceptions import ValidationError
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

    def test_new_todo_has_no_due_date(self):
        self.assertIsNone(Todo.objects.create(title="Buy milk").due_date)

    # Count: new behaviour.

    def test_remaining_leaves_out_done_todos(self):
        Todo.objects.create(title="Buy milk")
        Todo.objects.create(title="Call home")
        done = Todo.objects.create(title="Read chapter 3", done=True)
        self.assertEqual(Todo.objects.remaining().count(), 2)
        self.assertNotIn(done, Todo.objects.remaining())

    def test_remaining_is_zero_when_all_are_done(self):
        Todo.objects.create(title="Buy milk", done=True)
        Todo.objects.create(title="Call home", done=True)
        self.assertEqual(Todo.objects.remaining().count(), 0)

    # Delete completed: new behaviour.

    def test_completed_gives_only_completed_todos(self):
        completed = Todo.objects.create(title="Buy milk", done=True)
        Todo.objects.create(title="Read chapter 3")
        self.assertEqual(list(Todo.objects.completed()), [completed])

    # Priority: new behaviour.

    def test_new_todo_is_medium_priority(self):
        todo = Todo.objects.create(title="Buy milk")
        self.assertEqual(todo.priority, Todo.Priority.MEDIUM)

    def test_priority_sorts_high_to_low_in_the_database(self):
        # A number sorts in the right order; the words would sort high, low, medium.
        low = Todo.objects.create(title="Low", priority=Todo.Priority.LOW)
        high = Todo.objects.create(title="High", priority=Todo.Priority.HIGH)
        medium = Todo.objects.create(title="Medium", priority=Todo.Priority.MEDIUM)
        self.assertEqual(list(Todo.objects.order_by("-priority")), [high, medium, low])

    # Notes: new behaviour.

    def test_new_todo_has_empty_notes(self):
        self.assertEqual(Todo.objects.create(title="Buy milk").notes, "")

    def test_full_clean_checks_the_notes_limit(self):
        with self.subTest(notes="500 characters"):
            Todo(title="Buy milk", notes="a" * 500).full_clean()
        with self.subTest(notes="501 characters"):
            with self.assertRaises(ValidationError) as caught:
                Todo(title="Buy milk", notes="a" * 501).full_clean()
            self.assertIn("notes", caught.exception.message_dict)
