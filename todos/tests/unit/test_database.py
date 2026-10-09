"""Reorder (16): the database settings that a move needs."""

from django.conf import settings
from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def test_sqlite_transactions_are_immediate(self):
        # A transaction takes the write lock at its start. Then a second
        # request that reads and writes WAITS for the first one, instead of
        # failing at once with "database is locked". A real two-thread test
        # needs a database file; the test database is in memory. This test
        # keeps the setting from being removed.
        options = settings.DATABASES["default"]["OPTIONS"]
        self.assertEqual(options["transaction_mode"], "IMMEDIATE")
