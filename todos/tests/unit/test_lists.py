"""Lists (feature 13): the TodoList table, who may use a list, and the list forms.

Ana has "My to-dos" and "Work". Ben has "My to-dos" and "Secret".
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from todos.forms import TodoEditForm, TodoForm
from todos.models import Subtask, Todo, TodoList
from todos.tests.integration.helpers import first_list, make_user


class ListTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")
        cls.ben = make_user("ben")
        cls.anas = first_list(cls.ana)
        cls.work = TodoList.objects.create(owner=cls.ana, name="Work")
        cls.bens = first_list(cls.ben)
        cls.secret = TodoList.objects.create(owner=cls.ben, name="Secret")


class TodoListModelTests(ListTestCase):
    def test_lists_for_user_are_only_their_own(self):
        for name in ["for_user", "owned_by"]:
            with self.subTest(queryset=name):
                lists = getattr(TodoList.objects, name)(self.ana)
                self.assertEqual(list(lists), [self.anas, self.work])

    def test_save_sets_the_owner_from_the_list(self):
        # The OWNERSHIP rule: the owner always follows the list, whatever was set.
        todo = Todo(title="x", todo_list=self.work, owner=self.ben)
        todo.save()
        todo.refresh_from_db()
        self.assertEqual(todo.owner, self.ana)
        todo.todo_list = self.secret
        todo.save()
        todo.refresh_from_db()
        self.assertEqual(todo.owner, self.ben)

    def test_todos_for_user_go_through_the_list(self):
        # A guard for sharing (20): the LIST decides who sees a to-do. update()
        # skips save(), so this row breaks the rule on purpose.
        todo = Todo.objects.create(title="Ben's secret", todo_list=self.secret)
        Todo.objects.filter(pk=todo.pk).update(owner=self.ana)
        self.assertEqual(list(Todo.objects.for_user(self.ben)), [todo])
        self.assertEqual(list(Todo.objects.for_user(self.ana)), [])

    def test_next_repeat_stays_in_the_same_list(self):
        bins = Todo.objects.create(
            title="Bins",
            todo_list=self.work,
            repeat="weekly",
            due_date=date(2026, 10, 12),
        )
        self.assertEqual(bins.next_copy().todo_list, self.work)

    def test_create_default_makes_my_todos(self):
        cai = make_user("cai")
        TodoList.objects.filter(owner=cai).delete()
        made = TodoList.objects.create_default(cai)
        self.assertEqual(
            list(TodoList.objects.filter(owner=cai).values_list("name", "owner")),
            [("My to-dos", cai.pk)],
        )
        self.assertEqual(made.name, "My to-dos")

    def test_make_user_has_my_todos(self):
        cai = make_user("cai")
        self.assertEqual(
            list(TodoList.objects.filter(owner=cai).values_list("name", flat=True)),
            ["My to-dos"],
        )

    def test_name_unique_per_owner_ignoring_case(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TodoList.objects.create(owner=self.ana, name="work")

    def test_two_people_may_use_the_same_name(self):
        TodoList.objects.create(owner=self.ben, name="Work")
        self.assertEqual(TodoList.objects.filter(name="Work").count(), 2)

    def test_constraint_message(self):
        with self.assertRaises(ValidationError) as caught:
            TodoList(owner=self.ana, name="WORK").validate_constraints()
        self.assertEqual(
            caught.exception.messages, ["You already have a list with this name."]
        )

    def test_deleting_a_list_deletes_its_todos(self):
        report = Todo.objects.create(title="Write report", todo_list=self.work)
        Subtask.objects.create(todo=report, title="Outline")
        milk = Todo.objects.create(title="Buy milk", todo_list=self.anas)
        self.work.delete()
        self.assertFalse(TodoList.objects.filter(pk=self.work.pk).exists())
        self.assertEqual(list(Todo.objects.all()), [milk])
        self.assertFalse(Subtask.objects.exists())
        self.assertEqual(list(TodoList.objects.filter(owner=self.ana)), [self.anas])

    def test_deleting_a_user_deletes_their_lists_and_todos(self):
        milk = Todo.objects.create(title="Buy milk", todo_list=self.anas)
        Todo.objects.create(title="Ben's secret", todo_list=self.secret)
        self.ben.delete()
        self.assertEqual(list(TodoList.objects.all()), [self.anas, self.work])
        self.assertEqual(list(Todo.objects.all()), [milk])


class TodoListFormTests(ListTestCase):
    # TodoListForm is imported in each test, so only these fail while it is missing.

    def test_list_form_refuses_a_name_already_used(self):
        from todos.forms import TodoListForm

        form = TodoListForm({"name": " WORK "}, owner=self.ana)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors, {"name": ['You already have a list called "WORK".']}
        )

    def test_list_form_may_rename_a_list_to_itself(self):
        from todos.forms import TodoListForm

        form = TodoListForm({"name": "work"}, instance=self.work, owner=self.ana)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_form_allows_a_name_another_person_uses(self):
        from todos.forms import TodoListForm

        form = TodoListForm({"name": "Secret"}, owner=self.ana)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_form_needs_a_name_up_to_50(self):
        from todos.forms import TodoListForm

        cases = [
            ("   ", "This field is required."),
            (
                "a" * 51,
                "Ensure this value has at most 50 characters (it has 51).",
            ),
        ]
        for name, error in cases:
            with self.subTest(name=name):
                form = TodoListForm({"name": name}, owner=self.ana)
                self.assertEqual(form.errors, {"name": [error]})
        form = TodoListForm({"name": "a" * 50}, owner=self.ana)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_form_needs_the_owner(self):
        # Keyword-only: forgetting the owner is an error at once.
        from todos.forms import TodoListForm

        with self.assertRaises(TypeError):
            TodoListForm({"name": "Home"})


class TodoFormListFieldTests(ListTestCase):
    def test_add_form_has_no_list_field(self):
        # The add form posts to /lists/<id>/add/: the address says the list.
        self.assertNotIn("todo_list", TodoForm().fields)

    def test_edit_form_offers_only_own_lists(self):
        field = TodoEditForm(user=self.ana).fields["todo_list"]
        self.assertEqual(list(field.queryset), [self.anas, self.work])
        self.assertIsNone(field.empty_label)

    def test_edit_form_refuses_another_users_list(self):
        todo = Todo.objects.create(title="x", todo_list=self.anas)
        form = TodoEditForm(
            {"title": "x", "todo_list": self.secret.pk}, instance=todo, user=self.ana
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                "todo_list": [
                    "Select a valid choice. That choice is not one of the "
                    "available choices."
                ]
            },
        )

    def test_edit_form_without_a_list_keeps_the_list(self):
        # A hand-made post without the box (a browser always sends it) keeps
        # the to-do where it is, like a missing priority is Medium.
        todo = Todo.objects.create(title="x", todo_list=self.work)
        form = TodoEditForm({"title": "y"}, instance=todo, user=self.ana)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().todo_list, self.work)
