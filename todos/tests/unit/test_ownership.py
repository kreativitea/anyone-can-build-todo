"""Accounts (17): who owns a to-do, and the guard that views always ask by owner."""

import re
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from todos.models import Todo
from todos.tests.integration.helpers import first_list, make_user


class OwnerModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")
        cls.ben = make_user("ben")
        cls.anas_list = first_list(cls.ana)
        cls.bens_list = first_list(cls.ben)

    def test_for_user_gives_only_their_todos(self):
        milk = Todo.objects.create(todo_list=self.anas_list, title="Buy milk")
        home = Todo.objects.create(todo_list=self.anas_list, title="Call home")
        Todo.objects.create(todo_list=self.bens_list, title="Ben's secret")
        self.assertEqual(list(Todo.objects.for_user(self.ana)), [milk, home])

    def test_next_repeat_keeps_the_owner(self):
        bins = Todo.objects.create(
            todo_list=self.bens_list,
            title="Bins",
            repeat="weekly",
            due_date=date(2026, 10, 12),
        )
        self.assertEqual(bins.next_copy().owner, self.ben)

    def test_deleting_a_user_deletes_their_todos(self):
        milk = Todo.objects.create(todo_list=self.anas_list, title="Buy milk")
        Todo.objects.create(todo_list=self.bens_list, title="Ben's secret")
        self.ben.delete()
        self.assertEqual(list(Todo.objects.all()), [milk])

    # Defence in depth: the model's own UPDATE and DELETE also ask for the owner.

    def test_mark_edited_changes_only_a_row_of_the_same_owner(self):
        milk = Todo.objects.create(todo_list=self.anas_list, title="Buy milk")
        stale = Todo.objects.get(pk=milk.pk)
        stale.owner_id = self.ben.pk  # an object that does not match its row
        stale.mark_edited()
        milk.refresh_from_db()
        self.assertFalse(milk.edited)
        milk.mark_edited()
        milk.refresh_from_db()
        self.assertTrue(milk.edited)

    def test_undo_never_deletes_a_copy_of_another_person(self):
        bins = Todo.objects.create(
            todo_list=self.anas_list,
            title="Bins",
            repeat="weekly",
            due_date=date(2026, 10, 12),
        )
        bins.set_done(True)
        bins.refresh_from_db()
        copy_pk = bins.next_todo_id
        # A broken row: the copy belongs to someone else.
        Todo.objects.filter(pk=copy_pk).update(owner=self.ben)
        bins.set_done(False)
        self.assertTrue(Todo.objects.filter(pk=copy_pk, owner=self.ben).exists())


# A to-do query that does not start from the owner. `Todo.objects` must go on
# with `.for_user(`; a step is never asked for directly (always through its
# to-do: `todo.subtasks`); no generic view or form is built on the models.
# Lists (13): `TodoList.objects` goes on with `.for_user(` (lists a person may
# use), `.owned_by(` (owner-only actions) or `.create_default(` (sign-up).
# Tags (14): `Tag.objects` goes on with `.owned_by(` (a person's own tags).
# Never a raw owner filter: sharing (20) replaces for_user, and must find
# every caller.
UNSCOPED = [
    re.compile(r"\bTodoList\.objects\b(?!\.(for_user|owned_by|create_default)\()"),
    re.compile(r"\bTodoList\._(default|base)_manager\b"),
    re.compile(r"get_object_or_404\(\s*TodoList\b(?!\.objects\.(for_user|owned_by)\()"),
    re.compile(r"get_list_or_404\(\s*TodoList\b(?!\.objects\.(for_user|owned_by)\()"),
    re.compile(r"\bTodo\.objects\b(?!\.for_user\()"),
    re.compile(r"\bTodo\._(default|base)_manager\b"),
    re.compile(r"\bSubtask\.objects\b"),
    re.compile(r"\bSubtask\._(default|base)_manager\b"),
    re.compile(r"get_object_or_404\(\s*Todo\b(?!\.objects\.for_user\()"),
    re.compile(r"get_object_or_404\(\s*Subtask\b"),
    re.compile(r"get_list_or_404\(\s*Todo\b(?!\.objects\.for_user\()"),
    re.compile(r"get_list_or_404\(\s*Subtask\b"),
    re.compile(r"\bTag\.objects\b(?!\.owned_by\()"),
    re.compile(r"\bTag\._(default|base)_manager\b"),
    re.compile(r"get_object_or_404\(\s*Tag\b(?!\.objects\.owned_by\()"),
    re.compile(r"get_list_or_404\(\s*Tag\b(?!\.objects\.owned_by\()"),
    re.compile(r"\bmodel\s*=\s*(Todo|Subtask|TodoList|Tag)\b"),
    # A model looked up by name skips every check above (only data migrations may).
    re.compile(r"\bget_model\("),
    re.compile(r"\.model\.objects\b"),
]

ROOT = Path(__file__).resolve().parents[3]

