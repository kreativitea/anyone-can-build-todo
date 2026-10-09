from django.test import TestCase

from todos.forms import TodoForm
from todos.models import Todo
from todos.tests.integration.helpers import PRIORITY_SELECT


class TodoFormPriorityTests(TestCase):
    def test_new_form_starts_on_medium(self):
        form = TodoForm()
        self.assertEqual(form["priority"].value(), Todo.Priority.MEDIUM)
        self.assertHTMLEqual(str(form["priority"]), PRIORITY_SELECT)

    def test_each_priority_is_accepted(self):
        for value, priority in [
            ("3", Todo.Priority.HIGH),
            ("2", Todo.Priority.MEDIUM),
            ("1", Todo.Priority.LOW),
        ]:
            with self.subTest(value=value):
                form = TodoForm({"title": "Buy milk", "priority": value})
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["priority"], priority)

    def test_missing_or_empty_priority_is_medium(self):
        for data in [{"title": "Buy milk"}, {"title": "Buy milk", "priority": ""}]:
            with self.subTest(data=data):
                form = TodoForm(data)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.save().priority, Todo.Priority.MEDIUM)

    def test_unknown_priority_is_an_error(self):
        for value in ["9", "0", "high"]:
            with self.subTest(value=value):
                form = TodoForm({"title": "Buy milk", "priority": value})
                self.assertEqual(
                    form.errors["priority"],
                    [
                        f"Select a valid choice. {value} is not one of the "
                        "available choices."
                    ],
                )
                self.assertFalse(form.is_valid())

    def test_form_shows_the_saved_priority(self):
        # For "edit" (feature 4): a form for a saved to-do shows its priority.
        todo = Todo.objects.create(title="Call home", priority=Todo.Priority.HIGH)
        self.assertEqual(
            TodoForm(instance=todo)["priority"].value(), Todo.Priority.HIGH
        )

    def test_editing_without_priority_makes_it_medium(self):
        # The rule "missing means Medium" holds for a saved to-do too.
        todo = Todo.objects.create(title="Call home", priority=Todo.Priority.HIGH)
        TodoForm({"title": "y"}, instance=todo).save()
        todo.refresh_from_db()
        self.assertEqual(todo.priority, Todo.Priority.MEDIUM)
