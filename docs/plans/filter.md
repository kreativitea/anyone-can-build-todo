# Plan: filter the list (All, Active, Completed)

Status: **done.** Built, reviewed, and rebased on `main` with 12 (count) and 11 (delete completed).

This is feature 8, the last one in wave 1 of [the rollout plan](feature-rollout.md). An adversarial
review (a reviewer whose job is to find what is wrong) checked the first version. Every finding is
fixed below.

**Where this starts.** The work starts on `main` **after feature 5 (due date) is merged**. So
"how it fails today" in the tests means: `main` with feature 5 in it. On that `main`:

- `todos/forms.py` has `TodoForm`.
- `todos/views.py` has a helper, `page_context(request, form)`. It returns the dictionary for the
  page, with the keys `"todos"` and `"form"`. Both `todo_list` and the error path of `todo_add` use
  it.
- The template draws the add form with `{{ form... }}`.

Features 12 (the count) and 11 (delete completed) are built at the same time as this one. They merge
**before** it. The section "After 12 and 11 are on `main`" says what this feature must then do.

## What we want

Above the list, three links: **All**, **Active** and **Completed**.

- **All** shows every to-do, like today.
- **Active** shows only the to-dos that are not finished.
- **Completed** shows only the to-dos that are finished.

The person can see which link is chosen. When they press Add, Done, Undo or Delete, they **stay on
the same filter**. The page needs no JavaScript.

## Words

These names are decided for the whole app:

- The button on each to-do stays **Done** / **Undo**. It is an **action**: something you do.
- The **state** of a finished to-do is **completed**. So the link is "Completed", the address is
  `?show=completed`, and the empty message is "Nothing completed yet."

## Decisions

### The filter is in the address

- A **query parameter** is the part of an address after `?`, for example `/?show=active`.
- Choosing a filter only reads. So it is a normal link: a `GET` request.
- The values are `show=active` and `show=completed`.
- **All** is the plain address `/`, with no `?`. `/?show=all` also means All.

### An unknown value means All

- `/?show=banana`, `/?show=COMPLETED`, `/?show=done` and `/?show=` all show every to-do.
- The All link is then marked as chosen.
- There is no error page. A wrong link should still show the list.

### Three small helpers hold the "list parameters"

The **list parameters** are the parts of the address that change how the list looks. Today there is
one: `show`. Later, search (10) adds `q` and sort (9) adds `sort`.

- `list_params(data)` reads the address and returns a dictionary with **only the checked values that
  are not the default**. Today that is `{}` or `{"show": "active"}` or `{"show": "completed"}`.
  Anything it does not know is dropped.
- `list_query(params)` turns that dictionary back into text for an address: `"?show=active"`, or
  `""` when there is nothing.
- `filter_todos(todos, params)` makes the list smaller. It is the one line the filter adds to the
  list query (the list-query rule in the rollout plan).

Search and sort will each add one check inside `list_params` and one line for the query. Then the
filter links, the forms and the redirects keep their parameters too, **with no other change**.

### Staying on the filter after a `POST`

- Add, toggle and delete end with a **redirect**: an answer that tells the browser "now go to this
  address".
- Every `POST` form's address (its `action`) gets the list query at the end. For example, the
  toggle form on the Active view posts to `/5/toggle/?show=active`.
- The view reads the query from its own address (`request.GET`). It works even in a `POST`
  request.
- One helper, `back_to_list(request)`, builds the address to go back to. It starts from
  `reverse("todo_list")`, which is `/`, and adds `list_query(list_params(request.GET))`.

### Never an open redirect

- An **open redirect** is a bug where a site sends the browser to any address someone put in a link
  or a form, for example a fake login page.
- We never redirect to an address taken from the request.
- `back_to_list` always starts from our own address, `/`. It adds only values that `list_params`
  has checked against a fixed list. A `next=` value, a full address, or a line break (`\r\n`) is
  dropped.

### The page shows which filter is chosen

- The chosen link has `aria-current="page"`. `aria-current` is an attribute that tells a screen
  reader (a program that reads the page aloud) "this is the one you are on".
