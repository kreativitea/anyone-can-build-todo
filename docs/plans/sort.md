# Plan: sort the list (date added, due date, priority, title)

Status: **approved.**

This is feature 9, the first one in wave 3 of [the rollout plan](feature-rollout.md). The merge
order in wave 3 is: **9 sort** → 19 repeating → 15 subtasks.

An adversarial review (a reviewer whose job is to find what is wrong) checked the first version.
Every finding is fixed below. The biggest change: the sort is now **links**, like the filter, not a
select box.

**Where this starts.** The work starts on `main` **after waves 1 and 2 are merged**: 5 due date,
12 count, 11 delete completed, 8 filter, 6 priority, 7 notes, 4 edit, 10 search. So "how it fails
today" in the tests means: `main` with all of those in it. On that `main`:

- `Todo` has `title`, `done`, `due_date` (can be empty), `priority`, `notes`, `created_at`, and
  `Meta.ordering = ["created_at"]` (oldest first).
- `priority` is a small number from `Todo.Priority`: **High = 3, Medium = 2, Low = 1** (from the
  priority plan). So `order_by("-priority")` gives High, Medium, Low. This plan depends on it.
- `views.py` has `list_params(data)`, `list_query(params)`, `FILTERS`, `filter_todos`,
  `filter_links`, `search_todos`, `back_to_list`, `list_url` (from 4) and
  `page_context(request, form)`.
- `list_params` returns `show` first, then `q`. The search form keeps the other parameters with
  hidden inputs (`search_keeps`: every parameter except `q`). "Clear search" keeps them too.
- The filter links are in `<nav aria-label="Filter to-dos">`, and the chosen one has
  `aria-current="page"`.
- The shared test helpers (`PageParts`, `page_parts`) are in
  `todos/tests/integration/helpers.py`.

If a name on `main` is different from this list, the builder uses what is really on `main` and says
so in the PR.

## What we want

Next to the filter links, a row of **sort links**:

**Sort by:** Date added · Due date · Priority · Title

- **Date added** — oldest first. This is the order today, and stays the default.
- **Due date** — the soonest date first. To-dos with **no** due date go at the end.
- **Priority** — High first, then Medium, then Low.
- **Title** — A to Z. Big and small letters A–Z count as the same (`apple` before `Banana`).

The chosen sort stays when the person filters, searches, adds, marks done, deletes or edits. The
page needs no JavaScript.

## Decisions

### The sort is in the address, like the filter and the search

- One more **query parameter** (the part of an address after `?`): `sort`.
- The values are a **fixed list**: `created`, `due`, `priority`, `title`.
- `created` (Date added) is the default. The default is **not** put in the address, so the plain
  address `/` still means "oldest first". `/?sort=created` means the same.
- **An unknown value means the default.** `/?sort=banana`, `/?sort=TITLE`, `/?sort=` and
  `/?sort=-title` all show the default order, with Date added marked. No error page, like the
  filter.

### Links, like the filter

```html
<nav class="sort" aria-label="Sort by">
  Sort by:
  {% for link in sort_links %}
    <a href="{{ link.url }}"{% if link.current %} aria-current="true"{% endif %}>{{ link.label }}</a>
  {% endfor %}
</nav>
```

- Choosing a sort only reads, so a normal link (a `GET` request) is right. No form, no button, no
  hidden inputs.
- The view builds the links with `sort_links(params)`, the same way `filter_links` builds the
  filter links. Each link keeps the other parameters, because it is made with
  `list_params({**params, "sort": value})`. On `/?show=active&q=milk`, the Title link is
  `/?show=active&q=milk&sort=title`.
- **`aria-current="true"`, not `"page"`.** `aria-current` tells a screen reader (a program that
  reads the page aloud) "this one is chosen". `"page"` means "the page you are on"; the filter uses
  it. A sort is not a page, so we use `"true"`, which means "the chosen one in this group". It also
  keeps the filter's tests right: they count `aria-current="page"` on the page, and expect one.
