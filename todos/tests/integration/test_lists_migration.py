"""The three list migrations (feature 13), run for real on the test database.

Like test_owner_migration.py: a TransactionTestCase, Django's MigrationExecutor,
and the migrations found by the END of their name, so the merge queue can
renumber them. No production data yet (owner decision): old to-dos without a
list are deleted, and old users get no list (no back-filling).
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from todos.tests.integration.test_owner_migration import migration_ending


class ListMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.add_list = migration_ending(executor, "_todolist")
        self.delete_old = migration_ending(executor, "_delete_todos_without_list")
        self.list_required = migration_ending(executor, "_todo_list_required")
        # The migration just before "add the list".
        parents = executor.loader.graph.node_map[self.add_list].parents
        [self.before] = [node.key for node in parents if node.key[0] == "todos"]

    def tearDown(self):
        # Leave the database complete, for the next test.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate_to(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def test_old_todos_without_a_list_are_deleted(self):
        apps = self.migrate_to(self.add_list)
        User = apps.get_model("auth", "User")
        OldTodo = apps.get_model("todos", "Todo")
        OldSubtask = apps.get_model("todos", "Subtask")
        OldList = apps.get_model("todos", "TodoList")
        ana = User.objects.create(username="ana")
        cake = OldTodo.objects.create(owner=ana, title="Bake a cake")
        OldSubtask.objects.create(todo=cake, title="Buy flour")
        OldTodo.objects.create(owner=ana, title="Buy milk")
        work = OldList.objects.create(owner=ana, name="Work")
        report = OldTodo.objects.create(owner=ana, title="Write report", todo_list=work)

        apps = self.migrate_to(self.delete_old)

        Todo = apps.get_model("todos", "Todo")
        self.assertEqual(list(Todo.objects.values_list("pk", flat=True)), [report.pk])
        self.assertEqual(apps.get_model("todos", "Subtask").objects.count(), 0)
        # The user stays, and gets no new list: no back-filling.
        self.assertTrue(apps.get_model("auth", "User").objects.filter(pk=ana.pk))
        TodoList = apps.get_model("todos", "TodoList")
        self.assertEqual(
            list(TodoList.objects.values_list("name", flat=True)), ["Work"]
        )

        # Going back one step does nothing (noop), and works.
        apps = self.migrate_to(self.add_list)
        self.assertEqual(apps.get_model("todos", "Todo").objects.count(), 1)

        apps = self.migrate_to(self.list_required)
        field = apps.get_model("todos", "Todo")._meta.get_field("todo_list")
        self.assertFalse(field.null)

    def test_the_migrations_can_be_reversed(self):
        apps = self.migrate_to(self.before)
        old_fields = [f.name for f in apps.get_model("todos", "Todo")._meta.fields]
        self.assertNotIn("todo_list", old_fields)
        todos_models = {
            m._meta.model_name
            for m in apps.get_models()
            if m._meta.app_label == "todos"
        }
        self.assertNotIn("todolist", todos_models)

        apps = self.migrate_to(self.list_required)
        new_fields = [f.name for f in apps.get_model("todos", "Todo")._meta.fields]
        self.assertIn("todo_list", new_fields)