- The CSS makes that same link **bold**. The look and the meaning come from one place.
- The view builds the three links (their words, addresses and which one is chosen). The template
  only draws them.

### The message for an empty list depends on the filter

| Filter | Message |
|---|---|
| All | `Nothing to do yet. Add something above.` (the same as today) |
| Active | `Nothing left to do.` |
| Completed | `Nothing completed yet.` |

### Other decisions

- **A to-do moves when it changes.** On Active, pressing Done makes the to-do leave the list. The
  person stays on Active.
- **If adding fails** (for example a bad date), the page is shown again with the error. It is
  filtered in the same way, and its forms keep the query.
- **The count (12) and "Delete completed" (11) are about the whole table,** not only what is shown.
  The footer is shown when the table has any to-do at all. So the filter cannot hide it.

## What we will not do (yet)

- **No JavaScript.** Each filter link loads the page again. That is fast enough for a short list.
- **No counts on the links**, like "Active (3)". Feature 12 shows one count; that is enough.
- **No remembering the filter** for the next visit. Only the address remembers it.
- **No search and no sort.** Those features extend `list_params` later.

## Changes in behaviour

1. `/?show=active` and `/?show=completed` show only part of the list. Before, the `?show=...` part
   was ignored, and every to-do was shown.
2. The page has three filter links, and one of them is marked as chosen.
3. The `POST` forms post to an address with the list query. Add, toggle and delete send the browser
   back to the same filter. Before, they always went to `/`.
4. The empty message is different on Active and on Completed.
5. After a failed add, the page is still filtered.

What stays the same:

- The plain address `/` shows every to-do, with the same empty message as today.
- Add, toggle and delete still accept `POST` only.
- A form posted with no query (an old page, or a test) still goes back to `/`.

## The changes, one file at a time

No model change, so **no migration**.

### 1. `todos/views.py` — the views

New helpers, at the top of the file:

```python
from urllib.parse import urlencode

from django.urls import reverse

# The filter links: (the value in the address, the word on the page).
FILTERS = [("all", "All"), ("active", "Active"), ("completed", "Completed")]


def list_params(data):
    """The list parameters in the address that we know, without the defaults.

    Anything we do not know is dropped, so it can never reach a redirect.
    """
    params = {}
    if data.get("show") in ("active", "completed"):
        params["show"] = data["show"]
    return params


def list_query(params):
    """The text to put after an address: "?show=active", or "" for none."""
    return "?" + urlencode(params) if params else ""


def filter_todos(todos, params):
    """Only the to-dos the filter asks for."""
    show = params.get("show")
    if show == "active":
        return todos.filter(done=False)
    if show == "completed":
        return todos.filter(done=True)
    return todos


def filter_links(params):
    """The All, Active and Completed links, each one keeping the other parameters."""
    chosen = params.get("show", "all")
    return [
        {
            "label": label,
            "url": reverse("todo_list")
            + list_query(list_params({**params, "show": value})),
            "current": value == chosen,
        }
        for value, label in FILTERS
    ]


def back_to_list(request):
    """Send the browser back to the list, with the same list parameters.

    The address always starts from our own list page.
    """
    return redirect(reverse("todo_list") + list_query(list_params(request.GET)))
```

- `data` is `request.GET`: what is in the address. It is a Django **QueryDict**, a dictionary of
  what the browser sent. A plain dictionary works too, which keeps the unit tests simple.
- `list_params({**params, "show": value})` makes the address for one link. For All, `list_params`
  drops `show` by itself, because "all" is the default. So the All link is `/`.
