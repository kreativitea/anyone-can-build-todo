"""Accounts (17): who owns a to-do, and the guard that views always ask by owner."""

import inspect
import re
from datetime import date

from django.test import SimpleTestCase, TestCase

from todos import forms, views
from todos.models import Todo
from todos.tests.integration.helpers import make_user


class OwnerModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")
        cls.ben = make_user("ben")

    def test_for_user_gives_only_their_todos(self):
        milk = Todo.objects.create(owner=self.ana, title="Buy milk")
        home = Todo.objects.create(owner=self.ana, title="Call home")
        Todo.objects.create(owner=self.ben, title="Ben's secret")
        self.assertEqual(list(Todo.objects.for_user(self.ana)), [milk, home])

    def test_next_repeat_keeps_the_owner(self):
        bins = Todo.objects.create(
            owner=self.ben, title="Bins", repeat="weekly", due_date=date(2026, 10, 12)
        )
        self.assertEqual(bins.next_copy().owner, self.ben)

    def test_deleting_a_user_deletes_their_todos(self):
        milk = Todo.objects.create(owner=self.ana, title="Buy milk")
        Todo.objects.create(owner=self.ben, title="Ben's secret")
        self.ben.delete()
        self.assertEqual(list(Todo.objects.all()), [milk])


# A to-do query in a view or a form that does not start from the owner.
# `Todo.objects` must go on with `.for_user(`; a step is never asked for
# directly (always through its to-do: `todo.subtasks`).
UNSCOPED = [
    re.compile(r"\bTodo\.objects\b(?!\.for_user\()"),
    re.compile(r"\bTodo\._(default|base)_manager\b"),
    re.compile(r"\bSubtask\.objects\b"),
    re.compile(r"\bSubtask\._(default|base)_manager\b"),
    re.compile(r"get_object_or_404\(\s*Todo\b(?!\.objects\.for_user\()"),
    re.compile(r"get_object_or_404\(\s*Subtask\b"),
]


def unscoped_lines(module):
    """Every line of `module` that asks for to-dos without the owner, with its number."""
    found = []
    for number, line in enumerate(inspect.getsource(module).splitlines(), start=1):
        if any(pattern.search(line) for pattern in UNSCOPED):
            found.append(f"{module.__name__}:{number}: {line.strip()}")
    return found


class OwnerGuardTests(SimpleTestCase):
    """A text search of views.py and forms.py. The 404 matrix is the real check
    (integration/test_ownership.py); this one catches the common mistake early.
    Model code (models.py) is not read: it works on a to-do already found.
    """

    maxDiff = None  # show every line the guard found

    def test_views_never_ask_for_todos_without_the_owner(self):
        found = unscoped_lines(views) + unscoped_lines(forms)
        self.assertEqual(
            found,
            [],
            "Start every to-do query with Todo.objects.for_user(request.user), "
            "and find a step through its to-do (todo.subtasks).",
        )

    def test_the_guard_finds_an_unscoped_query(self):
        # The guard itself must work: each of these is a mistake.
        for line in [
            "todos = Todo.objects.all()",
            "Todo.objects.filter(pk=pk).update(edited=True)",
            "todo = get_object_or_404(Todo, pk=pk)",
            "step = get_object_or_404(Subtask, pk=pk)",
            "steps = Subtask.objects.filter(todo_id=pk)",
            "Todo._default_manager.all()",
        ]:
            with self.subTest(line=line):
                self.assertTrue(any(p.search(line) for p in UNSCOPED))
        for line in [
            "todos = Todo.objects.for_user(request.user).completed()",
            "todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)",
            "step = get_object_or_404(todo.subtasks, pk=subtask_pk)",
            "SEARCH_MAX_LENGTH = Todo._meta.get_field('title').max_length",
        ]:
            with self.subTest(line=line):
                self.assertFalse(any(p.search(line) for p in UNSCOPED))
