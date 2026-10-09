# Plan: delete the completed to-dos (feature 11, "clear completed")

Status: **done.** See "What happened" at the end. This is the second version. The first version was checked by an
adversarial review (a reviewer whose job is to find what is wrong). Every finding is fixed below.
The owner answered the open questions (see the end).

This is feature 11, in wave 1 of [the rollout plan](feature-rollout.md).

**Starting point.** The builder starts from `main` **after** [the due-date plan](due-date.md) is
merged. On that `main`:

- `todos/forms.py` has `TodoForm`.
- `todos/views.py` has a shared helper, used by `todo_list` and by the error path of `todo_add`:

  ```python
  def page_context(request, form):
      return {
          "todos": Todo.objects.all(),
          "form": form,
      }
  ```

- Features 12 (count) and 8 (filter) are **not** merged yet. They are built at the same time as this
  one. The wave 1 merge order is: 5 due date → 12 count → **11 (this one)** → 8 filter.

Every "How it fails today" in this plan is true on that starting point.

## What we want

One button that **deletes every completed to-do the person can see**, all at once. A person who has
finished many things can clean up the list with one click, instead of one Delete click for each.

## Decisions

- **One name for everything: "delete completed".** In this app, "Done" and "Undo" are the
  **actions** (the buttons on each row); "completed" is the **state** of a to-do after Done. The button says `Delete 3 completed to-dos` (or
  `Delete 1 completed to-do`). The address is `/delete-completed/`, the view is `todo_delete_completed`, and the
  form has `class="delete-completed"`. We say "Delete", not "Clear", because the to-dos are gone for
  ever; "Clear" can sound like they are only hidden. The number tells the person exactly how many
  will go.
- **The button shows only when at least one to-do is completed.**
- **The button sits in the footer under the list** (`<div class="list-footer">`, made by feature
  12), far from the Done / Undo / Delete buttons of each to-do. It is a `<div>`, not a `<footer>`
  element: a `<footer>` in `<body>` is announced to screen readers as the footer of the whole page.
- **Only the completed to-dos the person saw are deleted.** The form sends the **id** of each completed to-do
  on the page (an id, or `pk`, is the number that names one row in the table). The view deletes only
  to-dos that are in that list **and** are still completed. This stops a **race** (two things happening
  at the same time, in the wrong order):
  - The list is shared. Ana opens the page: 2 to-dos are completed, so the button says `Delete 2`.
  - Ben, in another browser, presses Done on a third to-do.
  - Ana presses the button. Without ids, 3 to-dos would go, but she was told 2. With ids, only her
    2 go. Ben's to-do stays.
  - Also: if someone presses **Undo** on one of Ana's 2 before she clicks, it is not completed any more,
    so it stays too.
- **Bad ids are ignored, never an error page.** An id that is not a plain number (`abc`, empty,
  `²`), or is too long to be a real id, is skipped. The rest still works. A request with no good id
  deletes nothing and goes back to the list.
- **No "Are you sure?" page.** The reasons, honestly:
  - Only **completed** to-dos are deleted, and only the ones the person saw and counted. Finished work is the
    least costly thing to lose.
  - The one-to-do Delete button has no "Are you sure?" either. The app behaves the same everywhere.
  - The button names the number. A person who misreads it loses only finished work.
  - The cost of a confirm page without JavaScript is real: one more view, one more template, one
    more address, and about three more tests. It also adds a click every time.

  But the list is **shared**: one click deletes the completed to-dos of everyone. The owner knew
  this and still said no confirm page (Open question 1, decided).
- **After the delete, the browser goes back to the list** (`redirect("todo_list")`), like add,
  toggle and delete. Keep it exactly this one line: feature 8 (filter) will swap it for its
  `back_to_list(request)` helper, and will add `{{ list_query }}` to every `POST` form's `action`,
  this one included. We do nothing for that now. No message is shown ("flashed") after it.
