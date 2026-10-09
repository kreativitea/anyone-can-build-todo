"""Reorder (16): the database settings and transactions that a move needs."""

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from todos.models import Todo
from todos.tests.integration.helpers import first_list, make_user


class DatabaseSettingsTests(SimpleTestCase):
    def test_sqlite_transactions_are_immediate(self):
        # A transaction takes the write lock at its start. Then a second
        # request that reads and writes WAITS for the first one, instead of
        # failing at once with "database is locked". The real two-thread test
        # is integration/test_concurrency.py. This test keeps the setting.
        options = settings.DATABASES["default"]["OPTIONS"]
        self.assertEqual(options["transaction_mode"], "IMMEDIATE")


class ConnectionTests(TestCase):
    def test_the_connection_uses_immediate(self):
        # The setting reaches the real connection (Django 5.1+ reads it).
        connection.ensure_connection()
        self.assertEqual(connection.transaction_mode, "IMMEDIATE")


def inside_one_transaction(sqls, wanted):
    """True when every query in `sqls` that `wanted` picks sits between one
    SAVEPOINT and its RELEASE SAVEPOINT.

    In a TestCase every test runs in a transaction, so an inner
    `transaction.atomic()` shows as a SAVEPOINT.
    """
    starts = [i for i, sql in enumerate(sqls) if sql.startswith("SAVEPOINT")]
    ends = [i for i, sql in enumerate(sqls) if sql.startswith("RELEASE SAVEPOINT")]
    picked = [i for i, sql in enumerate(sqls) if wanted(sql)]
    if not (starts and ends and picked):
        return False
    return starts[0] < min(picked) and max(picked) < ends[-1]


class TransactionTests(TestCase):
    """The reads and the writes of a move, and of an add, are one transaction."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("ana")
        cls.todo_list = first_list(cls.user)

    def make(self, title):
        return Todo.objects.create(todo_list=self.todo_list, title=title)

    def test_move_reads_and_swaps_inside_one_transaction(self):
        from todos.ordering import move

        self.make("A")
        self.make("B")
        c = self.make("C")
        shown = Todo.objects.filter(todo_list=self.todo_list)
        with CaptureQueriesContext(connection) as context:
            move(c, shown, "up")
        sqls = [query["sql"] for query in context.captured_queries]
        updates = [sql for sql in sqls if sql.startswith("UPDATE")]
        self.assertEqual(len(updates), 2)  # the swap: two small UPDATEs
        self.assertTrue(
            inside_one_transaction(sqls, lambda sql: '"todos_todo"' in sql), sqls
        )

    def test_add_reads_the_largest_number_and_inserts_inside_one_transaction(self):
        self.make("A")
        with CaptureQueriesContext(connection) as context:
            self.make("B")
        sqls = [query["sql"] for query in context.captured_queries]
        self.assertTrue(any("MAX(" in sql for sql in sqls), sqls)
        self.assertTrue(
            inside_one_transaction(
                sqls, lambda sql: "MAX(" in sql or sql.startswith("INSERT")
            ),
            sqls,
        )
