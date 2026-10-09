# Plan: put the to-dos in my own order (Move up / Move down)

Status: **done.** Approved with the owner's answers (buttons only; "Date added" stays the default
sort). Built on `feature/reorder`, on top of lists (13); see "What happened" at the end.

This is feature 16, the last one in wave 5 of [the rollout plan](feature-rollout.md). It merges
**after lists (13) and tags (14)**. An adversarial review (a reviewer whose job is to find what is
wrong) checked the first version. Every finding is fixed below.

**The owner's answers.**

- **Buttons only.** This plan is a saved order per list and **Move up / Move down** buttons. There
  is **no JavaScript**, no dragging and no `/reorder/` address. (Dragging was planned as "16b"; the
  owner said no, so it is not built. The buttons already do the whole job, also on phones.)
- **"Date added" stays the default sort.** "My order" is a new sort choice, not the default.

## Where this starts

`main` after waves 1–4, lists (13) and tags (14). "How it fails today" in the tests means that
`main`. The names come from lists.md, accounts.md, sort.md and CONVENTIONS:

- `Todo.todo_list`: the list of a to-do. It is a **foreign key** (a column that points at a row of
  another table), with `on_delete=models.RESTRICT`. `Todo.owner` always equals
  `todo.todo_list.owner`. `Todo.save()` sets it.
- `Todo.objects.for_user(user)`: the to-dos this person may use. `get_list(request, list_id)`: one
  of this person's lists, or 404.
- `page_context(request, form, current_list)`, `back_to_list(request, current_list)`,
  `list_params`, `list_query`, `filter_todos`, `search_todos`, the tag filter, `sort_todos`,
  `sort_links(params, current_list)`.
- `SORTS` is one table of **links** (not a select box): `created` ("Date added", the default),
  `due`, `priority`, `title`. The chosen link has `aria-current="true"`. Every order ends with
  `created_at`, then `pk`.
- `Meta.ordering = ["created_at", "pk"]`.
- `base.html` holds the `<head>` and the shared CSS. Every page extends it.
- Test helpers: `LoggedInTestCase` (with `cls.todo_list` and `self.make_todo(...)`), `make_user()`,
  and `page_parts` in `todos/tests/integration/helpers.py`.

The builder checks each name first. If one is different, change the name, not the idea.

## What we want

A person can put the to-dos of a list **in their own order**:

- Each to-do has two small buttons: **↑ (Move up)** and **↓ (Move down)**.
- They work with **no JavaScript**, with a keyboard, and with a screen reader (a program that reads
  the page aloud).
- The order is **saved**. It is the same after a reload, and on another computer.
- The order is **per list**. A move in "Work" does not change "Home".

## Words

- **Position**: a number on each to-do. A smaller number is higher in the list.
- **My order**: the new sort choice. It means "the order I made by hand".
- **Visible rows**: the to-dos on the page now. A filter (Active, Completed), a search or a tag can
  hide some to-dos of the list. Those are **hidden rows**.
- **Transaction**: a group of database changes that are saved all together, or not at all.

## Decisions

### 1. A whole number, `position`, that can be empty

- New field: `position = models.PositiveIntegerField(null=True, blank=True, editable=False)`.
  - `editable=False` keeps it out of `TodoForm`, `TodoEditForm` and the admin form. Only the move
    buttons change it.
  - **Empty (`NULL`) means "not placed yet".** My order sorts empty positions **last**:
    `F("position").asc(nulls_last=True)`, then `created_at`, then `pk`.
- So a to-do with no number (see Decision 3) is never lost and never jumps to the top. It sits at
  the end of the list, oldest first.
- **No unique rule in the database** on `(todo_list, position)`. The reviewer checked it: swapping
  two numbers with `bulk_update` under a unique rule fails on SQLite with `IntegrityError: UNIQUE
  constraint failed`. SQLite checks the rule after each row, not at the end. So a tie is possible.
  The order still has a tie-breaker (`created_at`, `pk`), and Decision 5 removes ties.
