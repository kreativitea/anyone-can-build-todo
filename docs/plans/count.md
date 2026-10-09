# Plan: show how many to-dos are left

Status: **done**. See "What happened" at the end.

This is feature 12, in wave 1 of [the rollout plan](feature-rollout.md). The merge order in wave 1
is: 5 due date → **12 count** → 11 clear completed → 8 filter.

**The starting point.** This feature starts **after** [the due-date feature](due-date.md) (5) is
merged into `main`. So on our starting point:

- `todos/forms.py` has `TodoForm`.
- `todos/views.py` has a shared helper, `page_context(request, form)`. It makes the dictionary the page
  needs, with one key per line:

  ```python
  def page_context(request, form):
      return {
          "todos": Todo.objects.all(),
          "form": form,
      }
  ```

  Both `todo_list` and the error path of `todo_add` use it.

Every "How it fails today" below is true on **that** starting point. Features 11 and 8 are built at
the same time as this one, by other agents, from the same starting point.

## What we want

Under the list, the page says how many to-dos are **not done yet**, like the well-known example app
TodoMVC:

```text
3 items left
```

When a person presses Done, the number goes down by one. When they press Undo, it goes up again.

## Decisions

- **The words:** `3 items left`, `1 item left` (no "s" for one), `0 items left`. Django's
  `pluralize` filter adds the "s". A **filter** here is a small helper in a template that changes a
  value before it is shown. `pluralize` gives `""` for 1 and `"s"` for every other number.
- **What counts:** every to-do that is **not done**. Done to-dos are not counted.
- **The counting lives on the model.** We add a method `remaining()` to the model's **manager**.
  The manager is the `Todo.objects` part of `Todo.objects.all()`: the object that reads to-dos from
  the database. So `Todo.objects.remaining()` gives the to-dos that are not done. The model is the
  right home for a rule about to-dos, and we can unit-test it alone.
- **The database counts, not Python.** We use `.count()`, which asks the database
  `SELECT COUNT(*) ...` and gets back one number. We do not load every to-do and count them in a
  Python loop: that gets slow when the list is long.
- **An empty list:** no count at all. The page already says "Nothing to do yet", and "0 items left"
  next to it would only repeat that.
- **Every to-do is done:** show `0 items left`. That is useful: it tells the person they are
  finished.
- **"Is the list empty?" is asked about the whole list**, with `Todo.objects.exists()`, not with
  the `todos` that the page shows. Feature 8 (filter) will change `todos` to show only some to-dos.
  If the count used `todos`, choosing a filter with no matches would hide the count, too.
- **A filter does not change the count.** For the same reason, the count is always for the
  **whole** list. This is how TodoMVC works too.
- **The same count on the error page.** When the add form has a mistake (for example a bad date),
  `todo_add` shows the page again. Because both views use `page_context`, the count is there
  without any more work.
- **Where on the page:** a `<div class="list-footer">` just after the list. We call it "the
  footer", but it is a plain `<div>`, not the HTML `<footer>` element: a `<footer>` placed directly
  in `<body>` is read by a screen reader as the footer of the **whole page** (its "contentinfo"
  landmark), which this is not. Feature 11 (clear completed) will put its button in the same
  footer, next to the count.
- **No `aria-live`.** `aria-live` tells a screen reader (a program that reads the page aloud) to
  say a change on the page without the person moving to it. That only matters when a page changes
  **without** loading again. Here every button loads the whole page again, so a screen reader starts
  from the top anyway. `aria-live` would do nothing.

## What we will not do (yet)

- No live update without reloading the page. Today every button reloads the page anyway, so the
  number is always right.
- No count of done to-dos ("2 done"). Only what is left.
- No other languages. The words are English only, like the rest of the page.

## Changes in behaviour

1. A list with at least one to-do shows a footer with `N item(s) left` under the list. Before,
   there was no count.
2. The error page from `todo_add` shows the same footer.