- **`POST` only, with the CSRF token.** A `GET` to `/delete-completed/` is refused with status **405**
  ("method not allowed"). (CSRF is a trick where another website makes your browser send a form to
  our site. Django's `{% csrf_token %}` stops it; without the token, Django answers **403**.)
- **The query lives on the model's manager.** A **manager** is the `Todo.objects` part; it is where
  Django puts the questions you can ask about the table. Feature 12 adds counting there
  (`Todo.objects.remaining()`). We add `Todo.objects.completed()` next to it. Views do not build their
  own `filter(done=True)`. (The database field is still called `done`; only the words people
  read and the names in the code say "completed".)
- **The delete is one `DELETE` query.** It never loads each to-do first (see the test
  `test_delete_completed_does_not_load_each_todo`).
- **The button counts the whole list**, not only the to-dos on the page. Note for feature 8
  (filter): on the "Active" view no completed to-do is on screen, but the button still says
  `Delete 2 completed to-dos`. **This is on purpose**: the button always says what it will really
  delete. Feature 8 must not change the button's count to follow the filter.

## What we will not do (yet)

- No "Are you sure?" page (see Decisions and Open question 1).
- No undo, and no "recycle bin".
- No "delete everything" button. Only completed to-dos.
- No JavaScript. No message after the delete.
- Nothing in the admin. The admin can already delete many to-dos, with its own confirm page.

## Changes in behaviour

1. A new address, `/delete-completed/`. A `POST` with ids deletes those to-dos that are still completed, and
   sends the browser back to the list. A `GET` gets 405. A `POST` without the CSRF token gets 403.
   Nothing changes in either case.
2. When at least one to-do is completed, the list page shows a `Delete N completed to-dos` button in the
   footer. When none is completed, there is no button.

What stays the same: add, toggle and delete; the CUJ journey; the add form and its errors.

## The changes, one file at a time

No migration. A manager change does not need one. `forms.py` does not change.

### 1. `todos/models.py` — `Todo.objects.completed()`

A **QuerySet** is a question to the database that is not sent yet, like "all completed to-dos". We give
`Todo` a QuerySet class with a `completed()` method, and use it as the manager.

- **If feature 12 has already merged when you start**, a `TodoQuerySet` exists. Add only the method:

  ```python
      def completed(self):
          return self.filter(done=True)
  ```

- **If not** (the normal case in wave 1), make the same shape feature 12 uses:

  ```python
  class TodoQuerySet(models.QuerySet):
      def completed(self):
          return self.filter(done=True)


  class Todo(models.Model):
      ...
      objects = TodoQuerySet.as_manager()
  ```

  Feature 12 makes the same class with `remaining()`. At merge time this **will clash** (see "Merge
  conflicts" below). The fix is to keep one class with both methods.

### 2. `todos/urls.py` — one new address

Add one line at the **end** of `urlpatterns`:

```python
    path("delete-completed/", views.todo_delete_completed, name="todo_delete_completed"),
```

### 3. `todos/views.py` — the ids for the page, and the new view

**In `page_context` only**, add one key. Both `todo_list` and the error path of `todo_add` use
`page_context`, so the button is on both pages with no other change:

```python
def page_context(request, form):
    return {
        "todos": Todo.objects.all(),
        "form": form,
        "completed_ids": list(
            Todo.objects.completed()
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)[:MAX_DELETE_AT_ONCE]
        ),
    }
```

`values_list("pk", flat=True)` asks only for the ids, as a list of numbers: `[3, 7]`. `list(...)`
runs the query once, so the template can count it and loop over it with no second query.
`[:MAX_DELETE_AT_ONCE]` keeps the oldest 500 (added after code review; see Open question 2).

**A new view, at the end of the file:**

```python
# A real id is a plain number. 18 digits always fit in SQLite's 64-bit integer;
# longer values may overflow.
MAX_ID_DIGITS = 18


@require_POST
def todo_delete_completed(request):
    ids = [
        value
        for value in request.POST.getlist("ids")
        if value.isascii() and value.isdigit() and len(value) <= MAX_ID_DIGITS
    ]
    Todo.objects.completed().filter(pk__in=ids).delete()
    return redirect("todo_list")
```

- `@require_POST`: a **decorator** (a line with `@` that wraps a function). It answers 405 to
  anything that is not `POST`.
- `getlist("ids")`: every value sent under the name `ids`.
- `isascii() and isdigit()`: only `0`–`9`. (`isdigit()` alone also accepts `²`, and then the
  database would raise an error.) `len(...) <= 18`: a number with more digits would overflow
  SQLite and give a 500 error page.
- `completed().filter(pk__in=ids)`: still completed **and** seen by the person. If `ids` is empty, Django
  sends no query at all, and nothing is deleted.

### 4. `todos/templates/todos/todo_list.html` — the button

The button goes **inside** `<div class="list-footer">`, after `</ul>`, below the count of feature
12:

```html
{% if completed_ids %}
  <form class="delete-completed" method="post" action="{% url 'todo_delete_completed' %}">
    {% csrf_token %}
    {% for pk in completed_ids %}<input type="hidden" name="ids" value="{{ pk }}">{% endfor %}
    <button type="submit">Delete {{ completed_ids|length }} completed to-do{{ completed_ids|length|pluralize }}</button>
  </form>
{% endif %}
```

- `<input type="hidden">`: a box the person cannot see. It carries one id to the server.
- `pluralize`: a Django **filter** (a helper after `|`) that adds `s` when the number is not 1.

If feature 12 has not merged when you start, make the footer yourself, with the same class:

```html
<div class="list-footer">
  ...the form above...
</div>
```

and one CSS line: `.list-footer { margin-top: 1rem; }` (feature 12 may already have it).

### 5. `AGENTS.md` — the file table

- `todos/urls.py` row: "The four addresses: the list, add, toggle, delete" becomes "The addresses:
  the list, add, toggle, delete, delete completed."
- `todos/views.py` row: "Add, toggle and delete accept `POST` only" becomes "Add, toggle, delete
  and delete completed accept `POST` only". Add: "Delete completed deletes only the completed to-dos whose ids the
  page sent."
- `todos/models.py` row: add "`Todo.objects.completed()` gives the completed to-dos."

## Merge conflicts, honestly

Git cannot "keep both" when two branches add different lines **at the same place**. It stops, and
a person (here, the merge queue) must write the combined version by hand. Feature 12 merges first,
so this branch is the one that is rebased and fixed. Expect these clashes:

| Place | What 12 adds | What 11 adds | The combined version |
|---|---|---|---|
| `models.py` | `TodoQuerySet` with `remaining()`, and `objects = ...` | the same class with `completed()` | one class with both methods, one `objects` line |
| `page_context` in `views.py` | its count key, after `"form"` | `"completed_ids"`, after `"form"` | both keys, one per line, 12's first |
| template, after `</ul>` | `<div class="list-footer">` with the count | the same footer with the button | one footer: the count, then the button |
| `AGENTS.md` rows | its text | this text | both sentences |

Each fix is small, but each one is a real clash, not a free merge. After the fix, run every test
of **both** features. Feature 8 then rebases on top of both.

## Tests (`todos/tests/`)

We write all of these **first** and run them **before** changing the code.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

**No change.** The journey (add, Done, Undo, Delete) is still the most important thing a person
does. The integration tests below check the whole path of this feature. After the change, check the
CUJ test still passes: the new button is **outside** the `<li>`, and the test looks for the
`Delete` button **inside** the item, so it still finds the right one.

### Bottom: a unit test (`todos/tests/unit/test_models.py`)

| Test | What it checks | How it fails today |
|---|---|---|
| `test_completed_gives_only_completed_todos` | with one completed and one open to-do, `Todo.objects.completed()` gives only the completed one | `AttributeError`: the manager has no `completed()` |

### Middle: integration tests (`todos/tests/integration/test_views.py`)

Most tests start with `Buy milk` (completed), `Call home` (completed) and `Read chapter 3` (open).
"Post the ids" means `POST` to `reverse("todo_delete_completed")` with `{"ids": [..]}`.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_delete_completed_removes_the_completed_ones_seen` | post the ids of the two completed to-dos | only `Read chapter 3` is left, and the answer redirects to `todo_list` (`assertRedirects`) | `NoReverseMatch`: no address named `todo_delete_completed` |
| `test_completed_after_the_page_loaded_survives` | post only `Buy milk`'s id (as if `Call home` became completed later) | `Call home` is still there | `NoReverseMatch` |
| `test_open_todo_is_never_deleted` | post the id of `Read chapter 3` (open) | nothing is deleted | `NoReverseMatch` |
| `test_bad_ids_are_ignored` | post `abc`, an empty value, `²`, `"9" * 19`, `"9" * 30`, and `Buy milk`'s id (19 digits pins the 18-digit cap) | status 302 (not 500), and only `Buy milk` is gone | `NoReverseMatch` |
| `test_delete_completed_does_not_load_each_todo` | post both completed ids inside `CaptureQueriesContext(connection)` | at least one captured query starts with `DELETE`, and **no** query starts with `SELECT` and reads the `todos_todo` table | `NoReverseMatch` |
| `test_get_cannot_delete_completed` | `GET` to `todo_delete_completed` | status 405, and all three to-dos are still there | `NoReverseMatch` |
| `test_delete_completed_needs_the_csrf_token` | `Client(enforce_csrf_checks=True)` posts the ids with no token | status 403, and all three are still there | `NoReverseMatch` |
| `test_delete_completed_form_on_the_list` | open the list | the whole form, exactly, once (`assertInHTML`, with the CSRF input taken out): `action="/delete-completed/"`, one hidden `ids` input for each completed id and none other, and `<button type="submit">Delete 2 completed to-dos</button>` | the page has no such form |
| `test_delete_completed_button_says_one_to_do` | only one completed to-do, open the list | the whole form, exactly, with `Delete 1 completed to-do` | the page has no such form |
| `test_delete_completed_form_is_in_the_list_footer` | open the list | the whole `<div class="list-footer">`, exactly: the count, then the form | no such footer (added after the first build; see "What happened") |
| `test_the_form_on_the_page_works_with_csrf_checks_on` | `Client(enforce_csrf_checks=True)` gets the page, reads the CSRF token and the ids from the form, and posts them | status 302, and only `Read chapter 3` is left | fails if the form has no `{% csrf_token %}` (added after code review) |
| `test_at_most_500_are_offered_at_once` | 501 completed to-dos | the form has the oldest 500; posting them leaves 1, and the page then offers that 1 | the page offers 501 (added after code review) |

Why `CaptureQueriesContext` and not `assertNumQueries(1)`: a later feature (accounts, 17) will add
its own queries to every request. This test only says what matters: the view never reads each
to-do before deleting it. **Note for later:** when a table points to `Todo` (subtasks, feature 15),
Django will `SELECT` the to-dos to delete their subtasks. That feature must change this test on
purpose, and say why.

`test_get_cannot_change_data` is **not** changed. The new GET rule has its own test above.

**A test that protects what already works.** It **passes** before the change, and must still pass:

| Test | What it checks |
|---|---|
| `test_no_delete_completed_form_when_nothing_is_completed` | only `Read chapter 3` (open): the whole footer, exactly, is the count and no form |

Every test that exists before this change must also still pass.

## Steps, in order

1. Start a worktree from the newest `main` (due date merged).
2. Write the new tests. Run `make test`: the unit test and the nine new integration tests fail with
   the errors listed, and the protecting test passes. Show this to the person.
3. Change `models.py`, then `urls.py`, then `views.py`, then the template.
4. Run `make test`: every test passes. Run `make test-cuj`: the journey still passes, unchanged.
5. Run `make run`. Add three to-dos, press Done on two; the button says `Delete 2 completed to-dos`. Open a
   second tab, press Done on the third there, then press the button in the first tab: the third stays.
   Make the window narrow, like a phone, and check the footer still fits.
6. Update `AGENTS.md`.
7. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected".
8. Run `make check`. Commit.

## Open questions (decided)

1. **Do you want an "Are you sure?" page?** **Decided: no.** The owner said to delete directly,
   with no confirm page. (If this changes later: the button becomes a link to
   `/delete-completed/confirm/`, a `GET` page that lists the completed to-dos, says "This cannot be
   undone", and has the same `POST` form and a Cancel link. The `/delete-completed/` address and its
   tests stay as they are.)
2. **Very long lists.** Django refuses a form with more than 1,000 fields (status 400), and then
   **nothing** is deleted. The owner first accepted this. Code review showed that with 1,000 or
   more completed to-dos the button would then never work. **Decided (orchestrator): the page
   offers at most the oldest 500** (`MAX_DELETE_AT_ONCE` in `views.py`). The button says
   `Delete 500 completed to-dos`, and the next click deletes the rest.
3. **Feature 8 (filter).** After the delete, the browser goes to the plain list, so a chosen filter
   is lost. Feature 8 should decide this once for add, toggle, delete and delete completed together.

## What happened

The tests were written first and committed alone, with this plan. Before the code changed,
`make test` showed `Integration: 19 passed, 2 failed, 7 errors` and `Unit: 4 passed, 1 error`.
Every new test failed for the reason in the tables above: the unit test with `AttributeError`
(no `completed()`), seven integration tests with `NoReverseMatch` (no `todo_delete_completed`),
and the two page tests because the form and button were not on the page. The protecting test
passed. After the code: `Unit: 5 passed`, `Integration: 28 passed`, `CUJ: 1 passed` (the journey
test did not change), and `makemigrations --check --dry-run` said "No changes detected".

Feature 12 (count) was not on this branch's base (`feature/due-date`), so this branch made
`TodoQuerySet` and `<div class="list-footer">` (with its CSS line) itself, as the plan says. Expect
the merge clashes listed in "Merge conflicts, honestly".

Small differences from the plan, with reasons:

- **The footer is a `<div class="list-footer">`, not a `<footer>`.** After the first build, the
  orchestrator said the shared footer (used by feature 12 too) is a `<div>`: a `<footer>` in
  `<body>` is announced to screen readers as the footer of the whole page. The template, its CSS
  line (now `.list-footer`) and this plan were changed. A new test,
  `test_delete_completed_form_is_in_the_list_footer`, was written first; it failed with
  `ValueError` (no `<div class="list-footer">`) on the `<footer>` version, and passes now. After
  this change: `Unit: 5 passed`, `Integration: 29 passed`, `CUJ: 1 passed`.

- **`urls.py`:** the new `path(...)` is split over three lines. The one-line version is longer than
  Ruff's line limit, and `ruff format` splits it.
- **`views.py`:** the new view has a one-line docstring (a short note under `def` that says what
  the function does). Nothing else changed.
- **Tests:** the new integration tests are in their own class, `DeleteCompletedTests`, so they can
  share the three starting to-dos in `setUp`. The one-to-do and nothing-completed tests delete
  from those three, instead of starting with a different set.
- **Step 5 (try it by hand with `make run` in two tabs) was not done.** The race it checks is
  covered by `test_completed_after_the_page_loaded_survives` and `test_open_todo_is_never_deleted`.
- **A warning for later:** `uv run ruff format` with no file names (that is `make format`) also
  rewrites Python code blocks inside Markdown files. It changed the `urls.py` example in this plan
  into wrong code, so that change was undone. The commit checks only format `.py` files, so they
  are safe.

### The rebase onto `main`

Due date and count were merged into `main`, and this branch was rebased onto it. The clashes were
the ones listed in "Merge conflicts, honestly", and each was fixed by keeping both:

- `models.py`: one `TodoQuerySet` with `remaining()` and then `completed()`.
- `page_context`: count's `has_todos` and `remaining_count`, then `completed_ids`.
- The template: count's footer, shown only when `has_todos`, holds the count `<p>` and then the
  form. Count's CSS line for `.list-footer` was kept; this branch's `margin-top` line was dropped.
  The button only shows when a to-do is completed, so there is always a to-do, and the footer is
  always there when the button is.
- `AGENTS.md`: the rows say both.

**Count's tests were changed on purpose.** Three of them compared the whole footer, exactly. With
a completed to-do, the footer now also holds the delete button, so they failed. They now name the
completed to-dos, and the expected footer has the form too. The CSRF token is different every time
the page is drawn, so the tests take the token input out before they compare (`page_without_csrf`).

### Code review

Four findings, fixed as new commits. The tests came first:

1. **A missing `{% csrf_token %}` passed every test.** New test
   `test_the_form_on_the_page_works_with_csrf_checks_on` reads the token and ids from the page and
   posts them with CSRF checks on. With the token line taken out of the template, it failed:
   `the delete-completed form has no CSRF token`.
2. **The 18-digit cap was not pinned.** `test_bad_ids_are_ignored` also posts 19 digits now. With
   `MAX_ID_DIGITS = 19`, it failed with `OverflowError: Python int too large to convert to SQLite
   INTEGER`. The comment above the cap was made exact.
3. **1,000 or more completed to-dos made the button useless** (see Open question 2). New test
   `test_at_most_500_are_offered_at_once`. Before the fix, it failed: the page offered
   `Delete 501 completed to-dos`. The fix: `page_context` keeps the oldest 500
   (`order_by("created_at", "pk")`, `pk` to break a tie).
4. **Loose checks.** The form, footer and no-form tests now compare the whole element, exactly
   (`assertInHTML`, `count=1`), instead of pieces of text and page-wide "not on the page" checks.

After the review fixes: `Unit: 7 passed`, `Integration: 42 passed`, `CUJ: 1 passed`, and
`make check` passed.