- **A delete leaves a gap** (1, 2, 4). That is fine: only the order of the numbers matters.

### 2. `Meta.ordering` does not change

- `Meta.ordering` stays `["created_at", "pk"]`. The admin, the tests from `main` and every other
  query keep their order.
- Why: the reviewer checked `ordering = ["position", ...]`. Then `main`'s
  `test_list_is_oldest_first` fails, and to-dos of two lists mix by number (1, 1, 2, 2) in the
  admin.
- A new queryset method, `in_my_order()`, gives the hand-made order. **Only `sort_todos` uses it**
  (for `sort=manual`).

### 3. Every new to-do gets the next number in its list

`Todo.save()` does it, not the add view. So **every** way that makes a to-do gets a number: the
add form, the admin, and the next copy of a repeating to-do (19).

```python
def save(self, *args, **kwargs):
    # (13 sets owner from todo_list here.)
    if self.pk and self.todo_list_id != getattr(self, "_loaded_list_id", self.todo_list_id):
        self.position = None  # moved to another list: go to the end of the new one
    with transaction.atomic():
        if self.position is None:
            self.position = Todo.objects.next_position(self.todo_list_id)
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "position"}
        super().save(*args, **kwargs)
```

The edge cases:

- **Moved to another list** (the edit page, or the admin): `from_db` remembers the list the to-do
  had when it was read (`_loaded_list_id`). This is the pattern in Django's own documentation. If
  the list changed, the to-do goes to the **end of the new list**. No view needs extra code.
- **`save(update_fields=[...])`**: if `save()` gives a number, it adds `"position"` to
  `update_fields`. Otherwise the number would be set in Python but never written.
- **`bulk_create` and `loaddata`** do not call `save()`. Their to-dos keep an empty position. That
  is safe: empty sorts last (Decision 1), and the next move numbers the list (Decision 5).
- **Two adds at the same moment**: `next_position` reads the largest number and the insert writes
  the new row, inside one transaction. With Decision 6, SQLite lets only one such transaction run
  at a time. So they cannot get the same number.

### 4. Old to-dos are numbered by age, per list (a data migration)

- Two migrations:
  1. Django makes the first one from `models.py`. It adds `position`, empty for every row.
  2. The second one is `makemigrations --empty todos --name number_todos`, plus **one line**:
     `migrations.RunPython(number_existing_todos, migrations.RunPython.noop)`.
- The logic is a normal function, `number_existing_todos(apps, schema_editor)`, in
  `todos/ordering.py`. For each list, it sorts the to-dos by `created_at`, then `pk`, and gives
  them 1, 2, 3, ….
- It uses `apps.get_model("todos", "Todo")`. That is the **historical model**: the model as it was
  at that migration. So it keeps working when `models.py` changes later. It uses
  `bulk_update(..., ["position"])`, which does not call `save()`.
- `RunPython.noop` means "going back does nothing". The field is removed anyway.
- **For the merge queue:** delete this branch's two migration files. Run `makemigrations`. Run
  `makemigrations --empty todos --name number_todos`. Paste the one line, and the import
  `from todos.ordering import number_existing_todos`. Test it on a copy of a database with old
  to-dos in two lists.
- **On day one, My order is exactly oldest first** in every list.

### 5. A move swaps two numbers

- "Move up" finds the **visible neighbour** above the to-do. "Move down" finds the one below. The
  two to-dos **swap their `position` values**. That is two small `UPDATE`s in one transaction.
- **Renumber only when needed.** If the list has an empty position or two to-dos with the same
  number, the move first renumbers the whole list 1..n (in My order), then swaps. Normally this
  never happens. It is there for `bulk_create`, `loaddata` and old rows.
- **"Move up" on the first visible row**, and **"Move down" on the last**, change nothing. The page
  shows those two buttons as `disabled`.