- `aria-label="Sort by"` gives the `<nav>` a name, so a screen reader can tell the two rows of
  links apart ("Filter to-dos" and "Sort by").
- The CSS makes the chosen link **bold**, chosen by `aria-current`, like the filter. The look and
  the meaning come from one place.

### One fixed direction for each choice

We do **not** add "up / down" (ascending / descending). Each choice has the one direction most
people want: what is due soonest, what matters most, A to Z, oldest first. This keeps the page to
one row of four short words. A direction can be added later as new values, with no change to the
design.

### Every order has more keys, so ties never jump

A **tie** is when two to-dos have the same value, for example two High to-dos. Then the database
may return them in any order, and the list could change between two page loads. So each choice
has a second key, and every choice ends with **`created_at`, then `pk`** (the id):

| `sort` | Words | `order_by(...)` |
|---|---|---|
| `created` (default) | Date added | `"created_at", "pk"` |
| `due` | Due date | `F("due_date").asc(nulls_last=True), "-priority", "created_at", "pk"` |
| `priority` | Priority | `"-priority", F("due_date").asc(nulls_last=True), "created_at", "pk"` |
| `title` | Title | `Lower("title"), "created_at", "pk"` |

- **Due date, then priority:** two to-dos due on the same day show the High one first.
- **Priority, then due date:** among the High to-dos, the one due soonest is first. A High to-do
  with no date comes after the dated High ones.
- **`F("due_date").asc(nulls_last=True)`**: `F` names a column. `asc` means smallest first.
  `NULL` is how the database writes "no value". `nulls_last=True` puts the to-dos with no date
  **after** the dated ones. Without it, SQLite puts them **first**, which is wrong.
- **`Lower("title")`**: compares the titles in small letters, so `apple` comes before `Banana`.
  Without it, every capital letter comes before every small letter (`Zoo` before `apple`).
- **`pk` is a safety key.** Two to-dos almost never have the very same `created_at` (it has
  microseconds). `pk` makes the order certain even then. We **cannot** test it on SQLite: when
  `created_at` is the same, SQLite already returns the rows in id order, with or without `pk`. We
  keep it in the code, and say so here.

### Titles in Japanese, and other letters

- SQLite's `lower()` changes only the letters **A–Z**. Every other character stays the same.
- Titles are compared **by code point**: the number each character has in Unicode. So:
  - every A–Z title comes before every Japanese title;
  - hiragana (あいう…) is in あいうえお order, and comes before katakana;
  - **kanji are not sorted by reading.** 牛乳 and 卵 are in Unicode order, not in the order of
    ぎゅうにゅう and たまご;
  - **`É`** comes after all of A–Z and a–z, so `Éclair` is after `zebra`, and `Éclair` and
    `éclair` are not seen as the same;
  - **full-width letters** (`Ａｐｐｌｅ`, often typed with a Japanese keyboard) are not the same
    as `Apple`. They come after all hiragana, katakana and kanji.
- We test only what is true on **any** database: A–Z with mixed case, and あ before い before う.
  We do **not** pin the kanji, `É` or full-width order in a test. That would be a test for a
  weakness, like the search plan's `CAFÉ` rule. A better database later (PostgreSQL) may change it
  for the better.

### Sort, filter and search all work together

They run one after another on the same query: filter, then search, then sort. So
`/?show=active&q=milk&sort=due` shows the active to-dos with "milk", soonest first.

`list_params` gets one more check, **after** `q`. So the address is always in the order `show`,
`q`, `sort`. Because of the helpers from 8 and 10, **with no change to their code**:

- the filter links keep the sort: on `/?sort=due`, the Active link is `/?show=active&sort=due`;
- the search form keeps the sort: `search_keeps` is "every parameter except `q`", so it now has a
  hidden `sort` input;
- "Clear search" keeps the sort: on `/?q=milk&sort=due`, it goes to `/?sort=due`;
- every `POST` form ends with `{{ list_query }}`, the Edit link too, and `back_to_list` sends the
  browser back with the sort.