What stays the same: an empty list shows "Nothing to do yet" and no footer. Adding, Done, Undo and
Delete work as before. No new address, no `POST` change, no new field, **no migration**.

## The changes, one file at a time

### 1. `todos/models.py` — the `remaining()` method

A **QuerySet** is Django's name for "a question to the database that gives some to-dos", like
`Todo.objects.all()` or `Todo.objects.filter(done=False)`. We make our own QuerySet class with one
extra method, and turn it into the manager with `as_manager()`:

```python
class TodoQuerySet(models.QuerySet):
    def remaining(self):
        """The to-dos that are not done yet."""
        return self.filter(done=False)


class Todo(models.Model):
    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TodoQuerySet.as_manager()
    ...
```

- Put `TodoQuerySet` **above** `class Todo`, and the line `objects = ...` **after** the fields, so
  the lines that other features add (new fields) do not touch these.
- `remaining()` gives a QuerySet, not a number. So it can be used in more ways later, and the
  caller adds `.count()` when it wants a number.
- `Todo.objects.all()`, `.create()` and the rest work exactly as before. A manager made this way
  has every normal method, plus `remaining()`.
- This makes **no migration**: Django does not save a plain `objects` manager in migrations.
  `make check` runs `makemigrations --check --dry-run`, which proves it.

### 2. `todos/views.py` — two keys in `page_context`

Add two keys **inside** `page_context`, one per line. Nothing else in `views.py` changes:

```python
def page_context(request, form):
    return {
        "todos": Todo.objects.all(),
        "form": form,
        "has_todos": Todo.objects.exists(),
        "remaining_count": Todo.objects.remaining().count(),
    }
```

- `has_todos`: `True` if there is at least one to-do in the whole list. `.exists()` asks the
  database only "is there one?", which is the fastest question.
- `remaining_count`: the number of to-dos that are not done. The database counts them.
- The key is `remaining_count`, and the method is `remaining()`: different names, so nobody mixes
  up the number and the method.
- Because each key is on its own line, features 11 and 8 add their own lines here, and a clash is
  small.

### 3. `todos/templates/todos/todo_list.html` — the page

Just **after** `</ul>`, add:

```html
{% if has_todos %}
  <div class="list-footer">
    <p class="count">{{ remaining_count }} item{{ remaining_count|pluralize }} left</p>
  </div>
{% endif %}
```

- `{% if has_todos %}`: no footer when the whole list is empty (see Decisions).
- `item{{ remaining_count|pluralize }}`: `item` for 1, `items` for any other number.
- Keep the `<p>` on **one line**, exactly as above, so the tests can match the whole element.

In the `<style>` block, add one rule:

```css
.list-footer { color: #666; font-size: 0.9rem; }
```

### 4. `AGENTS.md` — the file table

- `todos/models.py` row: add "`Todo.objects.remaining()` gives the to-dos that are not done."
- `todos/views.py` row: add "`page_context` also gives the page `has_todos` and
  `remaining_count`."
- The template row: add "and a footer with how many to-dos are left".

The README does not describe the page in detail, so it does not change.

### Files that do not change

`forms.py`, `urls.py`, `admin.py`, and the migrations. No new package.

## Tests (`todos/tests/`)

We write all of these **first** and run them **before** changing the code. Each one fails on the
starting point (`main` with the due date merged) for the reason in the table.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

**No change.** The main journey (add, Done, Undo, Delete) is the same. The count is a small extra
on the page, and the tests below check it fully and fast. Adding it to the slow browser test would
make it longer, and more likely to clash with features 11 and 8.

### Bottom: unit tests (`todos/tests/unit/test_models.py`)

The counting rule is tested here, on the model alone, with no page. Add them to the existing
`TodoModelTests` class:

| Test | What it sets up | What it checks | How it fails today |
|---|---|---|---|
| `test_remaining_leaves_out_done_todos` | 3 to-dos, 1 of them done | `Todo.objects.remaining().count()` is `2`, and the done one is not in it | `AttributeError`: the manager has no `remaining` |
| `test_remaining_is_zero_when_all_are_done` | 2 to-dos, both done | `Todo.objects.remaining().count()` is `0` | `AttributeError`: the manager has no `remaining` |

### Middle: integration tests (`todos/tests/integration/test_views.py`)

These only check the **wiring**: that the number reaches the page, in the right words, in the right
places. Put them in a new class `CountTests` in the same file. Features 11 and 8 add tests to this
file at the same time, and separate classes clash less.

Every check on the count matches the **whole footer**, wrapper and all, for example:

```python
self.assertContains(
    response,
    '<div class="list-footer"><p class="count">2 items left</p></div>',
    html=True,
)
```

With `html=True`, Django compares whole HTML elements, not pieces of text. So a check for
`1 item left` can never match `11 items left` by mistake, and a change to the wrapper fails the
test.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it sets up | What it checks | How it fails today |
|---|---|---|---|
| `test_count_is_shown_under_the_list` | 3 to-dos, 1 of them done | the page has `<p class="count">2 items left</p>` | `AssertionError`: the page has no count yet |
| `test_count_says_item_for_one` | 1 to-do, not done | the page has `<p class="count">1 item left</p>` | `AssertionError`: the page has no count yet |
| `test_count_says_items_for_zero` | 1 to-do, done | the page has `<p class="count">0 items left</p>` | `AssertionError`: the page has no count yet |
| `test_count_is_on_the_error_page` | 1 to-do; post title `Buy milk` with date `not-a-date` | status 200, and the page has `<p class="count">1 item left</p>` | `AssertionError`: the error page has no count yet |
| `test_count_comes_after_the_list` (added after review) | 1 to-do | `class="count"` is on the page, and comes after `</ul>` | `AssertionError`: the page has no count yet |
| `test_count_follows_done_and_undo` (added after review) | 2 to-dos | `POST` toggle on one, follow the redirect: `1 item left`; toggle again: `2 items left` | `AssertionError`: the page has no count yet |
| `test_the_database_does_the_counting` (added after review) | 1 to-do | while the list page loads (`CaptureQueriesContext`), one SQL question is a `COUNT` on `todos_todo`. Not `assertNumQueries`: later features add questions. | `AssertionError`: no `COUNT` is asked yet |

(In the table above, every `<p class="count">…</p>` is checked inside its whole
`<div class="list-footer">…</div>`, as shown before the table.)

**Tests that protect what already works.** These **pass** before the change, and must still pass
after:

| Test | What it checks |
|---|---|
| `test_no_count_when_the_list_is_empty` (new) | with no to-dos: the page says `Nothing to do yet`, and does **not** contain the text `item left`, the text `items left`, `class="count"` or `class="list-footer"`. It checks both the words a person would see and the elements. |
| `test_list_page_loads` (already there) | the page still loads with status 200 and says `Nothing to do yet`. |

Every test that exists before this change must also still pass.

### A note for feature 8 (filter)

Feature 8 merges **after** this one. Its builder should add one more test, because only then can it
be tested: `test_count_ignores_the_filter`. With 2 to-dos (1 done), open the list with a filter
that shows no to-dos (for example "Active", after marking both done, or "Done" with none done), and
the page still has the footer and the right count. `has_todos` and `remaining_count` already use
the whole list, so this should pass with no change to the count code. The orchestrator should pass
this note to feature 8's builder.

## Steps, in order

1. Make the branch in its own worktree, from an **up-to-date** `main` on GitHub, so it includes the
   due-date feature:

   ```bash
   git fetch origin
   git worktree add -b count .claude/worktrees/count origin/main
   ```

   (`make worktree` starts from the local `main`, which may be old. That is why we use `git`
   directly here.) Check that `todos/forms.py` and `page_context` are there.
