"""The three owner migrations (feature 17), run for real on the test database.

A TransactionTestCase really writes to the database, so it can run migrations.
The MigrationExecutor is Django's own tool that moves the database forward or
back to a named migration. The migrations are found by the END of their name,
not by number, so the merge queue can renumber them.
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


def migration_ending(executor, ending):
    """The one ("todos", name) migration whose name ends with `ending`."""
    found = [
        key
        for key in executor.loader.disk_migrations
        if key[0] == "todos" and key[1].endswith(ending)
    ]
    if len(found) != 1:
        raise AssertionError(f"{len(found)} todos migrations end with {ending!r}")
    return found[0]


class OwnerMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.add_owner = migration_ending(executor, "_todo_owner")
        self.owner_required = migration_ending(executor, "_todo_owner_required")
        # The migration just before "add the owner": the old to-do table.
        self.before = executor.loader.graph.node_map[self.add_owner].parents
        [self.before] = [node.key for node in self.before if node.key[0] == "todos"]

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

    def test_old_todos_without_owner_are_deleted(self):
        apps = self.migrate_to(self.add_owner)
        OldTodo = apps.get_model("todos", "Todo")
        OldSubtask = apps.get_model("todos", "Subtask")
        cake = OldTodo.objects.create(title="Bake a cake")
        OldSubtask.objects.create(todo=cake, title="Buy flour")
        OldTodo.objects.create(title="Buy milk")

        apps = self.migrate_to(self.owner_required)

        self.assertEqual(apps.get_model("todos", "Todo").objects.count(), 0)
        self.assertEqual(apps.get_model("todos", "Subtask").objects.count(), 0)

    def test_the_migrations_can_be_reversed(self):
        apps = self.migrate_to(self.before)
        old_fields = [f.name for f in apps.get_model("todos", "Todo")._meta.fields]
        self.assertNotIn("owner", old_fields)

        apps = self.migrate_to(self.owner_required)
        new_fields = [f.name for f in apps.get_model("todos", "Todo")._meta.fields]
        self.assertIn("owner", new_fields)
