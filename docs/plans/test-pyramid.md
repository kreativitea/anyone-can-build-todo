# Plan: a test pyramid

Status: **done**, on the branch `test-pyramid`. Done before [the due-date plan](due-date.md), so
its tests go into the right place from the start. See "What happened" at the end.

## What we want

1. A **test pyramid**: many small, fast tests at the bottom, and only a few big, slow tests at the
   top. Fast tests tell us quickly that something broke. A slow test in a real browser tells us the
   whole app still works for a person.
2. **A summary for each level** at the end of every test run, like this:

   ```text
   CUJ:          1 passed
   Integration: 10 passed
   Unit:        35 passed
   ```

   (These numbers are an example. Today we will have fewer tests.)
3. **Tests that run in parallel** — at the same time, on several CPU cores — when that is faster.

This plan changes **no behaviour** of the app. It only moves the tests we have, adds new ones, and
changes how they run.

## The three levels

The **folder** a test is in decides its level. Nobody has to label a test by hand.

| Level | Folder | How many | What it uses | Speed |
|---|---|---|---|---|
| **CUJ** (top) | `todos/tests/cuj/` | 1 | Django's test client (a real browser until the "Later change" below) | milliseconds |
| **Integration** (middle) | `todos/tests/integration/` | most | Django's test client | milliseconds |
| **Unit** (bottom) | `todos/tests/unit/` | a few | one piece alone (the model, later also the test helpers) | milliseconds |

```text
todos/tests/
├── __init__.py
├── cuj/
│   ├── __init__.py
│   └── test_journeys.py
├── integration/
│   ├── __init__.py
│   └── test_views.py
└── unit/
    ├── __init__.py
    └── test_models.py
```

Each `__init__.py` is an empty file. Django needs it to find the tests in a folder.

### Top: CUJ tests

A **CUJ** (critical user journey) is the most important thing a person does with the app, tested
from start to finish in a real browser, the way a person would do it.

Our one journey, `test_plan_and_finish_a_todo`:

1. Open the list. It says "Nothing to do yet".
2. Type "Buy milk" and press Add. "Buy milk" is on the list.
3. Press Done. The title is crossed out, and the button says Undo.
4. Press Undo. The title is not crossed out.
5. Press Delete. The list says "Nothing to do yet" again.

**The tool: Playwright.** Playwright is a library that controls a real browser from Python. We use
it with `StaticLiveServerTestCase`, a Django test class that starts a real server while the test
runs. We do not need pytest: Django's own test runner is enough.

A sketch of the test:

```python
import os

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright


class JourneyTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        # Playwright runs an event loop, and Django refuses database work while
        # one is running. That is a safety check for real async code; this test
        # has none, so turning it off here is safe.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def test_plan_and_finish_a_todo(self):
        page = self.browser.new_page()
        page.goto(self.live_server_url)
        expect(page.get_by_text("Nothing to do yet")).to_be_visible()
        page.get_by_label("New to-do").fill("Buy milk")
        page.get_by_role("button", name="Add").click()
        ...
```

`expect(...)` waits a little for the page to change, so the test does not fail just because the
browser is slow.

### Middle: integration tests

These send requests with Django's **test client** — a pretend browser inside the test, with no
real server. Each request goes through the URL, the view, the form, the template and the database
together. All 5 tests we have today are this kind.

Form rules (an empty title, spaces around a title, and later the date) are tested here too, through
a request. Django's test client is fast, and this way each test checks the whole path a person
uses. If a form rule gets complicated later, we can add a form unit test then.

**New tests**, for rules in `AGENTS.md` that nothing tests today:

| Test | What it checks |
|---|---|
| `test_get_cannot_change_data` | a `GET` to add, toggle or delete is refused with status 405, and nothing changes. One test, with a `subTest` for each address. |
| `test_toggle_missing_todo_is_404` | toggling a to-do that does not exist gives status 404 |
| `test_delete_missing_todo_is_404` | deleting a to-do that does not exist gives status 404 |

### Bottom: unit tests

These test the `Todo` model alone, with no request and no page.

| Test | What it checks |
|---|---|
| `test_str_is_the_title` | `str(todo)` gives the title (the admin uses this) |
| `test_new_todo_is_not_done` | a new to-do has `done=False` |
| `test_list_is_oldest_first` | `Todo.objects.all()` gives the oldest to-do first |

## The summary for each level

A **test runner** is the program that finds the tests, runs them, and prints the result. Django's
is called `DiscoverRunner`. We make a small one of our own, built on top of it, in a new file
`config/test_runner.py`, and tell Django to use it in `config/settings.py`:

```python
TEST_RUNNER = "config.test_runner.LevelTestRunner"
```

How it works:

- A **result** object is told about each test as it finishes: passed, failed, error, or skipped.
  Our result object also counts each one by **level**.