### Where it goes on the page

Add form, search form, filter links, **sort links**, list, footer.

### Other decisions

- **`Meta.ordering` stays `["created_at"]`.** The admin and every other query keep their order.
  `order_by` in the view replaces it only for the list page.
- **Completed to-dos are not moved to the end.** Sort only sorts. To hide them, use the Active
  filter.
- **A new to-do goes where the sort puts it,** not always at the end. On Title, `Apple` appears at
  the top.
- **The empty message does not change.** Sorting never hides a to-do.
- **The count, "Delete completed" and its ids** read the whole table, not the sorted list.
- **No index** in the database. A list this small does not need one. So **no migration**.

## What we will not do (yet)

- **No up/down direction** (see Decisions).
- **No remembering the sort** for the next visit. Only the address remembers it.
- **No sorting by reading** for kanji, and no sort that understands `É` or full-width letters.
- **No "My order".** Feature 16 (drag to reorder, wave 5) adds it later. This plan does not prepare
  for it, and does not block it: 16 adds one row to `SORTS` and may change `DEFAULT_SORT`.
- **No JavaScript.**

## Changes in behaviour

1. `/?sort=due`, `/?sort=priority` and `/?sort=title` show the list in that order. Before, `sort`
   was ignored.
2. The page has a "Sort by" row of four links, and one is marked as chosen.
3. The filter links, the search form, "Clear search", every `POST` form, the Edit link and every
   redirect keep `sort`. Before, `sort` was dropped.

What stays the same: `/` is oldest first; the filter, the search and the messages work as before;
add, toggle, delete and edit accept `POST` only.

## The changes, one file at a time

No model change, so **no migration**.

### 1. `todos/views.py`

**Imports:**

```python
from django.db.models import F
from django.db.models.functions import Lower
```

**The one table of choices**, next to `FILTERS`. The first row is the default.

```python
# The sort links: (the value in the address, the word on the page, the order).
# The first one is the default. Every order ends with created_at, then pk, so ties never jump.
DUE_SOONEST_FIRST = F("due_date").asc(nulls_last=True)
SORTS = [
    ("created", "Date added", ("created_at", "pk")),
    ("due", "Due date", (DUE_SOONEST_FIRST, "-priority", "created_at", "pk")),
    ("priority", "Priority", ("-priority", DUE_SOONEST_FIRST, "created_at", "pk")),
    ("title", "Title", (Lower("title"), "created_at", "pk")),
]
DEFAULT_SORT = SORTS[0][0]
SORT_ORDERS = {value: order for value, _label, order in SORTS}
```

**In `list_params`**, after the `q` check (so the address is `show`, `q`, `sort`):

```python
    if data.get("sort") in SORT_ORDERS and data["sort"] != DEFAULT_SORT:
        params["sort"] = data["sort"]
```

Only a value from the table is kept. The default is dropped, like `show=all`.

**Two new functions**, next to `filter_todos` and `filter_links`:

```python
def sort_todos(todos, params):
    """The to-dos in the chosen order. Ties keep the order they were added."""
    return todos.order_by(*SORT_ORDERS[params.get("sort", DEFAULT_SORT)])


def sort_links(params):
    """The Sort by links, each one keeping the other parameters."""
    chosen = params.get("sort", DEFAULT_SORT)
    return [
        {
            "label": label,
            "url": reverse("todo_list") + list_query(list_params({**params, "sort": value})),
            "current": value == chosen,
        }
        for value, label, _order in SORTS
    ]
```

**In `page_context`**: one line for the query (after search), and one key:

```python
    todos = sort_todos(todos, params)        # new, after search_todos
    ...
        "sort_links": sort_links(params),    # new
```

Every other key and every view: **no change**.

### 2. `todos/templates/todos/todo_list.html`

