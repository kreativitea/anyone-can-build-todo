"""Reorder (16): many requests at the same time, on a real database FILE.

The test database is in memory, so this test makes its own small SQLite file
with the project's settings (IMMEDIATE transactions), under a second database
name. Four threads add to-dos and four threads move one, all at once. Each
thread has its own connection, like each request on a real server.
"""

import copy
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connections

from todos.models import Todo, TodoList
from todos.ordering import move
from todos.tests.integration.helpers import TEST_PASSWORD

ALIAS = "concurrency_file"
ADDERS = 4
MOVERS = 4
ROUNDS = 10


class ConcurrencyTests(unittest.TestCase):
    # A plain unittest TestCase: Django's test cases refuse threads, and a
    # database name that is not in the settings when the tests are found.

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp())
        config = copy.deepcopy(connections.settings["default"])
        config["NAME"] = str(cls.folder / "db.sqlite3")
        config["TEST"] = {**config.get("TEST", {}), "NAME": config["NAME"]}
        connections.settings[ALIAS] = config
        super().setUpClass()
        # The tables of today's models. Not `migrate`: the old data
        # migrations always use the default database.
        with connections[ALIAS].schema_editor() as editor:
            for model in apps.get_models():
                editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        connections[ALIAS].close()
        del connections[ALIAS]
        del connections.settings[ALIAS]
        shutil.rmtree(cls.folder)

    def make_list(self, username):
        """A new user on the file database, with one list."""
        user = (
            get_user_model()
            .objects.db_manager(ALIAS)
            .create_user(username, password=TEST_PASSWORD)
        )
        return TodoList.objects.using(ALIAS).create(owner=user, name="Mine")

    def test_add_and_move_use_a_transaction_on_their_own_database(self):
        # Without `using`, atomic() opens its transaction on the DEFAULT
        # database, and the to-do's own database has none. Every query on
        # the to-dos table must run inside a transaction of ITS database.
        todo_list = self.make_list("ben")
        connection = connections[ALIAS]
        outside = []

        def watch(execute, sql, params, many, context):
            if '"todos_todo"' in sql and not connection.in_atomic_block:
                outside.append(sql)
            return execute(sql, params, many, context)

        first = Todo.objects.using(ALIAS).create(todo_list=todo_list, title="A")
        second = Todo.objects.using(ALIAS).create(todo_list=todo_list, title="B")
        shown = Todo.objects.using(ALIAS).filter(todo_list=todo_list)
        with connection.execute_wrapper(watch):
            Todo.objects.using(ALIAS).create(todo_list=todo_list, title="C")
            move(second, shown, "up")
        self.assertEqual(outside, [])
        order = shown.in_my_order().values_list("pk", flat=True)
        self.assertEqual(list(order)[:2], [second.pk, first.pk])

    def test_adds_and_moves_at_the_same_time(self):
        todo_list = self.make_list("ana")
        todos = [
            Todo.objects.using(ALIAS).create(todo_list=todo_list, title=f"T{i}")
            for i in range(6)
        ]
        errors = []
        start = threading.Barrier(ADDERS + MOVERS)

        def adder(number):
            try:
                mine = TodoList.objects.using(ALIAS).get(pk=todo_list.pk)
                start.wait()
                for k in range(ROUNDS):
                    Todo.objects.using(ALIAS).create(
                        todo_list=mine, title=f"Add {number}-{k}"
                    )
            except Exception as error:
                errors.append(repr(error))
            finally:
                connections[ALIAS].close()

        def mover(number):
            try:
                start.wait()
                for k in range(ROUNDS):
                    todo = Todo.objects.using(ALIAS).get(pk=todos[3].pk)
                    shown = Todo.objects.using(ALIAS).filter(todo_list=todo_list)
                    move(todo, shown, "up" if (number + k) % 2 else "down")
            except Exception as error:
                errors.append(repr(error))
            finally:
                connections[ALIAS].close()

        threads = [threading.Thread(target=adder, args=(i,)) for i in range(ADDERS)]
        threads += [threading.Thread(target=mover, args=(i,)) for i in range(MOVERS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])  # never "database is locked"
        positions = list(
            Todo.objects.using(ALIAS)
            .filter(todo_list=todo_list)
            .values_list("position", flat=True)
        )
        self.assertEqual(len(positions), 6 + ADDERS * ROUNDS)
        self.assertEqual(len(set(positions)), len(positions))  # no number twice
        self.assertNotIn(None, positions)