- The level comes from the test's module name. `todos.tests.unit.test_models` has `unit` in it, so
  it is a unit test.
- A test in none of the three folders is counted as **Other**. Then the runner prints a warning,
  so a test in the wrong place is easy to notice.
- After all tests finish, the runner prints one line for each level. A line shows only the counts
  that are not zero, for example `Integration: 9 passed, 1 failed`.
- It works with parallel runs (below). In parallel, each worker sends its results back to the main
  process, and our result object counts them there.

A sketch:

```python
import unittest
from collections import Counter

from django.test.runner import DiscoverRunner

LEVELS = {"cuj": "CUJ", "integration": "Integration", "unit": "Unit"}


def level_of(test):
    test = getattr(test, "test_case", test)  # a failed subTest points to its test
    parts = type(test).__module__.split(".")
    return next((name for key, name in LEVELS.items() if key in parts), "Other")


class LevelResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = Counter()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed[level_of(test)] += 1


class LevelTestRunner(DiscoverRunner):
    def get_resultclass(self):
        return LevelResult

    def run_suite(self, suite, **kwargs):
        result = super().run_suite(suite, **kwargs)
        # Count result.failures, result.errors and result.skipped by level too,
        # then print one line per level.
        ...
        return result
```

## Running in parallel

Django can already do this: `manage.py test --parallel auto` starts one **worker** (a separate
Python process) for each CPU core. Each worker gets its own copy of the test database, so tests in
different workers cannot change each other's data.

Some things to know:

- Django gives each worker whole **test classes**, not single tests. Tests in one class always run
  one after another.
- **With few, fast tests, parallel can be slower.** Starting each worker takes about a second, and
  our unit and integration tests take a fraction of a second together. The real gain is that the
  **slow browser test runs at the same time as the rest**, not after them. So we **measure both
  ways** (see the steps) and keep parallel only where it is faster.
- **`tblib`** is a small package that lets a worker send the full error message of a failed test
  back to the main process. Without it, Django cannot show a failure from a parallel run properly.
  We add it as a tool for development only.
- The browser test starts its own server and browser inside its worker, so it works in parallel
  too.

## Commands

| Command | What it runs | When |
|---|---|---|
| `make test` | unit + integration, in parallel | all the time, while working |
| `make test-cuj` | only the CUJ test | after a change to a page |
| `make check` | the commit checks, then **every** test, in parallel | before every commit |

`make test` chooses the levels by folder, with no extra labels:

```bash
uv run python manage.py test --parallel auto todos.tests.unit todos.tests.integration
```

CI runs every test, like `make check`. CI is the set of checks GitHub runs on every push, in
`.github/workflows/check.yml`. The commit checks in `.pre-commit-config.yaml` do **not** change:
they run no tests.

## "Show it failing" for tests that pass at once

`AGENTS.md` says to show a test failing before a change. This plan changes no behaviour, so every
new test passes at once. To prove a new test can catch a bug, **break the code on purpose for a
moment**:

- Remove `@require_POST` from `todo_delete`. `test_get_cannot_change_data` fails. Put it back.
- In the template, change "Done" to "Finish". The CUJ test fails. Put it back.

The same broken code also checks the summary. The failure must appear on the right line, for
example `Integration: 5 passed, 1 failed`, both with and without `--parallel`.

We do not commit the broken code. `git diff` must be empty afterwards.

## The changes, one file at a time

1. **`pyproject.toml`, `uv.lock`** — add Playwright and tblib as tools for development only:
   `uv add --dev playwright tblib`.
2. **The browser** — `uv run playwright install chromium`. This **downloads** a browser (about
   150 MB) into a cache folder outside this project. Ask the person before running it.
3. **`todos/tests.py` → `todos/tests/`** — make the folders above. Move the 5 tests to
   `integration/test_views.py` **without changing them**, with `git mv`, so git keeps their
   history.
4. **`config/test_runner.py`** — new: the runner that prints the summary for each level.
5. **`config/settings.py`** — add `TEST_RUNNER = "config.test_runner.LevelTestRunner"`.
6. **`Makefile`** — change `test`, add `test-cuj`, and run every test in `check`, as in
   "Commands". `setup` also runs `uv run playwright install chromium`. Update `make help`.
7. **`.github/workflows/check.yml`** — before the tests, add
   `uv run playwright install --with-deps chromium`. (`--with-deps` also installs the system
   libraries the browser needs on Linux.) The test step becomes
   `uv run python manage.py test --parallel auto`.
8. **`AGENTS.md`**:
   - File table: replace the `todos/tests.py` row with the three folders, and add
     `config/test_runner.py`.
   - Commands: add `make test-cuj`, and say `make test` skips the CUJ test.
   - Rules: a new rule, "Put a test in the lowest level that can catch the bug. Its folder sets the
     level. Add a CUJ test only for a new journey a person takes."
   - Setup: `make setup` also downloads the browser.