- Everything happens inside one transaction: renumber if needed, read the visible ids, swap.

### 6. SQLite takes the write lock at the start of a transaction

- Add `"OPTIONS": {"transaction_mode": "IMMEDIATE"}` to `DATABASES["default"]` in
  `config/settings.py` (Django 5.1+; we have 5.2).
- **Why.** By default, SQLite starts a transaction as a reader. It asks for the write lock only at
  the first write. When two requests read and then write at the same time, the second one fails
  **at once** with `database is locked`. The reviewer reproduced this with two threads: one failed
  with the default mode; both succeeded with `IMMEDIATE`. With `IMMEDIATE`, the second request
  **waits** (up to 5 seconds) and then runs.
- This helps every feature that reads and then writes (delete completed, repeating, moves).
- **`select_for_update()` is not used.** On SQLite it does nothing (the reviewer checked:
  `has_select_for_update` is `False`). It would look like protection, but it is not.
- Cost: an `atomic()` block that only reads also takes the write lock. Our transactions are short,
  so this is fine.

### 7. "My order" is a sort choice

- Add `("manual", "My order", <in_my_order keys>)` to `SORTS`.
- **The Move buttons are shown only in My order.** In "Due date" order, a "Move up" that changes
  nothing on the screen would be confusing.
- **"Date added" stays the default** (the owner's answer). "My order" is the **last** row of
  `SORTS`, at `?sort=manual`. So the Move buttons appear only at `?sort=manual`. `DEFAULT_SORT`, the
  plain address and every default test in sort.md do not change.
- **On day one, "My order" and "Date added" show the same order** (Decision 4). The two links look
  the same until someone moves a to-do. This is expected, not a bug.
- Only `test_sort_links_are_on_the_page` and `test_sort_links` (unit) change: they list **five**
  links, with `<a href="/lists/<id>/?sort=manual">My order</a>` last. `list_params` keeps
  `sort=manual` like any other non-default sort; one row is added to
  `test_list_params_keeps_the_sort`.

### 8. With a filter or a search, a move still keeps the whole list in order

The problem: on "Active", completed to-dos are hidden. The full list could be `A, (done X), B`. On
the page the person sees `A, B`.

- The move view builds the **visible rows** with the same code as the page. One helper,
  `shown_todos(request, current_list, params)`, applies the filter, the search and the tag.
  `page_context` and the move view both call it, so they can never disagree.
- The neighbour is the next **visible** row. In the example, "Move up" on `B` swaps with `A`:
  `A` gets B's number, `B` gets A's number. The result is `B, X, A`.
- So every press moves the row **one place on the screen**. It never moves "behind" a hidden row
  with no change on the screen.
- `X` keeps its number. The hidden rows keep their order relative to each other. When the person
  clicks "All", nothing looks shuffled.
- If the to-do is not visible (an old page with another filter), the neighbour comes from the full
  list.

### 9. The move buttons

- One small form per row, with **two buttons**: `name="direction" value="up"` and
  `value="down"`. It posts to `/<pk>/move/{{ list_query }}`.
- The buttons show `↑` and `↓`. The accessible name says what happens, like the Edit link does:
  `aria-label="Move Buy milk up"`, and `title="Move up"` for a mouse tooltip.
- They are normal `<button>`s. The keyboard reaches them with Tab. Enter or Space presses them.
  This is the **accessible way to reorder**. (WCAG is the rule book for accessible web pages.
  Rule 2.5.7 says: anything you can do by dragging, you must also be able to do without dragging.
  This feature has no dragging at all.)
- After a move, the redirect goes to `back_to_list(request, current_list)` plus `#todo-<pk>`. Each
  row has `id="todo-<pk>"`. The browser scrolls to the moved row, and the next Tab starts there.
  The fragment is built from the integer `pk`, never from the request.
- A `direction` that is not `up` or `down` → **400** (bad request). Nothing changes.

### 10. Who may move

- The to-do comes from `get_object_or_404(Todo.objects.for_user(request.user), pk=pk)`. Another
  person's to-do → **404**, and nothing changes.
- **Not `owned_by`.** A move changes the order, not the list itself. So when sharing (20) comes,
  **editors** of a shared list may move to-dos. Sharing replaces this line with
  `get_todo_or_deny(request.user, pk, need=EDIT)`, as its plan says (editors 302, viewers 403). If
  this feature used an owner-only query, editors would get a 404 later.

### 11. Two tabs at the same time

- Each move reads the list **fresh, inside the transaction**, then swaps. With Decision 6, a second
  move waits for the first one. So no move is lost, and no number is doubled.
- A Move button in an **old tab** moves the to-do relative to the order **in the database now**,
  not the old page. The redirect then shows the real order. This is good enough.

## What we will not do (yet)

- **No dragging, and no JavaScript.** The owner chose buttons only.
- **No "move to top" / "move to bottom"**, and no typing a position number.
- **No order across lists.** Each list has its own order.
- **No moving a to-do into another list from the list page.** The edit page does it, and the to-do
  goes to the end of the new list.
- **No undo** of a move. Press the other arrow.

## Changes in behaviour

1. A new sort choice, **My order** (`?sort=manual`), the last sort link. "Date added" stays the
   default.
2. In My order, each row has ↑ and ↓. The first ↑ and the last ↓ are disabled.
3. A new to-do goes to the end of **its list** in My order.
4. A to-do moved to another list (edit page or admin) goes to the end of that list.
5. A new address: `POST /<pk>/move/`.
6. SQLite transactions take the write lock at the start (`IMMEDIATE`).

What stays the same: `Meta.ordering`; every other sort; filter, search and tags; Add, Done, Undo,
Edit, Delete, Delete completed; every change is a `POST`; another person's to-do is a 404.

## The changes, one file at a time

### 1. `config/settings.py`

`"OPTIONS": {"transaction_mode": "IMMEDIATE"}` in `DATABASES["default"]`, with a comment: "the
second writer waits instead of failing with 'database is locked'".

### 2. `todos/models.py`

- `position = models.PositiveIntegerField(null=True, blank=True, editable=False)` (after the
  fields that are already there).
- `TodoQuerySet.in_my_order()` →
  `self.order_by(F("position").asc(nulls_last=True), "created_at", "pk")`.
- `TodoQuerySet.next_position(todo_list_id)` →
  `(self.filter(todo_list_id=todo_list_id).aggregate(Max("position"))["position__max"] or 0) + 1`.
  The database finds the largest number, not a Python loop.
- `Todo.from_db(...)`: remember `_loaded_list_id`. `Todo.save()`: as in Decision 3.
- `Meta.ordering` does **not** change.

### 3. `todos/migrations/` — two new files

Made as in Decision 4. The only hand-written part is the one `RunPython` line in the `--empty` file.

### 4. `todos/ordering.py` — new file

- `number_existing_todos(apps, schema_editor)`: the data migration (Decision 4).
- `renumber(todos)`: gives 1..n in My order; `bulk_update`s only the rows that changed.
- `move(todo, shown, direction)`: in `transaction.atomic()`. If the list has an empty or a repeated
  number (counted by the database), `renumber` first. Then the ids of `shown.in_my_order()`. Find
  the neighbour. Swap the two numbers with two `QuerySet.update()` calls. Return quietly at the
  first or last row.

### 5. `todos/views.py`

- `SORTS`: add the `manual` row **last**. `DEFAULT_SORT` stays `created`.
- `shown_todos(request, current_list, params)`: the filter, search and tag steps, moved out of
  `page_context`. `page_context` calls it, then `sort_todos`.
- `page_context`: one new key, `"can_move"` (True when the sort is `manual`). One key per line.
- New view:

```python
@require_POST
def todo_move(request, pk):
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    direction = request.POST.get("direction")
    if direction not in ("up", "down"):
        return HttpResponseBadRequest("direction must be up or down")
    params = list_params(request.GET)
    move(todo, shown_todos(request, todo.todo_list, params), direction)
    response = back_to_list(request, todo.todo_list)
    response["Location"] += f"#todo-{todo.pk}"
    return response
```

### 6. `todos/urls.py`

`path("<int:pk>/move/", views.todo_move, name="todo_move"),` next to toggle and delete.

### 7. `todos/templates/todos/todo_list.html`

- Each `<li>` gets `id="todo-{{ todo.pk }}"`.
- Only when `can_move`, each row gets:

```html
<form class="move" method="post" action="{% url 'todo_move' todo.pk %}{{ list_query }}">
  {% csrf_token %}
  <button type="submit" name="direction" value="up" aria-label="Move {{ todo.title }} up" title="Move up"{% if forloop.first %} disabled{% endif %}>↑</button>
  <button type="submit" name="direction" value="down" aria-label="Move {{ todo.title }} down" title="Move down"{% if forloop.last %} disabled{% endif %}>↓</button>
</form>
```

No `<script>`, so `base.html` does not change.

### 8. `AGENTS.md`

Add `todos/ordering.py` to the file table: "the hand-made order: numbering and moving". Add one
line to the `config/settings.py` row: "SQLite transactions are `IMMEDIATE`".

## Tests

Every test is written first and shown failing. "How it fails today" is on `main` after lists (13)
and tags (14).

### Unit

`todos/tests/unit/test_database.py` (new):

| Test | What it checks | How it fails today |
|---|---|---|
| `test_sqlite_transactions_are_immediate` | `settings.DATABASES["default"]["OPTIONS"]["transaction_mode"] == "IMMEDIATE"` | `KeyError: 'OPTIONS'` |

(A real two-thread test needs a database file and `TransactionTestCase`; the test database is in
memory. The reviewer's script showed the behaviour. This test keeps the setting from being
removed.)

`todos/tests/unit/test_models.py` (add):

| Test | What it checks | How it fails today |
|---|---|---|
| `test_new_todo_goes_to_the_end_of_its_own_list` | list A has 1–2, list B has 1–5. A new to-do in A gets **3** (not 6) | `AttributeError`: no `position` |
| `test_moving_to_another_list_goes_to_the_end` | a to-do read from the database, `todo_list` set to B, `save()` → last in B | the same |
| `test_save_with_update_fields_writes_the_new_position` | a row with `position=None` (made with `bulk_create`); `save(update_fields=["done"])`; `refresh_from_db()` → it has a number | the same |
| `test_empty_position_sorts_last_in_my_order` | `bulk_create` a row with no position; `in_my_order()` puts it last | `AttributeError`: no `in_my_order` |
| `test_meta_ordering_is_still_oldest_first` | protecting: `main`'s `test_list_is_oldest_first` still passes | passes today. Show it failing against a deliberate bug: `ordering = ["position", ...]` |
| `test_number_existing_todos_per_list_by_age` | two lists, every position empty. After `number_existing_todos(django.apps.apps, None)`, each list is 1..n, oldest first | `ImportError`: no `todos.ordering` |

`todos/tests/unit/test_ordering.py` (new, database):

| Test | What it checks | How it fails today |
|---|---|---|
| `test_move_up_and_down_swap_with_the_neighbour` | A, B, C: `move(C, up)` → A, C, B; `move(A, down)` → C, A, B | `ImportError` |
| `test_move_at_the_ends_changes_nothing` | first up, last down: no number changes | the same |
| `test_move_jumps_over_a_hidden_row` | A, X, B; shown = A, B; `move(B, up)` → **B, X, A**; X keeps its number | the same |
| `test_move_renumbers_a_tie_first` | A and B both have position 1; move works and gives 1, 2, 3 | the same |
| `test_move_numbers_an_empty_position_first` | a `bulk_create` row with no position; move works | the same |

`todos/tests/unit/test_list_params.py`: add a `sort=manual` row to `test_list_params_keeps_the_sort`
(fails today: `{}`), and the fifth link to `test_sort_links` (Decision 7).

### Integration — `todos/tests/integration/test_move.py` (new)

Each test is a `LoggedInTestCase`, with to-dos in `self.todo_list`.

| Test | What it checks | How it fails today |
|---|---|---|
| `test_move_up_swaps_with_the_row_above` | A, B, C; move C up, posted to `/<C>/move/?sort=manual` → `?sort=manual` shows A, C, B; 302 to `/lists/<id>/?sort=manual#todo-<C>` exactly | 404: no `/<pk>/move/` |
| `test_move_keeps_the_list_query` | posted to `/<pk>/move/?show=active&sort=manual` → redirect keeps them, then `#todo-<pk>` | 404 |
| `test_move_on_a_filtered_page_jumps_over_a_hidden_row` | A, (done X), B; move B up from `?show=active` → full order B, X, A | 404 |
| `test_move_up_on_the_first_row_changes_nothing` | the order is the same; 302 | 404 |
| `test_move_with_a_bad_direction_is_400` | `direction=left` and no direction → 400; the order is the same | 404 |
| `test_move_is_post_only` | GET → 405 | 404 |
| `test_cannot_move_another_persons_todo` | ben's to-do → 404; ben's order is the same | 404 for the wrong reason. Show it failing against a deliberate bug: `Todo.objects` without `for_user` |
| `test_move_buttons_in_my_order` | at `?sort=manual`, `page_parts` finds the first row; its `<form class="move">` is exact (`html=True`), with ↑ `disabled` and the full `aria-label`s | no form |
| `test_no_move_buttons_in_other_sorts` | `/` (Date added, the default) and `?sort=due`: the first row's element has no `form.move` (checked inside the row, not page-wide) | passes today (protecting). Show it failing against a deliberate bug: always `can_move = True` |
| `test_editing_a_todo_into_another_list_puts_it_last` | the edit page moves it to list B → it is last in B | it keeps its old number |

Data-migration check (by hand, in the merge queue, Decision 4): a copy of a database with old
to-dos in two lists. After `migrate`, each list shows the same order in My order as before.

### CUJ — `todos/tests/cuj/test_journeys.py`: `test_put_my_todos_in_order` (new journey)

1. Sign in. Add "One", "Two", "Three". Click the sort link **My order**.
2. Click **Move Three up** (`get_by_role("button", name="Move Three up")`). The order is One,
   Three, Two.
3. **With the keyboard:** focus **Move One down** and press Enter. The order is Three, One, Two.
4. Reload. The order is still Three, One, Two.

How it fails today: there is no "Move Three up" button (timeout after 5 seconds).

Why a CUJ: it is a new journey, and it proves the keyboard path in a real browser.

## Steps, in order

1. Check the names in "Where this starts" against `main`.
2. `test_database.py` → fails → add `IMMEDIATE` → passes. Run `make test`: every old test passes.
3. Model tests → fail → `position`, `in_my_order`, `next_position`, `from_db`, `save()`;
   `makemigrations`; `makemigrations --empty todos --name number_todos` + the one line;
   `number_existing_todos` → pass.
4. `test_ordering.py` → fails → `renumber`, `move` → passes.
5. Sort tests (Decision 7) → change → fail → the `manual` row, last in `SORTS` → pass.
6. `test_move.py` → fails → `shown_todos`, `todo_move`, the URL, the template → passes.
7. CUJ → fails → passes.
8. AGENTS.md. `make check` and `make test-cuj`.

## Risks

- **A person must choose "My order" first** to see the buttons. That is the owner's choice. The
  sort link is always on the page.
- **`IMMEDIATE` is for every transaction.** A read-only `atomic()` also takes the write lock. Our
  transactions are short. If a request holds a transaction for more than 5 seconds, another one
  fails with `database is locked`. Nothing here does that.
- **Sharing (20)** must switch `todo_move` to `get_todo_or_deny(..., EDIT)`. Its matrix already
  has the row "reorder / move (16)".
- **Rows with no number** (from `bulk_create` or `loaddata`) sit at the end until the next move.
  That is the design, not a bug.
- **Busy rows.** Each row now has Done/Undo, Edit, Delete, ↑ and ↓. On a phone this is tight. The
  arrows are small on purpose.

## Not built: dragging

The owner chose buttons only. Dragging (HTML5 drag and drop, about 55 lines of JavaScript, a
`POST /lists/<list_id>/reorder/` address and a drag CUJ) was planned in the second version of this
plan and is **not built**. If it is wanted later, it needs its own plan; the buttons stay as the
keyboard and phone way.

## What happened

Built on `feature/lists` (lists, 13, not merged yet), in two commits: the tests first (red), then
the feature (green). Tags (14) is built at the same time and merges first, so the merge queue
renumbers the two migrations. These are the places where the build is different from the plan, and
why.

1. **Names from lists.** `back_to_list(request, list_id)` and `list_url(request, list_id)` take a
   list **id**, not the list. `todo_move` redirects to `list_url(request, list_id) + "#todo-<pk>"`.
   The `<li id="todo-<pk>">` was already there (details pane).
2. **The view finds the list with `get_list` too** (CONVENTIONS): first the to-do through
   `Todo.objects.for_user(request.user)`, then `get_list(request, todo.todo_list_id)`. So there are
   two gates (see the deliberate bugs below).
3. **The data function is in `todos/data_migrations.py`** (CONVENTIONS: the logic of every data
   migration lives there), not in `todos/ordering.py`. `todos/ordering.py` has `move`, `renumber`,
   `needs_renumber` and `move_limits`. The two migration files are `0013_todo_position.py` (made by
   `makemigrations`) and `0014_number_todos.py` (`makemigrations --empty todos --name number_todos`
   plus the one `RunPython` line and its import).
4. **Completed to-dos go last in My order too** (owner decision on sort). So `manual` is
   `("done", position with empty ones last, "created_at", "pk")`, and a move swaps only with the
   next shown row **with the same done state**: an open to-do never swaps with a completed one
   (that would change nothing on the screen). So the disabled buttons are: ↑ on the first open row
   and on the first completed row, ↓ on the last open row and on the last completed row
   (`move_limits`, keys `no_up_ids` / `no_down_ids` in `page_context`).
5. **No queries outside the list.** `next_position()` takes no list id: it is called on one list's
   to-dos (`self.todo_list.todos.next_position()`), and `move` starts every query from
   `todo.todo_list.todos`. So the source guard needed no new allowed line for the model or
   `ordering.py`. It needed two for `number_existing_todos` (the historical model, every row once),
   like the other data migrations.
6. **The neighbour is read inside the transaction.** The page's visible ids are read with
   `values_list("pk")` (no step counts: `shown_todos` returns the rows before
   `with_subtask_progress()`), then the list's own rows in My order are kept only if they are shown.
7. **No real browser** (owner decision). The journey `test_put_my_todos_in_order` uses the test
   client: it follows the "My order" link, presses "Move Three up" and "Move One down" (Enter on a
   focused button sends the same form), reloads, and checks that "Date added" keeps the old order.
8. **Tests added beyond the plan:** `test_move_stays_with_the_open_or_the_completed_rows`,
   `test_move_never_touches_another_list` (unit); `test_move_down_swaps_with_the_row_below`,
   `test_move_on_a_search_page_jumps_over_a_hidden_row`, `test_move_of_a_missing_todo_is_404`,
   `test_new_todo_goes_last_in_my_order`, `test_a_move_never_changes_another_persons_list`,
   `test_move_buttons_stop_where_the_completed_todos_start`, `test_move_buttons_keep_the_list_query`
   (integration); `test_saving_again_in_the_same_list_keeps_the_position`,
   `test_the_next_repeating_copy_goes_to_the_end` (unit); and
   `integration/test_reorder_migration.py`, which runs the two migrations for real on old to-dos in
   two lists. The 404 matrix has two rows for `todo_move` (`up`, `down`); the canary already opens
   every `SORTS` value, so it also opens My order. Helpers: `move_form(...)` and `row_html(...)`.
9. **One old test changed after the red run:** `test_completed_go_last_in_every_sort` checks that
   every `SORTS` value has a case, so it got a `manual` case (made by hand positions).

### Red and green

- **Red** (`reorder-before.txt`, in the builder's scratchpad): Integration 326 passed, 19 failed,
  10 errors; Unit 135 passed, 2 failed, 16 errors; CUJ 7 passed, 1 failed. The reasons: no `position` field (`AttributeError`, `KeyError`), no
  `todos.ordering` (`ModuleNotFoundError`), no `number_existing_todos` (`ImportError`), no
  `in_my_order`, `KeyError: 'transaction_mode'`, no `/<pk>/move/` (404, and `NoReverseMatch` for
  `todo_move` in the matrix), no "My order" sort link (four links, not five; `{}` for
  `sort=manual`), no `form.move` in the rows, no migration ending `_todo_position`, and the journey
  found 0 links named "My order".
- **Green:** `make test`: Integration 347 passed, Unit 153 passed. `make test-cuj`: CUJ 8 passed.
  `make check`: every commit check passed, no missing migrations, 508 tests OK.

### Deliberate bugs (each caught, then put back)

- `Meta.ordering = ["position", "created_at"]` → `test_meta_ordering_is_still_oldest_first` and
  `test_list_is_oldest_first` fail.
- `todo_move` with `get_object_or_404(Todo.objects, pk=pk)` → the source guard fails. The 404
  tests still pass, because `get_list` is a second gate. With **both** gates removed (no
  `for_user`, and `todo.todo_list` instead of `get_list`): moving **out of another person's list**
  is caught by `test_cannot_move_another_persons_todo` and the 404 matrix (`302 != 404`, both
  directions), and by the guard.
- `can_move = True` always → `test_no_move_buttons_in_other_sorts` fails for every other sort.
- **Into another person's list:** `move` reads its neighbours from every to-do
  (`type(todo)._default_manager.all()`) instead of the to-do's own list →
  `test_a_move_never_changes_another_persons_list` (ben's positions changed) and
  `test_move_never_touches_another_list` fail. (The guard does not see `type(todo)._default_manager`;
  the tests do.)

### Migration check

A scratch database at `0012_todo_list_required` with six old to-dos in three lists (two people),
added in a mixed order with set dates. After `migrate`: Home 1 H-a, 2 H-b, 3 H-c; Work 1 W-a,
2 W-b; Other 1 O-a. Each list's My order equals its "Date added" order. The scratch database was
deleted after.

### Checked by eye (headless Chrome, 1280 × 800)

`runserver` on a free port with a fresh database; a test user made in the shell, logged in through
the real log-in form; five to-dos added and three Move buttons pressed through the real forms; Pay
rent marked Done; Chrome got the pages through a small local proxy that adds the session cookie;
then the server was stopped and the database deleted.

- **My order** (`reorder-my-order-1280.png`): "Sort by: Date added  Due date  Priority  Title  **My
  order**"; the rows Water the plants, Buy milk, Call the dentist, Return the library books, then
  the completed Pay rent. Each row ends with a small ↑ above a small ↓, after Delete. Greyed
  (disabled): ↑ of Water the plants, ↓ of Return the library books, and both on Pay rent (the only
  completed one). The rows are a little taller than before (two stacked buttons); nothing wraps.
- **Date added** (`reorder-date-added-1280.png`): the order they were added, and no arrows.