# The only lines allowed to match, each with its reason. A line is matched by
# its file and its exact text, so a NEW line like these still fails.
ALLOWED = {
    # Model methods: they work on the to-do (self) that a view already found
    # through its owner. mark_edited and Undo's DELETE also filter by owner_id.
    ("todos/models.py", "Subtask.objects.bulk_create("),
    (
        "todos/models.py",
        "Todo.objects.filter(pk=self.pk, owner_id=self.owner_id).update(edited=True)",
    ),
    (
        "todos/models.py",
        "claimed = Todo.objects.filter(pk=self.pk, done=not target).update(",
    ),
    ("todos/models.py", "fresh = Todo.objects.get(pk=self.pk)"),
    ("todos/models.py", "Todo.objects.filter(pk=fresh.pk).update(next_todo=copy)"),
    ("todos/models.py", "Todo.objects.filter("),  # Undo's DELETE, with owner_id
    # The ModelForms' Meta: a form reads no rows (the owner is never a field).
    ("todos/forms.py", "model = Todo"),
    ("todos/forms.py", "model = Subtask"),
    ("todos/forms.py", "model = TodoList"),
    # A data migration runs once, on every row, before anyone is logged in.
    ("todos/data_migrations.py", "Todo.objects.filter(owner__isnull=True).delete()"),
    ("todos/data_migrations.py", 'Todo = apps.get_model("todos", "Todo")'),
    (
        "todos/data_migrations.py",
        "Todo.objects.filter(todo_list__isnull=True).delete()",
    ),
    # The admin: staff see every to-do on purpose.
    ("todos/admin.py", "model = Subtask"),
}


def source_files():
    """Every .py file of the app and the project, except tests and migrations."""
    for folder in ["todos", "config"]:
        for path in sorted((ROOT / folder).rglob("*.py")):
            parts = path.relative_to(ROOT).parts
            if "tests" in parts or "migrations" in parts:
                continue
            yield path


def unscoped_lines():
    """Every line that asks for to-dos without the owner, with its file and number."""
    found = []
    for path in source_files():
        name = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            text = line.strip()
            if (name, text) in ALLOWED:
                continue
            if any(pattern.search(line) for pattern in UNSCOPED):
                found.append(f"{name}:{number}: {text}")
    return found


class OwnerGuardTests(SimpleTestCase):
    """A text search of every .py file in todos/ and config/ (not tests or
    migrations). The 404 matrix and the canary are the real checks
    (integration/test_ownership.py); this one catches the common mistake early.
    """

    maxDiff = None  # show every line the guard found

    def test_views_never_ask_for_todos_without_the_owner(self):
        self.assertEqual(
            unscoped_lines(),
            [],
            "Start every to-do query with Todo.objects.for_user(request.user), "
            "and find a step through its to-do (todo.subtasks). Model code that "
            "works on a to-do already found goes in ALLOWED, with its reason.",
        )

    def test_the_guard_reads_the_views_forms_and_settings(self):
        names = {path.relative_to(ROOT).as_posix() for path in source_files()}
        for name in [
            "todos/views.py",
            "todos/forms.py",
            "todos/models.py",
            "todos/admin.py",
            "config/urls.py",
            "config/settings.py",
        ]:
            self.assertIn(name, names)
        self.assertFalse(any("/tests/" in n or "/migrations/" in n for n in names))

    def test_the_guard_finds_an_unscoped_query(self):
        # The guard itself must work: each of these is a mistake.
        for line in [
            "todos = Todo.objects.all()",
            "Todo.objects.filter(pk=pk).update(edited=True)",
            "todo = get_object_or_404(Todo, pk=pk)",
            "step = get_object_or_404(Subtask, pk=pk)",
            "steps = Subtask.objects.filter(todo_id=pk)",
            "Todo._default_manager.all()",
            "    model = Todo",
            "class TodoDetail(DetailView): model = Todo",
            "steps = get_list_or_404(Subtask, todo=todo)",
            "todos = get_list_or_404(Todo, done=True)",
            "steps = todo.subtasks.model.objects.all()",
            "lists = TodoList.objects.all()",
            "lists = TodoList.objects.filter(owner=request.user)",
            "todo_list = get_object_or_404(TodoList, pk=list_pk, owner=request.user)",
            "TodoList._default_manager.get(pk=list_id)",
            "lists = get_list_or_404(TodoList, owner=user)",
            "    model = TodoList",
            "class ListDetail(DetailView): model = TodoList",
            'TodoList = apps.get_model("todos", "TodoList")',
            'lists = django_apps.get_model("todos.TodoList").objects.all()',
            "tags = Tag.objects.filter(name=name)",
            "tag, _ = Tag.objects.get_or_create(owner=owner, name=name)",
            "tag = get_object_or_404(Tag, pk=pk)",
            "Tag._default_manager.all()",
            "tags = get_list_or_404(Tag, owner=user)",
            "    model = Tag",
        ]:
            with self.subTest(line=line):
                self.assertTrue(any(p.search(line) for p in UNSCOPED))
        for line in [
            "todos = Todo.objects.for_user(request.user).completed()",
            "todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)",
            "step = get_object_or_404(todo.subtasks, pk=subtask_pk)",
            "SEARCH_MAX_LENGTH = Todo._meta.get_field('title').max_length",
            "todos = get_list_or_404(Todo.objects.for_user(request.user))",
            "lists = TodoList.objects.for_user(request.user)",
            "first = TodoList.objects.owned_by(request.user).first()",
            "TodoList.objects.create_default(user)",
            "get_object_or_404(TodoList.objects.for_user(request.user), pk=list_id)",
            "get_object_or_404(TodoList.objects.owned_by(request.user), pk=list_id)",
            "Tag.objects.owned_by(owner).get_or_create(owner=owner, name=name)",
            "model = TagAdmin",
            "todos = todos.filter(tags__name=tag)",
        ]:
            with self.subTest(line=line):
                self.assertFalse(any(p.search(line) for p in UNSCOPED))
