"""Runs the tests like Django does, then prints how each level did.

The folder a test is in sets its level: todos/tests/cuj, integration or unit.
"""

import sys
import unittest
from collections import Counter, defaultdict

from django.test.runner import DiscoverRunner

LEVELS = {"cuj": "CUJ", "integration": "Integration", "unit": "Unit"}
OTHER = "Other"


def level_of(test):
    # id() names the module, even for a subTest or a failed setUpClass.
    test_id = test.id()
    for folder, name in LEVELS.items():
        if f".{folder}." in test_id:
            return name
    return OTHER


class LevelResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = Counter()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed[level_of(test)] += 1


class LevelTestRunner(DiscoverRunner):
    def get_resultclass(self):
        # Keep Django's own result for --debug-sql and --pdb.
        return super().get_resultclass() or LevelResult

    def run_suite(self, suite, **kwargs):
        result = super().run_suite(suite, **kwargs)
        if isinstance(result, LevelResult):
            print_summary(result)
        return result


def print_summary(result):
    counts = defaultdict(Counter)
    for level, number in result.passed.items():
        counts[level]["passed"] = number
    for kind, tests in [
        ("failed", result.failures),
        ("errors", result.errors),
        ("skipped", result.skipped),
    ]:
        for test, _ in tests:
            counts[level_of(test)][kind] += 1

    out = sys.stderr
    out.write("\n")
    for level in [*LEVELS.values(), OTHER]:
        if level in counts:
            parts = [
                f"{n} {'error' if kind == 'errors' and n == 1 else kind}"
                for kind, n in counts[level].items()
                if n
            ]
            out.write(f"{level + ':':<13}{', '.join(parts)}\n")
    if OTHER in counts:
        out.write(
            "Warning: some tests are not in todos/tests/cuj, integration or unit.\n"
        )
    out.flush()
