from datetime import date

from django.test import TestCase

from todos.forms import TodoEditForm, TodoForm
from todos.models import Todo
from todos.tests.integration.helpers import PRIORITY_SELECT, first_list, make_user


class TodoFormPriorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user()
        cls.todo_list = first_list(cls.user)

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
                form.instance.todo_list = self.todo_list
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
        todo = Todo.objects.create(
            todo_list=self.todo_list, title="Call home", priority=Todo.Priority.HIGH
        )
        self.assertEqual(
            TodoForm(instance=todo)["priority"].value(), Todo.Priority.HIGH
        )

    def test_editing_without_priority_makes_it_medium(self):
        # The rule "missing means Medium" holds for a saved to-do too.
        todo = Todo.objects.create(
            todo_list=self.todo_list, title="Call home", priority=Todo.Priority.HIGH
        )
        TodoForm({"title": "y"}, instance=todo).save()
        todo.refresh_from_db()
        self.assertEqual(todo.priority, Todo.Priority.MEDIUM)


class TodoFormNotesTests(TestCase):
    """The notes field of the one form. TestCase: a ModelForm may use the database."""

    def form(self, **data):
        return TodoForm(data={"title": "Buy milk", **data})

    def test_notes_are_optional(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["notes"], "")

    def test_notes_are_trimmed(self):
        for notes, expected in [("  Low-fat  ", "Low-fat"), ("   ", "")]:
            with self.subTest(notes=notes):
                form = self.form(notes=notes)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["notes"], expected)

    def test_line_break_becomes_one_character(self):
        cases = [
            ("Low-fat\r\nOr soy", "Low-fat\nOr soy"),
            # An old Mac line break, "\r" alone, is a line break too.
            ("a\rb", "a\nb"),
        ]
        for notes, expected in cases:
            with self.subTest(notes=notes):
                form = self.form(notes=notes)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["notes"], expected)

    def test_notes_limit(self):
        cases = [
            ("500 characters", "a" * 500, True),
            ("501 characters", "a" * 501, False),
            # 501 characters sent, but 500 after "\r\n" becomes "\n".
            ("500 with a line break", "a" * 498 + "\r\n" + "a", True),
        ]
        for name, notes, valid in cases:
            with self.subTest(name):
                form = self.form(notes=notes)
                self.assertEqual(form.is_valid(), valid, form.errors)
                if not valid:
                    self.assertEqual(list(form.errors), ["notes"])

    def test_notes_box_open(self):
        with self.subTest("a new empty form"):
            self.assertFalse(TodoForm().notes_box_open())
        cases = [
            (
                "bad date, with notes",
                {"due_date": "not-a-date", "notes": "Ring Ana first"},
                True,
            ),
            (
                "bad date, notes of only spaces",
                {"due_date": "not-a-date", "notes": "   "},
                False,
            ),
            ("notes too long", {"notes": "a" * 501}, True),
        ]
        for name, data, expected in cases:
            with self.subTest(name):
                form = self.form(**data)
                form.is_valid()
                self.assertEqual(form.notes_box_open(), expected)


class TodoFormRepeatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user()
        cls.todo_list = first_list(cls.user)

    def test_missing_repeat_on_edit_becomes_none(self):
        # "Changes in behaviour", point 6: like priority, a post without
        # `repeat` saves the empty value ("none"), it does not keep the old one.
        todo = Todo.objects.create(
            todo_list=self.todo_list,
            title="Bins",
            due_date=date(2026, 10, 12),
            repeat="weekly",
        )
        form = TodoEditForm(
            {"title": "Bins", "due_date": "2026-10-12"}, instance=todo, user=self.user
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        todo.refresh_from_db()
        self.assertEqual(todo.repeat, "none")

    # The remembered day (owner decision): a form that sets or changes the
    # due date or the repeat remembers the due date's day.

    def test_add_remembers_the_day(self):
        cases = [
            ({"title": "Rent", "due_date": "2027-01-31", "repeat": "monthly"}, 31),
            ({"title": "Milk", "due_date": "2027-01-05"}, 5),
            ({"title": "Milk"}, None),
        ]
        for data, day in cases:
            with self.subTest(data=data):
                form = TodoForm(data)
                form.instance.todo_list = self.todo_list
                todo = form.save()
                self.assertEqual(todo.repeat_day, day)

    def test_edit_that_changes_the_date_remembers_the_new_day(self):
        todo = Todo.objects.create(
            todo_list=self.todo_list,
            title="Rent",
            due_date=date(2027, 2, 28),
            repeat="monthly",
            repeat_day=31,
        )
        data = {"title": "Rent", "due_date": "2027-02-27", "repeat": "monthly"}
        TodoEditForm(data, instance=todo, user=self.user).save()
        todo.refresh_from_db()
        self.assertEqual(todo.repeat_day, 27)

    def test_edit_that_changes_the_repeat_remembers_the_day(self):
        todo = Todo.objects.create(
            todo_list=self.todo_list, title="Rent", due_date=date(2027, 1, 30)
        )
        data = {"title": "Rent", "due_date": "2027-01-30", "repeat": "monthly"}
        TodoEditForm(data, instance=todo, user=self.user).save()
        todo.refresh_from_db()
        self.assertEqual(todo.repeat_day, 30)

    def test_edit_of_only_the_title_keeps_the_day(self):
        # A copy due 28 Feb that remembers the 31st: fixing a typo must not
        # move the day to the 28th.
        todo = Todo.objects.create(
            todo_list=self.todo_list,
            title="Rnet",
            due_date=date(2027, 2, 28),
            repeat="monthly",
            repeat_day=31,
        )
        data = {"title": "Rent", "due_date": "2027-02-28", "repeat": "monthly"}
        TodoEditForm(data, instance=todo, user=self.user).save()
        todo.refresh_from_db()
        self.assertEqual(todo.repeat_day, 31)
