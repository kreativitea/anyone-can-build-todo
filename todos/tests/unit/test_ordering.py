"""Reorder (16): moving a to-do up or down in "My order" (todos/ordering.py)."""

from django.test import TestCase

from todos.models import Todo, TodoList
from todos.tests.integration.helpers import first_list, make_user


class MoveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("ana")
        cls.todo_list = first_list(cls.user)

    def make(self, title, **fields):
        return Todo.objects.create(todo_list=self.todo_list, title=title, **fields)

    def mine(self):
        """Every to-do of the list: the `shown` of a page with no filter or search."""
        return Todo.objects.filter(todo_list=self.todo_list)

    def order(self, todo_list=None):
        """The titles of a list in My order."""
        rows = Todo.objects.filter(todo_list=todo_list or self.todo_list)
        return list(rows.in_my_order().values_list("title", flat=True))

    def positions(self):
        return dict(self.mine().values_list("title", "position"))

    def move(self, todo, direction, shown=None):
        # Imported here, so only these tests fail while todos.ordering is missing.
        from todos.ordering import move

        move(todo, self.mine() if shown is None else shown, direction)

    def test_move_up_and_down_swap_with_the_neighbour(self):
        a, _b, c = self.make("A"), self.make("B"), self.make("C")
        self.move(c, "up")
        self.assertEqual(self.order(), ["A", "C", "B"])
        self.move(a, "down")
        self.assertEqual(self.order(), ["C", "A", "B"])

    def test_move_at_the_ends_changes_nothing(self):
        a, _b, c = self.make("A"), self.make("B"), self.make("C")
        before = self.positions()
        self.move(a, "up")
        self.move(c, "down")
        self.assertEqual(self.positions(), before)

    def test_move_jumps_over_a_hidden_row(self):
        self.make("A")
        x = self.make("X")
        b = self.make("B")
        x_before = Todo.objects.get(pk=x.pk).position
        shown = self.mine().exclude(pk=x.pk)  # a filter hides X
        self.move(b, "up", shown)
        self.assertEqual(self.order(), ["B", "X", "A"])
        self.assertEqual(Todo.objects.get(pk=x.pk).position, x_before)

    def test_move_renumbers_a_tie_first(self):
        a, b, c = self.make("A"), self.make("B"), self.make("C")
        Todo.objects.filter(pk__in=[a.pk, b.pk]).update(position=1)
        self.move(c, "up")
        self.assertEqual(self.order(), ["A", "C", "B"])
        self.assertEqual(sorted(self.positions().values()), [1, 2, 3])

    def test_move_numbers_an_empty_position_first(self):
        self.make("A")
        self.make("B")
        # bulk_create does not call save(): no position.
        [c] = Todo.objects.bulk_create(
            [Todo(todo_list=self.todo_list, owner=self.user, title="C")]
        )
        self.assertIsNone(Todo.objects.get(pk=c.pk).position)
        self.move(c, "up")
        self.assertEqual(self.order(), ["A", "C", "B"])
        self.assertEqual(sorted(self.positions().values()), [1, 2, 3])

    def test_move_stays_with_the_open_or_the_completed_rows(self):
        # Completed to-dos go last in every sort (owner decision), so a move
        # never swaps an open to-do with a completed one: it would change
        # nothing on the screen.
        self.make("A")
        b = self.make("B")
        x = self.make("X", done=True)
        before = self.positions()
        self.move(b, "down")
        self.move(x, "up")
        self.assertEqual(self.positions(), before)
        self.move(b, "up")
        self.assertEqual(self.order(), ["B", "A", "X"])

    def test_move_never_touches_another_list(self):
        work = TodoList.objects.create(owner=self.user, name="Work")
        self.make("A")
        Todo.objects.create(todo_list=work, title="Report")
        b = self.make("B")
        before = list(Todo.objects.filter(todo_list=work).values())
        self.move(b, "up")
        self.assertEqual(self.order(), ["B", "A"])
        self.assertEqual(list(Todo.objects.filter(todo_list=work).values()), before)
        self.assertEqual(self.order(work), ["Report"])