## Steps, in order

1. Move the 5 tests into `todos/tests/integration/test_views.py`. Run
   `uv run python manage.py test`: 5 pass. (Nothing else has changed yet, so this shows the move
   worked.)
2. Add the 3 unit tests and the 3 new integration tests. Run them: 11 pass.
3. Add the test runner and the setting. Run the tests: the summary shows `Integration: 8 passed`
   and `Unit: 3 passed`.
4. Ask the person, then add Playwright and tblib, and download the browser.
5. Write the CUJ test. Run it: `CUJ: 1 passed`.
6. Show that each new test can fail, and that the failure is on the right summary line, with and
   without `--parallel` (see "Show it failing"). Then put the code back.
7. **Measure.** Time every test with and without `--parallel auto`, and do the same for `make test`
   alone. Write the times in this plan. Keep `--parallel auto` only where it is faster.
8. Change the `Makefile`, the CI file and `AGENTS.md`.
9. Run `make check`: all 12 tests pass. Commit.
10. Push, and check that CI passes with the browser test.

## What happened

Differences from the plan:

- Moving `todos/tests.py` needed one line changed: `from .models import Todo` became
  `from todos.models import Todo`, because `.` means "the folder this file is in", and the file had
  moved deeper. The tests themselves did not change.
- The CUJ test waits at most **5 seconds** for each step (`page.set_default_timeout(5_000)`).
  Playwright's default is 30 seconds, so a broken page took 31 seconds to fail.
- The summary says `1 error`, not `1 errors`.

"Show it failing": removing `@require_POST` from `todo_delete` made
`test_get_cannot_change_data` fail, and renaming "Done" to "Finish" made the CUJ test fail. Both
showed on the right summary line, with and without `--parallel`. A test file put outside the three
folders showed as `Other`, with the warning. The code was put back afterwards.

**Measured times** (3 runs each, on a laptop with 10 CPU cores):

| What | One at a time | `--parallel auto` |
|---|---|---|
| `make test` (unit + integration, 11 tests) | 0.3 s | 0.6 s |
| every test (12, with the browser) | 1.3 s | 1.6 s |

Parallel is slower today, as expected: starting 10 workers costs more than 12 quick tests. **We keep
`--parallel auto` anyway**, because many features are coming, and it will be faster once there are
more tests.

**One parallel run failed** (1 of 3 timed runs), and we did not see why: its output was not saved.
It did not happen again in 40 more runs. If it comes back, save the output and look for the cause.

## Risks

- **A slow or flaky browser test.** A flaky test sometimes passes and sometimes fails with no code
  change. We use `expect(...)`, which waits for the page, and never a fixed `sleep`. We keep only
  one CUJ test.
- **Our own test runner is code we must keep working.** It is small, and it is built on Django's,
  so it changes only the summary. If a new Django version breaks it, we can delete the
  `TEST_RUNNER` line, and the tests still run, without the summary.
- **CI gets slower** by about a minute, because it downloads the browser each time. That is fine
  for now. We can cache it later if it becomes a problem.

## Later change: the CUJ level uses the test client

On the branch `test/cuj-client`, the CUJ level stopped using a real browser. The journey test now
uses Django's **test client**, like the integration tests. Playwright is removed from the project,
so `make setup` and CI no longer download a browser.

Why:

- **The browser test was flaky.** It failed about 1 run in 10, and we never found why.
- **The owner decided:** no real-browser tests. Things only a browser shows (CSS, layout, focus)
  are checked by eye, with a screenshot.

The journey has the same steps as before. Each step reads the form from the page (its address, its
fields and the CSRF token), posts it with CSRF checks on (`Client(enforce_csrf_checks=True)`),
follows the redirect, and checks the to-do's row exactly (`html=True`). So it still proves that the
page's own forms work. The helper `page_forms` in `todos/tests/integration/helpers.py` reads the
forms, and sends what a browser would send:

- a repeated name sends every value (like the ids of delete completed);
- a `<textarea>` sends its text, and a `<select>` sends the selected option, or the first one;
- an unchecked checkbox or radio, or a disabled field, sends nothing;
- the pressed button sends its own name and value;
- a form with no `action` posts to the page's own address.

Unit tests in `todos/tests/unit/test_helpers.py` check these rules on small pieces of HTML.

The browser journey also proved that the fields have the right accessible names (the names a
screen reader reads: "New to-do", "Due date"). An integration test,
`test_add_form_fields_have_accessible_names`, now checks those fields exactly.

The three levels, the folders and the summary for each level stay the same. `make test-cuj` still
runs only the CUJ level; it now takes milliseconds.
