from datetime import date, timedelta
from unittest import mock

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


class RepeatModelTests(TestCase):
    """Repeating to-dos (feature 19): the fields, the check, and the next copy."""

    # One sample value for each field a person can change. A new field from a
    # later feature must be added here: see the test below.
    SAMPLES = {
        "title": "Bins",
        "notes": "blue bag",
        "priority": Todo.Priority.HIGH,
        "repeat": "weekly",
    }

    def test_new_todo_does_not_repeat(self):
        todo = Todo()
        self.assertEqual(todo.repeat, "none")
        self.assertFalse(todo.repeats)

    def test_repeat_without_due_date_is_invalid(self):
        with self.assertRaises(ValidationError) as caught:
            Todo(title="x", repeat="weekly").full_clean()
        self.assertEqual(
            caught.exception.message_dict,
            {"repeat": ["A repeating to-do needs a due date."]},
        )

    def test_next_copy_copies_every_field_a_person_can_change(self):
        names = [
            field.name
            for field in Todo._meta.get_fields()
            if getattr(field, "editable", False)
            and not field.auto_created
            and field.name not in {"done", "due_date", "created_at"}
        ]
        for name in names:
            with self.subTest(field=name):
                if name not in self.SAMPLES:
                    self.fail(
                        f"New field `{name}`: add a sample value here, and decide "
                        "whether next_values() copies it."
                    )
                todo = Todo(title="x", repeat="daily", due_date=date(2026, 10, 12))
                setattr(todo, name, self.SAMPLES[name])
                self.assertEqual(getattr(todo.next_copy(), name), self.SAMPLES[name])

    def test_next_copy_is_open_with_the_next_date(self):
        todo = Todo.objects.create(
            title="Bins", repeat="weekly", due_date=date(2026, 10, 12), done=True
        )
        copy = todo.next_copy()
        self.assertFalse(copy.done)
        self.assertEqual(copy.due_date, date(2026, 10, 19))
        self.assertIsNone(copy.pk)

    def test_next_copy_without_due_date_starts_from_today(self):
        todo = Todo(title="Water plants", repeat="daily")
        with mock.patch(
            "django.utils.timezone.localdate", return_value=date(2026, 10, 12)
        ):
            copy = todo.next_copy()
        self.assertEqual(copy.due_date, date(2026, 10, 13))
