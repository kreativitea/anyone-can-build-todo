"""Reorder (16): the two position migrations, run for real on the test database.

Like test_lists_migration.py: the migrations are found by the END of their
name, so the merge queue can renumber them.
"""

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from todos.tests.integration.test_owner_migration import migration_ending


class PositionMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.add_position = migration_ending(executor, "_todo_position")
        self.number = migration_ending(executor, "_number_todos")
        parents = executor.loader.graph.node_map[self.add_position].parents
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

    def test_old_todos_are_numbered_per_list_by_age(self):
        apps = self.migrate_to(self.before)
        User = apps.get_model("auth", "User")
        OldList = apps.get_model("todos", "TodoList")
        OldTodo = apps.get_model("todos", "Todo")
        ana = User.objects.create(username="ana")
        # A historical model has no save() of ours: name_key is set by hand.
        home = OldList.objects.create(owner=ana, name="Home", name_key="home")
        work = OldList.objects.create(owner=ana, name="Work", name_key="work")

        def make(todo_list, title):
            return OldTodo.objects.create(owner=ana, todo_list=todo_list, title=title)

        h1, w1, h2, w2, h0 = (
            make(home, "H1"),
            make(work, "W1"),
            make(home, "H2"),
            make(work, "W2"),
            make(home, "H0"),
        )
        # H0 was added first, so it is first in Home.
        OldTodo.objects.filter(pk=h0.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        apps = self.migrate_to(self.number)

        Todo = apps.get_model("todos", "Todo")
        positions = dict(Todo.objects.values_list("pk", "position"))
        self.assertEqual(
            [positions[t.pk] for t in [h0, h1, h2, w1, w2]], [1, 2, 3, 1, 2]
        )

        # Going back works: the data step does nothing, then the field goes.
        apps = self.migrate_to(self.before)
        fields = [f.name for f in apps.get_model("todos", "Todo")._meta.fields]
        self.assertNotIn("position", fields)