- The sort `<nav>` (see Decisions), right after the filter `<nav>`.
- The CSS, the same as the filter row:

  ```css
  nav.sort { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; }
  nav.sort a[aria-current="true"] { font-weight: bold; text-decoration: none; color: inherit; }
  ```

  On a phone, "Sort by:" and four short words fit on one row. If not, `flex-wrap` moves the last
  link to the next row. (If 4 made a shared `base.html`, the CSS goes where the filter CSS is.)

### 3. `todos/models.py`, `todos/forms.py`, `todos/urls.py` — no change

### 4. `AGENTS.md`

- `todos/views.py` row: add "The list can be sorted (`?sort=due`, `priority`, `title`; the default
  is `created`, Date added, oldest first). `SORTS` is the one table of choices. Every order ends
  with `created_at`, then `pk`. `list_params` keeps the order `show`, `q`, `sort`."
- Template row: "add form, search form, filter links, sort links, the list and the footer."

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code.

A **`subTest`** is a small named part of one test. If one part fails, the others still run, and the
report says which part failed. We use it when one test checks the same rule with several inputs.

**How to make an order test real.** Today the list is always oldest first. So in every order
test, the to-do that should come **first** is made **last**. Then the test cannot pass by
chance, only because the list is still oldest first.

**How to make a tie test real.** For two to-dos that tie, make `B` first and `A` second. Then set
`A`'s `created_at` to **earlier** than `B`'s, with
`Todo.objects.filter(pk=a.pk).update(created_at=...)`. Now the id order (`B`, `A`) and the
date-added order (`A`, `B`) disagree. Without the tie key, SQLite returns them in id order, and the
test fails.

**How to check the order.** `[t.title for t in response.context["todos"]]` must equal an exact
list. The template draws `todos` in this order with a `for` loop.

All dates in tests are written with the year, for example `2026-10-12`.

### Top: the CUJ test — no change

Sorting is a new way to look at the same list, not a new journey. The CUJ test opens `/`, which
keeps the default order, so it still passes.

### Bottom: unit tests (`todos/tests/unit/test_list_params.py`, made by 8)

