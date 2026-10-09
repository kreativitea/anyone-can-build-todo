"""Subtasks (feature 15): the Subtask table and the step counts."""

from django.test import TestCase
from django.utils import timezone

from todos.models import Subtask, Todo
from todos.tests.integration.helpers import first_list, make_user


class SubtaskModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user()
        cls.todo_list = first_list(cls.user)

    def setUp(self):
        self.cake = Todo.objects.create(todo_list=self.todo_list, title="Bake a cake")
        Subtask.objects.create(todo=self.cake, title="Buy flour", done=True)
        Subtask.objects.create(todo=self.cake, title="Buy eggs")
        Subtask.objects.create(todo=self.cake, title="Bake")
        self.shop = Todo.objects.create(todo_list=self.todo_list, title="Shop")

    def test_with_subtask_progress_counts_steps(self):
        todos = {t.title: t for t in Todo.objects.with_subtask_progress()}
        self.assertEqual(todos["Bake a cake"].subtask_count, 3)
        self.assertEqual(todos["Bake a cake"].subtask_done_count, 1)
        self.assertEqual(todos["Shop"].subtask_count, 0)
        self.assertEqual(todos["Shop"].subtask_done_count, 0)

    def test_counts_stay_right_when_the_query_joins_again(self):
        # A filter through the steps after the counts JOINs the steps a second
        # time: each step is on two lines. distinct=True still counts it once.
        # (Tags, 14, make the same kind of second JOIN.)
        todos = Todo.objects.with_subtask_progress().filter(
            subtasks__title__startswith="Buy"
        )
        cake = todos.distinct().get()
        self.assertEqual((cake.subtask_done_count, cake.subtask_count), (1, 3))

    def test_deleting_a_todo_deletes_its_steps(self):
        Subtask.objects.create(todo=self.shop, title="Milk")
        self.cake.delete()
        titles = list(Subtask.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["Milk"])

    def test_steps_are_oldest_first(self):
        # The same created_at can happen in a fast test: the id breaks the tie.
        Subtask.objects.filter(todo=self.cake).update(created_at=timezone.now())
        self.assertEqual(
            [s.title for s in self.cake.subtasks.all()],
            ["Buy flour", "Buy eggs", "Bake"],
        )

    def test_str_is_the_title(self):
        self.assertEqual(str(Subtask(title="Bake")), "Bake")