2. Write the two unit tests and the integration tests. Run `make test`: the two unit tests
   fail with `AttributeError`, the four new-behaviour integration tests fail with `AssertionError`,
   and the two protecting tests pass. Show this to the person.
3. Add `TodoQuerySet` and `objects = TodoQuerySet.as_manager()` to `models.py`. Run `make test`:
   the unit tests pass now; the integration tests still fail.
4. Add the two keys to `page_context` in `views.py`.
5. Change the template: the footer after `</ul>`, and the CSS rule.
6. Run `make test`: every test passes. Run `make test-cuj`: it still passes, with no change.
7. Run `make run` and open the page. Add three to-dos, press Done on one, and check that it says
   `2 items left`. Press Done on the other two: `0 items left`. Delete them all: no footer.
8. Update `AGENTS.md`.
9. Run `make check` (it also checks that no migration is missing). Commit.

## Risks

- **Merge conflicts with 11 and 8.** All three add lines to `page_context` and something near
  `</ul>` in the template. Each one adds its own lines, and 11 puts its button inside our footer,
  so a clash is small and easy to fix by hand. This feature merges first of the three, so it has no
  clash itself.
- **Two more small database questions per page** (`exists()` and `count()`). Each one is very fast.
  This is fine for a small app; we do not try to merge them into one question.

## What happened

Built as planned. The tests were written first. Before the code: the 2 unit tests failed with
`AttributeError: 'Manager' object has no attribute 'remaining'`, the 4 new integration tests failed
with `AssertionError` (no count on the page), and `test_no_count_when_the_list_is_empty` and
`test_list_page_loads` passed. After the code: Unit 6 passed, Integration 23 passed, CUJ 1 passed,
and `make check` passed (no migration needed: `makemigrations --check` said "No changes detected").

Small differences from the plan, and why:

- **`page_context` takes `request` too.** The approved plan showed `page_context(form)`. On the
  branch we started from, it is already `page_context(request, form)` (added for the filter
  feature). The two new keys went inside it, exactly as planned. The plan text above now shows
  `page_context(request, form)`.
- **The branch.** The plan says to start from `origin/main` with the due date merged. The due date
  was not merged yet, so this branch (`feature/count`) starts from `origin/feature/due-date`, and
  will be moved onto `main` after the due date merges.
- **Step 7 (check by hand in the browser) was not done** by the builder. It is still to do, by a
  person, before the merge.

### After the review

An adversarial code review found gaps in the tests. These were fixed as new commits on the same
branch:

1. **`<footer>` became `<div class="list-footer">`.** A `<footer>` directly in `<body>` is the
   page's "contentinfo" landmark for a screen reader, which is wrong here (orchestrator's decision).
   The CSS selector `.list-footer` did not need to change.
2. **The wrapper and the position are now tested.** Every count check matches the whole
   `<div class="list-footer"><p class="count">…</p></div>`, and `test_count_comes_after_the_list`
   checks the count comes after `</ul>`.
3. **"The database counts" is now tested** with `test_the_database_does_the_counting`.
4. **Done and Undo are tested through `todo_toggle`** with `test_count_follows_done_and_undo`.
5. **The empty-list test** now checks that `class="count"` and `class="list-footer"` are absent,
   not `<footer`.

Each new or changed test was first shown to fail: the wrapper tests failed against the old
`<footer>`, and then each test was run against a deliberate bug, put in and taken out again:
the count moved above the list (fails `test_count_comes_after_the_list`); the wrapper changed to
`<section>` (fails the 5 whole-footer tests); a Python loop instead of `.count()` (fails
`test_the_database_does_the_counting`); counting done to-dos too (fails
`test_count_follows_done_and_undo` and two others); a footer with no words on an empty list
(fails `test_no_count_when_the_list_is_empty`). After the fix: Unit 6 passed, Integration 26
passed, CUJ 1 passed, and `make check` passed.