- `filter_todos` takes a **queryset** (Django's description of a database question, not run yet)
  and returns a smaller one. Search and sort can add their own step after it.

`page_context` (from feature 5) gets the filter. Each key is on its own line, so the parallel
branches add lines, not change them:

```python
def page_context(request, form):
    params = list_params(request.GET)
    todos = Todo.objects.all()
    todos = filter_todos(todos, params)
    return {
        "todos": todos,
        "form": form,
        "show": params.get("show", "all"),
        "list_query": list_query(params),
        "filter_links": filter_links(params),
    }
```

- `todo_list` and the error path of `todo_add` do not change: they already call `page_context`.
  The error path is filtered because the add form posts to `/add/?show=...`, so `request.GET` has
  the query.
- In `todo_add` (the good path), `todo_toggle` and `todo_delete`, one line changes in each:
  `return redirect("todo_list")` becomes `return back_to_list(request)`.

### 2. `todos/templates/todos/todo_list.html` — the page

**The filter links**, between the add form and the list:

```html
<nav class="filters" aria-label="Show">
  {% for link in filter_links %}
    <a href="{{ link.url }}"{% if link.current %} aria-current="page"{% endif %}>{{ link.label }}</a>
  {% endfor %}
</nav>
```

- `<nav>` tells a screen reader "these are links to move around". `aria-label="Show"` gives it a
  name.

**Every `POST` form** gets the list query at the end of its address:

```html
<form class="add" method="post" action="{% url 'todo_add' %}{{ list_query }}">
<form method="post" action="{% url 'todo_toggle' todo.pk %}{{ list_query }}">
<form method="post" action="{% url 'todo_delete' todo.pk %}{{ list_query }}">
```

`{{ list_query }}` is always built by our own code from checked values. Django also escapes it
(makes it safe inside HTML) by itself. The `&` between parameters, when search adds one, becomes
`&amp;`, which is correct in HTML.

**The empty message:**

```html
{% empty %}
  <li>{% if show == "active" %}Nothing left to do.{% elif show == "completed" %}Nothing completed yet.{% else %}Nothing to do yet. Add something above.{% endif %}</li>
```

**The CSS:**

```css
nav.filters { display: flex; gap: 1rem; margin-bottom: 1rem; }
nav.filters a[aria-current="page"] { font-weight: bold; text-decoration: none; color: inherit; }
```

The bold style is chosen by `aria-current`. So the link that looks chosen is always the link a
screen reader says is chosen. Three short words fit on one row, even on a phone.

### 3. `todos/urls.py`, `todos/models.py`, `todos/forms.py` — no change

The filter uses the list address that already exists.

### 4. `AGENTS.md`

- `todos/views.py` row: add "The list can show All, Active or Completed (`?show=active`,
  `?show=completed`). `list_params` reads the list parameters and drops anything unknown. Every
  `POST` form posts to an address with the list query, and `back_to_list` sends the browser back to
  the same view."
- Template row: "The one page: the add form, the filter links and the list."
- Rules: "A new `POST` form on the list page ends its `action` with `{{ list_query }}`, and its view
  ends with `back_to_list(request)`."

## After 12 and 11 are on `main`

This feature merges last in wave 1. Before it joins the merge queue, the builder **rebases** on
`main` with 12 and 11 in it. A **rebase** moves this branch's commits so they start from the newest
`main`. Then the builder does this part:

1. **`page_context`.** Keep every key: 12's keys (`has_todos`, the count) and this feature's keys.
   Check that 12 counts from the whole table, with `Todo.objects.remaining().count()`, and that
   `has_todos` comes from `Todo.objects.exists()`. Neither may use the filtered `todos`.
2. **Delete completed (11).** Its form is in the footer, and sends the ids of the completed to-dos
   it showed. Its `action` becomes `{% url ... %}{{ list_query }}`. Its view ends with
   `back_to_list(request)` instead of `redirect("todo_list")`.
3. Write the three tests in "After the rebase" below. Run them, then fix what fails.

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

**No change.** A filter is a new way to look at the same list, not a new journey. The integration
tests below check every part of it.

The CUJ test still passes after the change:

- It opens `/`, which is All. The empty message for All is the same as today.
- It finds the Done button inside the to-do, by its role `button`. The new links are called All,
  Active and Completed, so nothing gets mixed up.

### Bottom: unit tests (`todos/tests/unit/test_list_params.py`, new file)

`list_params` and `list_query` need no database. They are tested with `SimpleTestCase`, Django's
test class for tests that do not use the database. Each row is one `subTest`.