`SimpleTestCase` (Django's test class with no database).

| Test | What it checks | How it fails today |
|---|---|---|
| `test_list_params_keeps_the_sort` | `sort=due`, `sort=priority`, `sort=title` → `{"sort": ...}` (a `subTest` each) | `{}`: `sort` is dropped |
| `test_list_params_drops_the_default_and_unknown_sorts` | `sort=created`, `sort=`, `sort=banana`, `sort=TITLE`, `sort=-title`, `sort=title%0D%0A`, `sort=title%26next%3Dx`, no `sort` → `{}` | **passes today** (protecting). Show it failing against a deliberate bug: keep any `sort` value |
| `test_list_params_order_is_show_q_sort` | `sort=due&q=milk&show=active` → `list(result) == ["show", "q", "sort"]` | `["show", "q"]` |
| `test_list_params_twice_is_the_same` (made by 8) | add rows `sort=due` and `show=active&q=milk&sort=title` | **passes today**: `sort` is dropped both times, so both sides are equal. Protecting: it matters because `sort_links` and `filter_links` call `list_params` again. Show it failing against a deliberate bug: store the label (`"Due date"`) instead of the value |
| `test_sort_links` | `sort_links({"show": "active"})` → four links, in the order Date added, Due date, Priority, Title, with the URLs `/?show=active`, `/?show=active&sort=due`, `/?show=active&sort=priority`, `/?show=active&sort=title`; only Date added is `current`. `sort_links({"sort": "title"})`: only Title is `current` | `ImportError`: there is no `sort_links` |

### Middle: integration tests (`todos/tests/integration/test_sort.py`, new file)

A new file, so it does not clash with 19 and 15. It uses `page_parts` from `helpers.py`.

**Tests for new behaviour.** These must **fail** before the change. The to-dos are made in the
order written.

| Test | The to-dos | Open | Expected order | How it fails today |
|---|---|---|---|---|
| `test_sort_by_due_date` | `No date` (no date), `Later` (2026-10-20), `Soon` (2026-10-12) | `/?sort=due` | `Soon`, `Later`, `No date` | oldest first: `No date`, `Later`, `Soon` |
| `test_due_date_ties_go_high_priority_first` | `Low` (2026-10-12, Low), `High` (2026-10-12, High) | `/?sort=due` | `High`, `Low` | `Low`, `High` |
| `test_sort_by_priority` | `Low` (Low), `Medium` (Medium), `High` (High) | `/?sort=priority` | `High`, `Medium`, `Low` | `Low`, `Medium`, `High` |
| `test_priority_ties_go_soonest_due_first` | `Low` (Low), `High no date` (High), `High later` (High, 2026-10-20), `High soon` (High, 2026-10-12) | `/?sort=priority` | `High soon`, `High later`, `High no date`, `Low` | `Low` first |
| `test_sort_by_title_ignores_case` | `cherry`, `Banana`, `apple` | `/?sort=title` | `apple`, `Banana`, `cherry` | `cherry`, `Banana`, `apple` |
| `test_title_ties_keep_date_added_order` | `Buy milk` (B), `buy milk` (A, then its `created_at` set earlier than B's), `apple` | `/?sort=title` | `apple`, `buy milk`, `Buy milk` | `buy milk`, `Buy milk`, `apple`. (Without the `created_at` key it would be `apple`, `Buy milk`, `buy milk`) |
| `test_sort_by_title_hiragana` | `うどん`, `いちご`, `あめ` | `/?sort=title` | `あめ`, `いちご`, `うどん` | the reverse |
| `test_sort_links_are_on_the_page` | — | `/` | `assertContains(..., html=True)` with the whole `<nav class="sort" aria-label="Sort by">`: `Sort by:`, then `<a href="/" aria-current="true">Date added</a>`, `<a href="/?sort=due">Due date</a>`, `<a href="/?sort=priority">Priority</a>`, `<a href="/?sort=title">Title</a>` | there are no sort links |
| `test_chosen_sort_is_marked` | — | a `subTest` each: `/?sort=priority` → only the Priority link has `aria-current="true"`; `/?sort=banana` → only Date added has it. Both: `aria-current="page"` is still on the filter's All link only | there are no sort links |
| `test_sort_is_kept_everywhere` | `Buy milk` (active) | `/?show=active&q=milk&sort=due`; a `subTest` each, each one exact (`html=True`): the Active link `<a href="/?show=active&amp;q=milk&amp;sort=due" aria-current="page">Active</a>`; the search form's `<input type="hidden" name="sort" value="due">`; `<a href="/?show=active&amp;sort=due">Clear search</a>`; the Edit link `<a class="edit" href="/<id>/edit/?show=active&amp;q=milk&amp;sort=due" aria-label="Edit Buy milk">Edit</a>`; the Title link `<a href="/?show=active&amp;q=milk&amp;sort=title">Title</a>` | `sort` is dropped from each one |
| `test_every_post_form_keeps_the_sort` | one active, one completed | `/?show=active&sort=title`; `page_parts` finds every `POST` form (add, toggle, delete, delete completed); **every** action ends with `?show=active&sort=title` | the actions end with `?show=active` |
| `test_post_goes_back_with_the_sort` | `Buy milk` | a `subTest` each: post to toggle, to delete, and `New` to add, each with `?show=active&sort=due` | redirect to `/?show=active&sort=due` exactly | redirect to `/?show=active` |
| `test_sort_filter_and_search_together` | `Milk later` (active, 2026-10-20), `Milk done` (completed, 2026-10-01), `Call home` (active, 2026-10-05), `Milk soon` (active, 2026-10-12) | `/?show=active&q=milk&sort=due` | `Milk soon`, `Milk later` | `Milk later`, `Milk soon`: oldest first |

**Tests that protect what already works.** These **pass** before the change, and must still pass
after:

| Test | What it checks | The deliberate bug that makes it fail |
|---|---|---|
| `test_default_is_oldest_first` | to-dos made in the order `C`, `A`, `B`; `/`, `/?sort=created` and `/?sort=banana` (a `subTest` each) all give `C`, `A`, `B` | default order `"-created_at"` |
| `test_redirect_drops_a_bad_sort` | toggle with `?sort=banana`, `?sort=created`, `?sort=title%0D%0ALocation:%20https://evil.example` (a `subTest` each): redirect to `/` exactly | keep any `sort` value in `list_params` |

**More checks against a deliberate bug**, after the code is written. Do each one for a moment, see
the named test fail, and put the code back. `git diff` must not show any of them.

- Remove `nulls_last=True`: `test_sort_by_due_date` and `test_priority_ties_go_soonest_due_first`
  fail.
- Remove `"-priority"` from the `due` row: `test_due_date_ties_go_high_priority_first` fails.
- Remove the due date key from the `priority` row: `test_priority_ties_go_soonest_due_first` fails.
- Remove `"created_at"` from the `title` row: `test_title_ties_keep_date_added_order` fails.
- Use `"title"` instead of `Lower("title")`: `test_sort_by_title_ignores_case` fails.

There is **no test for `pk`** (see Decisions: SQLite cannot show the difference).

Every test that exists before this change must also still pass, especially `test_filter.py`, the
search tests, and `test_list_page_loads`.

## Steps, in order

1. Write the unit tests and `test_sort.py`. Run `make test`: the new-behaviour tests fail as
   listed (`test_sort_links` with `ImportError`), and the protecting tests pass.
2. Change `views.py`: the imports, `SORTS`, the `list_params` check, `sort_todos`, `sort_links`,
   and the two `page_context` lines.
3. Change the template: the sort `<nav>` and the CSS.
4. Run `make test`: every test passes. Do the deliberate-bug checks, one at a time.
5. Run `make test-cuj`: the CUJ test still passes.
6. Run `make run`. Add to-dos with and without due dates, each priority, and English and Japanese
   titles. Try each sort, with a filter and a search. Press Done, Delete and Edit, and check the
   sort stays. Make the window narrow, like a phone, and check the sort row fits.
7. Update `AGENTS.md`.
8. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected".
9. Run `make check`. Commit.

## Risks

- **This plan reads code that is not on `main` yet** (`search_todos`, `search_keeps`, `list_url`,
  the Edit link, `priority`, `page_parts`). If a wave 2 feature changes those names before it
  merges, the builder follows what is really on `main`, and says what changed.
- **Priority numbers.** The sort trusts High = 3, Medium = 2, Low = 1. `test_sort_by_priority`
  catches a change.
- **SQLite and `lower()`.** Only A–Z are made small. `É`, full-width letters and kanji are in
  Unicode order. This is written in "What we will not do (yet)", and no test pins it.
- **Feature 16 (drag to reorder)** plans to add `("manual", "My order")` as the first row of `SORTS`
  and make it `DEFAULT_SORT`. Then `/` shows My order, `?sort=created` stays in the address, and
  `test_default_is_oldest_first`, `test_sort_links_are_on_the_page`, `test_chosen_sort_is_marked`
  and the `sort=created` unit rows **change on purpose** in 16's branch.
- **Subtasks (15)** start the list from `with_subtask_progress()`, an `annotate` with `Count`, which
  makes the database use `JOIN` and `GROUP BY`. Sort orders only by `Todo`'s own columns, and Django
  adds them to the `GROUP BY` by itself, so the counts and the order stay right. 15 keeps sort's
  `order_by` and runs the sort tests after its rebase. A later sort by a **count** (not planned)
  would need more care.
- **Repeating (19).** When a repeating to-do is done, its next copy is a **new** to-do with a new
  `created_at`. So on Date added it goes to the **bottom**, not where the old one was. On Due date it
  goes to its new date. This is expected; 19's plan should say it to the person.
- **Collisions in wave 3.** 19 and 15 also change `page_context` and the template. Sort merges
  first, and only adds lines. They rebase on it.