| Test | What it checks | How it fails today |
|---|---|---|
| `test_list_params_keeps_known_values` | `QueryDict("show=active")` → `{"show": "active"}`; `show=completed` → `{"show": "completed"}`; `show=active&next=https://evil.example` → `{"show": "active"}` | `ImportError`: there is no `list_params` yet |
| `test_list_params_drops_the_rest` | `""`, `show=all`, `show=`, `show=COMPLETED`, `show=done`, `show=banana`, `show=https://evil.example`, `show=completed%0D%0A` (a line break), `show=completed%26next%3Dx` (a hidden `&next=`), `next=https://evil.example` → `{}` | `ImportError` |
| `test_list_query` | `{}` → `""`; `{"show": "active"}` → `"?show=active"` | `ImportError` |

The `ImportError` makes the whole file fail as one error. That is expected: the functions do not
exist yet.

### Middle: integration tests (`todos/tests/integration/test_filter.py`, new file)

A new file, so it does not clash with 12 and 11, which change `test_views.py`.

In these tests, "an active to-do" is `Buy milk` (not done). "A completed to-do" is `Call home`
(done). Redirects are checked with `response["Location"]`, exactly.

**A small helper in the test file** finds the forms on a page. It uses `html.parser.HTMLParser`,
which comes with Python. It returns the `action` of every form with `method="post"`.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_active_shows_only_active_todos` | one of each; open `/?show=active` | `Buy milk` is there, `Call home` is not | `Call home` is shown: `?show` is ignored |
| `test_completed_shows_only_completed_todos` | one of each; open `/?show=completed` | `Call home` is there, `Buy milk` is not | `Buy milk` is shown |
| `test_filter_links_are_on_the_page` | open `/` | `<a href="/" aria-current="page">All</a>`, `<a href="/?show=active">Active</a>`, `<a href="/?show=completed">Completed</a>` (`assertContains` with `html=True`) | there are no links |
| `test_chosen_filter_is_marked` | open `/?show=completed` | the Completed link has `aria-current="page"`, and `aria-current` is on the page once | there are no links |
| `test_unknown_filter_marks_all` | open `/?show=banana` | the All link has `aria-current="page"` | there are no links |
| `test_empty_message_for_each_filter` | one completed to-do, open `/?show=active`; one active to-do, open `/?show=completed` (a `subTest` each) | `Nothing left to do.`; `Nothing completed yet.` | the list is not filtered, so it is not empty: no message |
| `test_every_post_form_keeps_the_filter` | one of each; open `/?show=active` and `/?show=completed` (a `subTest` each) | the helper finds at least 3 `POST` forms (add, toggle, delete), and **every** action ends with the same `?show=...` | the actions have no query |
| `test_add_keeps_the_filter` | post title `Buy milk` to `/add/?show=active` | redirect to `/?show=active` | redirect to `/` |
| `test_toggle_keeps_the_filter` | post to toggle, with `?show=completed` | redirect to `/?show=completed` | redirect to `/` |
| `test_toggle_on_active_leaves_the_list` | one active to-do; post to toggle with `?show=active`, `follow=True` | the browser ends on `/?show=active`; `Buy milk` is not on the page; `Nothing left to do.` is | redirect to `/`, and `Buy milk` is still shown |
| `test_delete_keeps_the_filter` | post to delete, with `?show=completed` | redirect to `/?show=completed` | redirect to `/` |
| `test_add_error_keeps_the_filter` | one of each; post title `New`, `due_date=not-a-date` to `/add/?show=active` | status 200; `Enter a valid date.`; `Buy milk` is there and `Call home` is not; the Active link has `aria-current`; every `POST` form action ends with `?show=active` | `Call home` is shown: the page is not filtered |
| `test_redirect_drops_unknown_params` | post to toggle with `?show=active&next=https://evil.example` | redirect to `/?show=active` exactly | redirect to `/` |

**Tests that protect what already works.** These **pass** before the change, and must still pass
after:

| Test | What it checks |
|---|---|
| `test_all_shows_every_todo` | one of each; `/` and `/?show=all` both show both to-dos |
| `test_unknown_filter_shows_every_todo` | `/?show=banana` shows both to-dos, with status 200 |
| `test_post_without_query_goes_to_the_list` | toggle with no query, and with `?show=all`: redirect to `/` (a `subTest` each) |
| `test_redirect_only_goes_to_the_list_page` | toggle with each of these (a `subTest` each): `?next=https://evil.example` **and** `next=https://evil.example` in the posted data; `?show=https://evil.example`; `?show=//evil.example`; `?show=completed%0D%0ALocation:%20https://evil.example`; `?show=completed%26next%3Dhttps://evil.example`. Each one redirects to `/` exactly |

**Why the last test passes today, and how to see it fail.** It passes today only because today
the views ignore everything in the request. That is honest, but it does not prove the test can
catch the bug. So, after the code is written, **break it on purpose for a moment**, with the real
open-redirect bug: in `back_to_list`, write
`return redirect(request.POST.get("next") or reverse("todo_list"))`. The test fails. Put the code
back. `git diff` must not show the broken line.

Every test that exists before this change must also still pass. That includes
`test_list_page_loads`, which checks `Nothing to do yet` on `/`.

### After the rebase on 12 and 11

Added to `test_filter.py` after the rebase:

| Test | What it does | What it checks | How it fails then |
|---|---|---|---|
| `test_count_shows_on_completed_view_with_nothing_completed` | one active to-do; open `/?show=completed` | `Nothing completed yet.` **and** `1 item left` | fails if the footer uses the filtered list. If it passes at once, break it on purpose for a moment (`has_todos` from `todos.exists()`), see it fail, put it back |
| `test_count_on_active_view_with_everything_completed` | one completed to-do; open `/?show=active` | `Nothing left to do.` **and** `0 items left` | the same as above (break: count from the filtered `todos`) |
| `test_delete_completed_keeps_the_filter` | one completed to-do; post to `/delete-completed/?show=completed` with its id (in 11's field) | redirect to `/?show=completed`, and the to-do is gone | redirect to `/`: 11's view does not use `back_to_list` yet |

`test_every_post_form_keeps_the_filter` also covers 11's form after the rebase: the footer form must
end with the query too, or the test fails.

## Steps, in order

1. Write the unit tests and the integration tests. Run `make test`:
   - the unit file fails with `ImportError` (one error),
   - the 13 new-behaviour tests fail as listed,
   - the 4 protecting tests pass.
2. Change `views.py`: add the helpers, the filter in `page_context`, and `back_to_list` in add,
   toggle and delete.
3. Change the template: the links, `{{ list_query }}` in every `POST` form, the empty message, the
   CSS.
4. Run `make test`: every test passes. Run `make test-cuj`: the CUJ test passes, unchanged.
5. Break `back_to_list` on purpose (see above). `test_redirect_only_goes_to_the_list_page` fails.
   Put it back. Check `git diff`.
6. Run `make run` and open the page:
   - Add three to-dos, finish one. Click Active, Completed and All.
   - On Active, press Done: the to-do leaves the list, and the address is still `/?show=active`.
   - Try `/?show=banana`: every to-do, and All is bold.
   - Make the window narrow, like a phone: the links still fit.
7. Update `AGENTS.md`.
8. When 12 and 11 are on `main`: rebase, then do "After 12 and 11 are on `main`" with its three
   tests. Run `make test` and `make test-cuj` again.
9. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected". This
   feature has no migration.
10. Run `make check`. Commit.

## Risks

- **Clashes when rebasing on 12 and 11.** All three change `page_context` and the template. One key
  per line keeps the clash small, and this plan says what to keep.
- **A future `POST` form may forget `{{ list_query }}`.** Then that button sends the person back to
  All. Nothing breaks; it is only annoying. `test_every_post_form_keeps_the_filter` catches it.
- **Reloading after a failed add.** The error page is the answer to a `POST`, at `/add/?show=...`.
  If the person reloads it, the browser asks to send the form again — the same as after feature 5;
  this feature does not change it.

## What happened

The builder followed the plan. These are the places where it did something a little different, and
why.

1. **The starting point.** The branch starts from `feature/due-date` (feature 5, finished but not
   merged yet), not from `main` with feature 5 in it. The code there is the same as the plan
   expects: `forms.py`, and `page_context(request, form)`.
2. **The part for 12 and 11 is not done yet.** The three tests in "After the rebase on 12 and 11",
   and the changes in "After 12 and 11 are on `main`", wait until this branch is rebased on `main`
   with 12 and 11 in it.
3. **"`aria-current` is on the page once".** `assertContains(..., html=True)` finds the chosen
   link, but it cannot say that **no other** link is marked too. (Counting the text
   `aria-current="page"` would not work either: the CSS selector has the same words.) So the test
   helper (an `HTMLParser`) lists the text of every link that has `aria-current="page"`, and the
   test checks that this list is exactly `["Completed"]`. That proves no other link is marked. The
   same check is used in `test_unknown_filter_marks_all` and `test_add_error_keeps_the_filter`.
4. **`test_toggle_on_active_leaves_the_list`** checks the end address with the test client's
   `redirect_chain`: it must be `[("/?show=active", 302)]`.
5. **The open-redirect test was seen failing twice.** Before the code, the real bug
   (`redirect(request.POST.get("next") or "todo_list")`) was put in `todo_toggle` for a moment. After
   the code, the plan's version of the bug was put in `back_to_list`. Both times
   `test_redirect_only_goes_to_the_list_page` failed with `'https://evil.example' != '/'`. Both
   times the line was taken out again, and `git diff` was checked.
6. **`page_context`'s docstring** lost the line "`request` is not used yet", because now it is.
7. **Ruff format** wrapped a few long lines in the tests and in `filter_links`. No change in
   meaning.
8. **Step 6 (look at the page in a browser by hand)** was not done by the builder agent. The
   integration tests check the links, the bold link's `aria-current`, the forms and the redirects;
   the CUJ test still passes unchanged.

Results: before the code, the unit file failed with one `ImportError`, all 13 new integration tests
failed for the reasons in the plan, and the 4 protecting tests passed. After the code, `make test`,
`make test-cuj` and `make check` all pass (CUJ 1, Integration 35, Unit 7).

### After the code review

An adversarial code reviewer found no blockers. These fixes were made as a new commit:

1. **One table of filters.** `FILTERS` is now a list of `Filter` rows. Each row has the value in
   the address, the word on the link, the empty message, and `apply`: the function that makes the
   list smaller. `list_params` checks `show` against this table. `filter_todos` and `filter_links`
   look the row up with `chosen_filter(params)`. `page_context` passes `empty_message` instead of
   `show`, so the template has no filter words in it: it draws `<li>{{ empty_message }}</li>`. A new
   filter is now one new row.
2. **The nav's name** is `aria-label="Filter to-dos"`, not `"Show"`. "Show" alone did not say what
   the links do.
3. **Exact checks in the tests.**
   - The helper also lists the text of every `<span class="title">`: the to-dos shown, in order.
     The tests compare that list exactly (for example `["Buy milk"]`), instead of searching for a
     title anywhere on the page.
   - The empty messages are checked as whole elements, like `<li>Nothing left to do.</li>`.
   - The filter links are checked as the whole `<nav>` element, with its `aria-label`.
   - The `POST` form actions are compared exactly to the list of addresses (add, toggle, delete),
     not with "ends with `?show=...`".
4. **New tests.**
   - `test_no_empty_message_when_the_list_has_items`: no empty message on any filter when the list
     has items.
   - `test_empty_list_on_all_shows_the_old_message`: the exact old message on an empty `/`.
   - `test_filter_links_with_no_params` and `test_filter_links_keep_other_params` (unit). The second
     one replaces `list_params` with a stub that also keeps a pretend search parameter `q`, and
     checks every link keeps `q`.
5. **Each new or tighter test was seen failing against its own bug,** put in for a moment and then
   taken out:
   - Empty message outside `{% empty %}`: `test_no_empty_message_when_the_list_has_items` failed.
   - `filter_links` built from `{"show": value}` only: `test_filter_links_keep_other_params` failed.
   - Delete form posting to the add address, with the right query (the old "ends with" check would
     pass): `test_every_post_form_keeps_the_filter` and `test_add_error_keeps_the_filter` failed.
   - `filter_todos` returning every to-do: the title tests failed with, for example,
     `['Buy milk', 'Call home'] != ['Buy milk']`.
   - The All link always marked too: `test_chosen_filter_is_marked`, `test_add_error_keeps_the_filter`
     and the unit test failed (`['All', 'Active'] != ['Active']`).
   - `aria-label` taken off the nav: the three nav tests failed.
6. **No `CONVENTIONS` file exists** in the repository yet. The exact checks follow what the reviewer
   asked for.

After these fixes: CUJ 1, Integration 37, Unit 9, all passing; `make check` passes.

**Added to the work after the rebase on 12 and 11:** `main` now has `TodoQuerySet` with
`remaining()` (from 12). The `apply` functions in `FILTERS` must use the queryset's methods
(`lambda t: t.remaining()`, and `lambda t: t.completed()` if 11 adds it; if not, add `completed()`
to `TodoQuerySet`) instead of their own `filter(done=...)`.
Also, `test_every_post_form_keeps_the_filter` and `test_add_error_keeps_the_filter` compare the
exact list of form actions, so 11's footer form must be added to that list.

### After the rebase on 12 and 11

The branch was rebased on `main` with 12 and 11 in it (`git rebase --onto origin/main`, only this
feature's three commits). The clashes were in `views.py`, the template and `AGENTS.md`. Each one was
fixed by keeping both sides: `page_context` keeps 12's and 11's keys (`has_todos`,
`remaining_count`, `completed_ids`) and this feature's keys (`empty_message`, `list_query`,
`filter_links`). The template keeps 11's footer and 5's due date inside the title span.

Then the work in "After 12 and 11 are on `main`":

1. **`page_context`.** The count is `Todo.objects.remaining().count()`, `has_todos` is
   `Todo.objects.exists()`, and `completed_ids` comes from `Todo.objects.completed()`. None of them
   uses the filtered `todos`.
2. **`FILTERS`** uses the queryset's methods: Active is `t.remaining()`, Completed is
   `t.completed()`. 11 added `completed()`, so nothing was added to the model.
3. **Delete completed (11).** Its form's `action` ends with `{{ list_query }}`, and its view ends
   with `back_to_list(request)`.
4. **Exact form lists.** `forms_for` in `test_filter.py` now also lists `/delete-completed/` with the
   query. Before the code change, `test_every_post_form_keeps_the_filter` and
   `test_add_error_keeps_the_filter` failed: the footer form had no query.
5. **Shared helpers.** `PageParts` and `page_parts` moved to `todos/tests/integration/helpers.py`.
   11's `page_without_csrf`, `delete_completed_form` and `list_footer` moved there too, so both test
   files use one copy. `delete_completed_form` and `list_footer` got a `query` argument (default
   `""`), so a test can build the footer for a filtered page. `PageParts` now takes only the text
   before any tag inside the title span, because 5's due date is a `<small>` inside it.
6. **The three tests**, each seen failing against its bug (put in for a moment, then taken out):

   | Test | Bug | Result |
   |---|---|---|
   | `test_count_shows_on_completed_view_with_nothing_completed` | `has_todos` from the filtered `todos.exists()` | failed: no footer (the Active test failed too) |
   | the same test | `remaining_count` from the filtered `todos` | failed: `0 items left` instead of `1 item left` |
   | `test_count_on_active_view_with_everything_completed` | before the code: the footer form had no query | failed |
   | the same test | `completed_ids` from the filtered `todos` | failed: no delete-completed form (the two exact form-list tests failed too) |
   | `test_delete_completed_keeps_the_filter` | the view still ends with `redirect("todo_list")` | failed: `'/' != '/?show=completed'` |

   **One difference from the plan:** the plan's bug for the Active test was "count from the filtered
   `todos`". That bug cannot fail this test: on Active with everything completed, the right count
   is 0, and the filtered count is 0 too. The Completed test catches that bug. The Active test was
   shown failing against the bug it can catch instead: `completed_ids` from the filtered list.

After the rebase: `make test`, `make test-cuj` and `make check` all pass (CUJ 1, Integration 64,
Unit 12).
