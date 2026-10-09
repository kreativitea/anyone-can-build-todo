# Plan: a details pane (feature 21)

Status: **approved, in progress.** The owner approved this plan with its three recommendations
(see "Questions for the owner"). Built on `feature/details-pane`; see "What happened" at the end.

This is the second version. An adversarial reviewer (a reviewer whose job is to find what is
wrong) checked the first version by building it and running it in a real browser. There were no
blockers. Every finding is fixed below, and the orchestrator's answers to the owner questions are
in (the owner confirms them; see "Questions for the owner").

This is feature 21, new in wave 2. The owner asked for it: "a preview pane on the right-hand side
which shows the details once an item is selected." The merge order in wave 2 is now:
6 priority → **21 details pane** → 7 notes → 4 edit → 10 search. The branch is
`feature/details-pane`.

**Where this starts.** The work starts **after 6 (priority) is merged**: `main` with wave 1
(5 due date, 12 count, 11 delete completed, 8 filter) and 6. So "how it fails today" in the tests
means: that `main`. On it:

- `todos/views.py` has `FILTERS`, `list_params(data)`, `list_query(params)`, `filter_links(params)`,
  `back_to_list(request)`, and `page_context(request, form)`: the **one** place for the list page's
  keys. It also has `MAX_ID_DIGITS = 18`, used by `todo_delete_completed` to check ids.
- The template `todos/templates/todos/todo_list.html` has its CSS in its own `<style>`. Each row is
  `<li class="done?">` with `<span class="title">{{ todo.title }}` + the priority label (6) + the
  due date `<small class="due">`, then the Done/Undo and Delete forms. Every `POST` form's `action`
  ends with `{{ list_query }}`. The title box has `autofocus`.
- `todos/tests/integration/helpers.py` has `page_without_csrf`, `list_footer` and `PageParts`
  (`post_actions`, `titles`, `current_links`).
- `Todo` has `title`, `done`, `due_date`, `priority`, `created_at`.

## What we want

A person clicks the title of a to-do. The page shows a **details pane** for that to-do: a box with
everything about it. On a wide screen the pane is on the **right** of the list. On a phone it is
**under** the list, and the browser jumps to it. A "Close" link hides it again.

Later features put more in the pane: notes (7), the Edit link (4), steps (15), tags (14) and
repeat (19).

## Decisions

### Selecting is a normal link, with `?selected=<id>` — no JavaScript

- The title of each to-do becomes a **link** to the same list page, with one more parameter in the
  address: `/?selected=5#details`. A **parameter** is a `name=value` pair after the `?` in an
  address. The part after `#` is a **fragment**: it tells the browser which part of the page to
  jump to.
- Opening a page only **reads**, so a link (a `GET` request) is right. Nothing is saved.
- **No JavaScript.** The browser loads the page again, with the pane. It works with every browser,
  the keyboard and screen readers, with no extra code.
- `selected` is one of the **list parameters**, like `show` (filter), and later `q` (search) and
  `sort`. So `list_params` checks it, and everything that keeps the list parameters keeps it too,
  with no extra code: the filter links, the add form, Done/Undo, Delete, Delete completed, and the
  redirect after each of them (`back_to_list`). Later: the search form, the sort links and the edit
  page.

### `list_params` checks `selected`: ASCII digits only

- A good value is only ASCII digits (`0`–`9`), at most `MAX_ID_DIGITS` (18) of them. Anything else
  is **dropped**: `abc`, `-1`, `1.5`, `1e3`, an empty value, a wide digit like `５`, a superscript
  like `²`, or 19 digits.
- **Why `isascii()` matters.** Python's `isdigit()` says yes to `５` **and** to `²`. `int("５")` is
  `5`, but `int("²")` **crashes** (`ValueError`), which would be a 500 error page. Checking
  `isascii()` first stops both. A test has both cases.
- Leading zeros are removed: `007` becomes `7`. So the same to-do always has the same address.
- If the address has `selected` twice, Django's `get()` takes the **last** one. So
  `?selected=5&selected=abc` is dropped. That is fine; the test for "same page" includes it.
- **One helper, `clean_id(value)`**, does this check. `todo_delete_completed` uses it too, so the
  rule for "a good id" is written once.
- **`selected` is always the last key** in `list_params`. Search (`q`) and sort (`sort`) put their
  check **before** it. Then the address is always `?show=active&q=milk&selected=5`.

### The pane takes its to-do **only from the list on the page**

This is the most important rule. (It comes from the sharing plan, feature 20.)

- The view does **not** look up the to-do by its id (no `get_object_or_404`, no
  `Todo.objects.get(pk=...)`). It looks for the id **in the list the page is already showing**:
  after the filter, and later after search, sort, and the "who may see this" check (lists, 13;
  sharing, 20).
- So an id that is not in the list on the page — it was deleted, it is hidden by the filter or the
  search, or (later) it belongs to someone else — gives **exactly the same page as no `selected`**.
  No pane, no error, never a 404 for the whole page. A person cannot learn anything about a to-do
  they cannot see. A test compares the two pages, character for character.
- To make the page **exactly** the same, `page_context` also **removes** `selected` from the list
  parameters when it found nothing. Then no link or form on the page carries a useless
  `selected=999`.
- **No extra query.** The page loads the list anyway. Looking for the id in that list costs
  nothing: the template's `{% for %}` uses the same loaded rows. (Django keeps the rows of a
  QuerySet after the first loop over it. This is called the **result cache**.) The reviewer
  counted: the same number of queries with and without `selected`. A test keeps it so.
- **The rule for every later feature: everything that changes `todos` comes before
  `selected_todo`.** That is filter, search (and its `title_match` annotation), sort, the steps
  count (15, an `annotate`), and the tags (14, a `prefetch_related`). `selected_todo` loads the
  rows. Any QuerySet method after it (`.order_by(...)`, `.prefetch_related(...)`, even `.all()`)
  makes a **new** QuerySet: the rows load a second time, and the pane's to-do is a different object
  from the one in the list (without the prefetched tags, for example).

### After Done, Undo, Delete or Add, the person comes back to the same view

- Every form keeps `selected` in its `action`, and `back_to_list` keeps it in the redirect. So:
  - **Done** on the selected to-do, on "All": the pane stays, and its status says "Completed".
  - **Done** on the selected to-do, on "Active": the to-do leaves the list, so no pane.
  - **Delete** the selected to-do: it is gone, so no pane. The address still says `selected=5`, and
    that is fine: the page treats it like any id that is not in the list.
  - **Delete completed** keeps `selected` too. If the selected to-do was completed, it is gone.
  - **Add** a new to-do: the pane still shows the old selection. (We do not select the new one.)
  - A **bad add** (for example a bad date): the error page also shows the pane.
- **A limit, on purpose.** The redirect has no `#details` (a `POST` sends the person back to the
  list address, `back_to_list` stays as it is). So after a form, the page opens **at the top**,
  with the focus in the add box (its `autofocus`). On a wide screen the pane is in view there. On a
  phone the pane is under the list, and the person scrolls to it. Adding `#details` to the
  redirects would change every redirect test for little gain; it can come later if people ask.

### Focus and the fragment

- The pane is `<aside id="details" tabindex="-1" aria-label="Details">`. An `<aside>` is a
  "complementary" region: a screen reader can list it and jump to it by its name, "Details".
- `tabindex="-1"` lets the browser **move the focus** to the pane when the address ends with
  `#details`. The reviewer checked in Chromium: **the fragment wins over the title box's
  `autofocus`**. The focus is on the pane, and the next Tab press goes to the first link in it.
  Without the fragment (after a form), `autofocus` wins and the focus is in the add box, as today.
- **The focus ring.** The pane is not a control; it gets the focus only so that Tab starts there.
  So `aside.details:focus { outline: none; }`: no ring around the whole pane. The links inside it
  keep their normal ring when Tab reaches them.

### The pane is read-only

- It shows: the **title** (as its heading, `<h2>`), the **status** (`Active` or `Completed`, the
  same words as the filter), the **due date** (`5 Oct 2026`, or `No due date`), the **priority**
  (`High`, `Medium` or `Low` — in the pane Medium is shown too, because the pane shows everything),
  and the **created** date (`2 Oct 2026`, in our time zone, Asia/Tokyo).
- It has a **Close** link: the same list address **without** `selected`, ending with `#todo-5`, so
  the browser goes back to that to-do's row (each row gets `id="todo-<pk>"`).
- **No change controls in this feature.** Done/Undo and Delete stay on the row. The **Edit** link
  comes with feature 4 (see "For later features").
- **The rule for change controls (for 4 and 20).** Every control in the pane that **changes**
  something (the Edit link, and any later Done or Delete in the pane) goes inside the one
  `<p class="details-actions">`. Today everyone may edit, so they are always drawn. When sharing
  (20) adds a `can_edit` flag, it wraps the change controls in `{% if can_edit %}`; the Close link
  stays outside the check, because closing only reads.
- Words: the labels are `Status`, `Due`, `Priority`, `Created`. Not `Due date` and not `Added`: the
  notes plan's rule says no label may contain a button's word ("Add", "Done", "Undo", "Delete",
  "Due date"), because the CUJ test finds buttons and boxes by part of their name.

### The selected row is marked

- Its title link has `aria-current="true"`. `aria-current` tells a screen reader "this is the
  current one". We use `"true"`, not `"page"`: the link does not open a different page (the filter
  uses `"page"`; sort uses `"true"` too).
- Its row gets the class `selected`: a light blue background, a blue bar on the left, and the title
  in **bold**. Not colour alone: the bold shows it too.
- **Nothing moves when a row is selected.** Every row gets the same left and right padding
  (`li { padding: 0.5rem; }`, today `0.5rem 0`). The blue bar is drawn **inside** that padding
  (`box-shadow: inset`), so the selected row's text stays exactly where it was.

### Layout

- **Wide screens** (at least `48rem`, about 768 pixels): the page becomes a **grid** of two
  columns. A **CSS grid** puts boxes in rows and columns. Left: the add form, the filter links, the
  list and the footer (at most `32rem` wide, like today). Right: the pane, `minmax(16rem, 1fr)`, so
  it is never narrower than `16rem` (about 256 pixels) and takes the rest of the width. The page may now be `56rem` wide.
- **The two columns are always there on a wide screen**, also when nothing is selected. So the list
  never moves when a person selects or closes. When nothing is selected and the list has to-dos,
  the right column shows one grey line: **"Click a to-do's title to see its details."** It is a
  plain `<p class="pane-hint">`, **not** an `<aside>`, and it is hidden on phones (`display: none`
  under `48rem`), where it would only push the page down.
- The pane is **sticky** (`position: sticky; top: 1rem`): when the person scrolls a long list,
  the pane stays in view. It is at most as tall as the window (`max-height: calc(100vh - 2rem)`)
  and scrolls inside itself (`overflow-y: auto`). Without this, a tall pane (long notes, later)
  would have its bottom, with the Close link, below the window and out of reach while sticky.
- **Phones** (narrower than `48rem`): one column, as today. The pane comes **after the list and the
  footer**. The title link's `#details` makes the browser jump to it at once. (Putting the pane
  **inside** the selected row would need the pane in the HTML twice, or a different place on wide
  screens; jumping is simpler.)
- **Where the CSS goes.** Today, in the template's own `<style>`. Edit (4) merges later and makes
  `base.html` with the shared CSS; these rules are only for the list page, so they move into the
  list page's `{% block style %}`. The `body { max-width: 56rem }` rule for wide screens moves there
  too: it overrides `base.html`'s `32rem` for the list page only. The edit page stays `32rem` wide.

### Notes (7) show only in the pane

- **Owner decision:** notes are **not** on the list rows. They are only in the pane. This keeps the
  list short and clean, on a phone too.
- So the notes plan changes (the orchestrator forwards this): no `<p class="notes">` in the row;
  one more row in the pane instead. See "For later features".

### Search (10): the "matches in notes" hint

Search matches the title **or** the notes. With notes only in the pane, a to-do that matches only
in its notes would look like a wrong result. **Decided (the owner confirms): a hint on the row.**
This is the **one** element both plans use:

```html
<small class="match-hint">matches in notes</small>
```

- It is shown only when there is a search (`q`), and the **title does not** match. (The to-do is in
  the list, so then the notes matched.)
- The database works it out in the **same** query. Search adds, **only when `q` is set**:

  ```python
  title_match = Q()
  for word in search_words(q):
      title_match |= Q(title__icontains=word)
  todos = todos.filter(title_match | notes_match).annotate(title_match=title_match)
  ```

  An **annotation** is a value the database works out for each row; here, true or false. It is the
  **same** OR of `Q(title__icontains=word)` as the search itself (both the word as typed and its
  NFKC form, from `search_words`). The reviewer checked: `annotate(title_match=Q(...))` works in
  Django 5.2.17, with one query.
- In the row, inside `<span class="title">`, right after the title link:
  `{% if q and not todo.title_match %}<small class="match-hint">matches in notes</small>{% endif %}`.
- The person clicks the title, and the pane shows the notes.
- Search builds this at its rebase; this plan fixes the element and the rule.

## What we will not do (yet)

- **No JavaScript**, and no "load the pane without reloading the page".
- **No change controls in the pane** in this feature. Edit (4) adds its link.
- **No `#details` after a form** (see "A limit, on purpose").
- **No new address** like `/5/`. The pane is on the list page.
- **No keyboard shortcuts** (for example arrow keys to select the next to-do).
- **No selecting several to-dos.**
- **No "remember the selection"** in a cookie or the session. It lives only in the address, so a
  person can bookmark it or send it.

## Changes in behaviour

1. Each to-do's title is a link: `/?…&selected=<id>#details`.
2. With a good `selected` that is in the list on the page, the page shows the details pane, and the
   row is marked (`aria-current="true"`, class `selected`).
3. With any other `selected` (bad, missing, deleted, filtered out), the page is **exactly** the
   page without it.
4. `selected` is kept by the filter links, every `POST` form, and every redirect back to the list.
5. On wide screens the page is up to `56rem` wide, in two columns; with nothing selected, the right
   column has the grey hint. On phones the layout is the same as today.
6. Each row has `id="todo-<pk>"`, and every row has `0.5rem` padding on the left and right.

What stays the same: add, Done/Undo, Delete, Delete completed, the filter, the count. No model
change, **no migration**. The CUJ journey still works, with one more step.

## The changes, one file at a time

### 1. `todos/views.py` — the views

**`MAX_ID_DIGITS` moves up**, next to `MAX_DELETE_AT_ONCE`, and gets one helper:

```python
# A real id is a plain number. 18 digits always fit in SQLite's 64-bit integer;
# longer values may overflow.
MAX_ID_DIGITS = 18


def clean_id(value):
    """The id as plain digits without leading zeros, like "5"; or None if it is not an id.

    isascii() comes first: isdigit() also says yes to "５" and "²", and int("²") crashes.
    """
    if value and value.isascii() and value.isdigit() and len(value) <= MAX_ID_DIGITS:
        return str(int(value))
    return None
```

**`list_params`**: one more check, **at the end** (later checks go before it):

```python
    selected = clean_id(data.get("selected"))
    if selected is not None:
        params["selected"] = selected
    return params
```

**Three small helpers**, next to `filter_links`:

```python
def without_selected(params):
    """The list parameters without the selection."""
    return {k: v for k, v in params.items() if k != "selected"}


def select_base(params):
    """The start of every title link: "/?show=active&selected=". The template adds the id."""
    others = without_selected(params)
    return reverse("todo_list") + (list_query(others) + "&" if others else "?") + "selected="


def selected_todo(todos, params):
    """The selected to-do, taken ONLY from the to-dos on the page; else None.

    Never look it up by id: a to-do that is not on the page (deleted, filtered
    out, or later: not yours) must give the same page as no selection.
    Everything that changes `todos` must come BEFORE this call.
    """
    wanted = params.get("selected")
    if wanted is None:
        return None
    return next((todo for todo in todos if str(todo.pk) == wanted), None)
```

**`page_context`**: the selection is the **last** step on the list. These lines go after
`todos = filter_todos(todos, params)` (search, sort, the steps count and the tags go **between**
the two, later):

```python
    selected = selected_todo(todos, params)
    if selected is None:
        params.pop("selected", None)  # then the page is exactly the page without it
```

And three new keys, one per line:

```python
        "selected": selected,
        "select_base": select_base(params),
        "close_url": reverse("todo_list") + list_query(without_selected(params)),
```

The template adds `#todo-<pk>` to `close_url`.

**`todo_delete_completed`**: use `clean_id`:

```python
    ids = [pk for value in request.POST.getlist("ids") if (pk := clean_id(value))]
```

(`:=` gives a name to a value inside an expression. `"0"` is a non-empty text, so it is kept, like
today; it matches nothing.) Its existing tests protect this.

`filter_links`, `back_to_list`, `todo_add`, `todo_toggle`, `todo_delete`: **no change**. They keep
`selected` because `list_params` keeps it.

### 2. `todos/templates/todos/todo_list.html` — the page

**The frame.** After `<h1>`, wrap the rest in a grid with two parts:

```html
<div class="layout">
  <div class="main">
    … the add form, the filter nav, the <ul>, the list footer: no change inside …
  </div>
  {% if selected %}
  <aside class="details" id="details" tabindex="-1" aria-label="Details">
    <h2>{{ selected.title }}</h2>
    <dl>
      <dt>Status</dt><dd>{% if selected.done %}Completed{% else %}Active{% endif %}</dd>
      <dt>Due</dt><dd>{% if selected.due_date %}{{ selected.due_date|date:"j M Y" }}{% else %}No due date{% endif %}</dd>
      <dt>Priority</dt><dd>{{ selected.get_priority_display }}</dd>
      <dt>Created</dt><dd>{{ selected.created_at|date:"j M Y" }}</dd>
    </dl>
    <p class="details-actions"><a href="{{ close_url }}#todo-{{ selected.pk }}">Close</a></p>
  </aside>
  {% elif has_todos %}
  <p class="pane-hint">Click a to-do's title to see its details.</p>
  {% endif %}
</div>
```

- `created_at` is a date **and time**, saved in UTC. Django shows it in our time zone (Asia/Tokyo)
  by itself, so a to-do made at 15:30 UTC on 1 October shows `2 Oct 2026`. A test checks it.
- The title is escaped by Django, like everywhere. Never add `|safe`.

**Each row.** Three small changes:

```html
<li id="todo-{{ todo.pk }}" class="{% if todo.done %}done{% endif %}{% if todo == selected %} selected{% endif %}">
  <span class="title"><a href="{{ select_base }}{{ todo.pk }}#details"{% if todo == selected %} aria-current="true"{% endif %}>{{ todo.title }}</a>{…priority label, due date: no change…}</span>
```

- `todo == selected`: Django compares two to-dos by their id. No query.
- Keep the `<a …>…</a>` on one line, so the tests can match it exactly.

**The CSS** (in the `<style>` today; into `{% block style %}` when 4 brings `base.html`). Change
the existing `li { … padding: 0.5rem 0; … }` to `padding: 0.5rem;`, and add:

```css
.title a { color: inherit; }
li.selected { background: #eef4ff; box-shadow: inset 4px 0 0 #1a56db; }
li.selected .title a { font-weight: bold; }
aside.details { margin-top: 1.5rem; padding: 1rem; border: 1px solid #ccc; border-radius: 0.5rem; overflow-wrap: anywhere; }
aside.details:focus { outline: none; }
aside.details h2 { margin-top: 0; font-size: 1.2rem; }
aside.details dl { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 1rem; }
aside.details dt { color: #555; }
aside.details dd { margin: 0; }
.pane-hint { display: none; color: #666; }
@media (min-width: 48rem) {
  body { max-width: 56rem; }
  .layout { display: grid; grid-template-columns: minmax(0, 32rem) minmax(16rem, 1fr); gap: 2rem; align-items: start; }
  aside.details { margin-top: 0; position: sticky; top: 1rem; max-height: calc(100vh - 2rem); overflow-y: auto; }
  .pane-hint { display: block; margin: 0; }
}
```

- `color: inherit`: the title link keeps the row's colour (grey and crossed out when done).
- `box-shadow: inset 4px 0 0 …`: the blue bar, drawn inside the row's padding, so nothing moves.
- **Contrast** (how different the text colour is from its background; normal text needs at least
  4.5 to 1): black text on `#eef4ff` is about 18 to 1; a done title (`#666`) on `#eef4ff` is about
  5.2 to 1; `#555` labels and `#666` hint on white are about 7.5 and 5.7 to 1. The blue bar is
  only decoration: the bold title carries the meaning too.
- `minmax(0, 32rem)`: a very long word cannot make the list column wider than its place.

### 3. `todos/tests/integration/helpers.py` — the shared helpers

**This feature owns the rule for checking titles.** The title is now a link with a long address, so
writing `<span class="title">Buy milk</span>` in a test is wrong from now on. Every later test
(search (10) at its rebase **must** follow this; so must 7, 4, 9, 14, 15, 19):

- **Which titles are on the page, in order:** `page_parts(response).titles`.
- **One exact title element:** `title_element(todo, query="", selected=False)`.

`PageParts` learns four things:

- **`titles`** also reads the text of an `<a>` that is **directly** inside `<span class="title">`.
  The priority label, the due date (and later the match hint) are still **not** part of the title.
- **`selected_titles`**: the text of every title link with `aria-current="true"`. A test that
  compares it to one name proves that no other row is marked. (Sort links also use
  `aria-current="true"`, but they are not in a title span, so they are not counted.)
- **`panes`**: the `aria-label` of every `<aside>` on the page, in order. `[]` means "no pane".
- **`row(title)`**: the row whose title is exactly this text, with `id` (the `<li>`'s `id`) and
  `classes` (the `<li>`'s classes, as a list). Notes (7) **adds** its own fields to this.

And two builders, like `list_footer`. Each returns the exact HTML the page must show, with the
title escaped by `django.utils.html.escape`:

```python
def title_element(todo, query="", selected=False):
    """The whole <span class="title"> of one row: the link, the priority label, the due date.

    `query` is the list query without the selection, like "?show=active".
    """


def pane_element(title, *, status="Active", due="No due date", priority="Medium",
                 created, close_url):
    """The whole details <aside>, exactly as the page must show it."""
```

Later features add one keyword each: `title_element(..., match_hint=False)` (search), and
`pane_element(..., notes=None, edit_url=None, steps=None, tags=(), repeat=None)`. So their tests
compare the **whole** element too.

### 4. `todos/urls.py`, `todos/models.py`, `todos/forms.py`, `todos/admin.py` — no change

### 5. `AGENTS.md`

- `todos/views.py` row: "`?selected=<id>` shows the details pane. `list_params` checks it (ASCII
  digits only, always the last key). The pane's to-do is taken **only** from the to-dos already on
  the page, never looked up by id. Everything that changes the list comes before `selected_todo`."
- Template row: "The one page: the add form, the list, and the details pane (on the right on wide
  screens, under the list on phones)."
- Rules: "A change control in the details pane goes in `<p class="details-actions">`." and "Check
  titles with `page_parts(...).titles` or `title_element(...)`, never a hand-written
  `<span class="title">`."

## For later features (the orchestrator forwards these)

- **Notes (7), merges right after this.** No notes on the rows. In the pane, after `Created`:
  `{% if selected.notes %}<dt>Notes</dt><dd class="notes">{{ selected.notes|linebreaksbr }}</dd>{% endif %}`.
  Its "shown with line breaks" and "escaped" tests compare `pane_element(…, notes=…)`. Its "no notes"
  test checks the whole pane without a Notes row. Its `row().notes_text` becomes
  `PageParts.pane_notes`.
- **Edit (4).** **Decided:** keep the row link `Edit <title>` (as built), **and** add one line in
  the pane, in `details-actions`, before Close:
  `<a href="{% url 'todo_edit' selected.pk %}{{ list_query }}">Edit</a> `.
  `list_query` has `selected`, so after Save or Cancel the person is back with the same pane open,
  showing the new values. **One test** in edit's `test_edit.py`: `test_pane_has_an_edit_link` —
  `GET /?show=active&selected=5` shows exactly `pane_element(…, edit_url="/5/edit/?show=active&selected=5", close_url="/?show=active")`.
  Edit also moves this feature's CSS into the list page's `{% block style %}`. The CUJ's title
  click must use `exact=True` (see Tests), because the row's Edit link is named "Edit Buy milk".
- **Search (10).** Its `q` check goes **before** `selected` in `list_params`, and `search_todos`
  runs **before** `selected_todo`. The search form's hidden inputs keep `selected` by themselves.
  Searching for something that hides the selected to-do closes the pane. The match hint: see
  Decisions. **Required at the rebase:** every title check in `test_search.py` uses
  `page_parts(...).titles` or `title_element(...)` (with `match_hint=True` where it applies); no
  hand-written `<span class="title">Shopping</span>`.
- **Sort (9).** The `sort` check goes before `selected`; sorting runs before `selected_todo`.
- **Steps (15).** Steps live on `/<id>/subtasks/`. **Recommendation:** the pane shows
  `<dt>Steps</dt><dd>2 of 5 done · <a href="/5/subtasks/">Steps</a></dd>`, using the counts the list
  already computes with `annotate(…, distinct=True)` (before `selected_todo`). No step list in the
  pane at first; showing the steps themselves later costs one more query, only for the selected
  to-do.
- **Tags (14).** A `Tags` row with each tag as a link to `?tag=<name>` (keeping `selected`). Its
  `prefetch_related` comes before `selected_todo`.
- **Repeat (19).** A `Repeats` row, for example `Every week`.
- **Lists (13) and sharing (20).** The pane is safe by design: it only shows a to-do from the list
  the page already shows (after `.visible_to(user)`). Sharing wraps the change controls in
  `{% if can_edit %}`. Keep the test "an id not in the list gives the same page".

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code. Every check on the page
is an exact element (`assertContains(..., html=True)`), a part read by `PageParts`, or the **whole
page** compared to another whole page. No loose pieces of text, and no page-wide "not on the page"
checks.

In the tables, `Buy milk` is a to-do with due date 5 Oct 2026, priority High, made at 15:30 UTC on
1 Oct 2026 (set with `Todo.objects.filter(pk=…).update(created_at=…)`, because `auto_now_add`
ignores a value given at create). `Call home` is a completed, Medium to-do with no date. Ids are
written `5` and `6`; the tests use the real `pk`.

"The whole page equals" means `page_without_csrf(a) == page_without_csrf(b)`. (The CSRF token is
different on every page, so the helper takes it out first.)

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

Selecting a to-do is a new **step** in the same journey ("plan and finish a to-do"), not a new
journey. So we add one step to `test_plan_and_finish_a_todo`, right after the check for
`due 5 Oct 2026`, and two checks later:

```python
item.get_by_role("link", name="Buy milk", exact=True).click()
details = page.get_by_role("complementary", name="Details")
expect(details.get_by_role("heading", name="Buy milk")).to_be_visible()
expect(details).to_contain_text("5 Oct 2026")
```

- `exact=True`: Playwright matches **part** of a name by default. After edit (4), the row also has
  a link named "Edit Buy milk", and without `exact=True` the click finds two links and fails. (The
  reviewer saw this happen.)
- After the Done click: `expect(details).to_contain_text("Completed")` — the pane stayed open
  after a `POST` and a redirect.
- After the Delete click: `expect(details).to_have_count(0)` — the pane is gone.

How it fails today: the title is not a link, so Playwright waits 5 seconds for a link "Buy milk"
and fails with a timeout.

### Bottom: unit tests (`todos/tests/unit/test_list_params.py`, made by 8)

| Test | What it checks | How it fails today |
|---|---|---|
| `test_list_params_keeps_a_good_selected` | `selected=5` → `{"selected": "5"}`; `selected=007` → `{"selected": "7"}`; 18 nines → kept | `{}`: `selected` is dropped today |
| `test_list_params_drops_a_bad_selected` | `selected=` / `abc` / `-1` / `1.5` / `1e3` / `%EF%BC%95` (wide `５`) / `%C2%B2` (`²`) / `5%C2%B2` (`5²`) / 19 nines / `5%26next%3Dx` (a hidden `&next=x`) → `{}` | **passes today** (protecting). Deliberate bug: in `clean_id`, leave out `value.isascii()` → the `５` case gives `{"selected": "5"}`, and the `²` cases crash with `ValueError` |
| `test_selected_is_the_last_key` | `selected=5&show=active` → `{"show": "active", "selected": "5"}`, and `list(result)` is `["show", "selected"]` | `{"show": "active"}` |
| `test_filter_links_keep_selected` | `filter_links({"show": "active", "selected": "5"})` → the URLs `/?selected=5`, `/?show=active&selected=5`, `/?show=completed&selected=5` | the URLs have no `selected` |
| `test_select_base` | `views.select_base({})` is `/?selected=`; `views.select_base({"show": "active", "selected": "5"})` is `/?show=active&selected=` | `AttributeError`: there is no `select_base` (the test imports the module, `from todos import views`, so only this test fails) |

The existing `test_list_params_twice_is_the_same` (if search adds it) is **not** changed by this
feature: no `selected` rows in it.

### Middle: integration tests (`todos/tests/integration/test_details.py`, new file)

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_titles_are_links_that_keep_the_filter` | subTests: `GET /` and `GET /?show=active` | `title_element(milk)` and `title_element(milk, "?show=active")`, each exactly once; `parts.titles` is still right | `assertContains` fails: the title is plain text |
| `test_selected_shows_the_pane_and_marks_the_row` | `GET /?selected=5` | `parts.panes == ["Details"]`; the whole pane is `pane_element("Buy milk", due="5 Oct 2026", priority="High", created="2 Oct 2026", close_url="/")` (2 Oct, because 15:30 UTC is 00:30 in Tokyo; `close_url` gets `#todo-5` inside the builder); `parts.selected_titles == ["Buy milk"]`; `parts.row("Buy milk").classes` has `selected` and its `id` is `todo-5`; `parts.row("Call home").classes` has not | `panes` is `[]` |
| `test_pane_shows_completed_medium_and_no_due_date` | `GET /?selected=6` | `pane_element("Call home", status="Completed", created=…, close_url="/")` | no pane |
| `test_title_is_escaped_in_the_pane` | a to-do titled `<b>x</b>`, selected | the whole pane, built with `escape` (its heading is `<h2>&lt;b&gt;x&lt;/b&gt;</h2>`) | no pane |
| `test_every_post_form_keeps_selected` | `GET /?show=active&selected=5` (with `Call home` completed, so the footer form is there) | `parts.post_actions` are exactly add, toggle, delete and delete-completed, each ending `?show=active&selected=5` | they end `?show=active` |
| `test_redirects_keep_selected` | subTests: post to add, toggle, delete (of `Call home`), and delete-completed, each with `?selected=5` | `response["Location"] == "/?selected=5"` | `Location` is `/` |
| `test_deleting_the_selected_todo_closes_the_pane` | post delete of 5, `?selected=5`, `follow=True` | redirect chain `[("/?selected=5", 302)]`; the whole page equals the page for `/` | the redirect is to `/` |
| `test_add_error_keeps_the_pane` | post `/add/?selected=5` with a bad date | status 200; `parts.panes == ["Details"]`; the whole pane | no pane |
| `test_hint_when_nothing_is_selected` | `GET /` with to-dos | exactly `<p class="pane-hint">Click a to-do's title to see its details.</p>`, once; `parts.panes == []` | the hint is not there |

**The sharing rule: an id not in the list is the same page as no `selected`.**

| Test | Cases (subTests) | What it checks |
|---|---|---|
| `test_selected_not_in_the_list_is_the_same_page_as_none` | `?show=active&selected=6` (completed, filtered out) vs `?show=active`; `?selected=999` (no such to-do) vs `/`; `?selected=abc`, `?selected=0`, `?selected=`, `?selected=5&selected=abc` vs `/` | the whole pages are **equal**, character for character |

- **How it fails today:** it **passes** today, because `selected` is ignored. It protects the rule
  against the two easy mistakes. **Deliberate bugs** (make each one for a moment, see the test
  fail, put the code back, check `git diff`):
  1. In `selected_todo`, use `Todo.objects.filter(pk=wanted).first()` (a lookup by id) → the
     filtered-out completed to-do gets a pane: the pages differ.
  2. In `page_context`, remove `params.pop("selected", None)` → every form on the page carries
     `selected=999`: the pages differ.

**Tests that protect what already works.** These pass today and must still pass:

| Test | What it checks | Deliberate bug that makes it fail |
|---|---|---|
| `test_selecting_costs_no_extra_query` | the number of queries for `/?selected=5` equals the number for `/` (`CaptureQueriesContext`) | in `selected_todo`, loop over `todos.all()` instead of `todos` (a new QuerySet: the rows load twice) |
| every existing test in `test_views.py` and `test_filter.py` | still passes; `titles` now reads the link text | in `PageParts`, forget the `<a>` case → every `titles` check fails |
| `test_bad_ids_are_ignored` (delete completed, exists) | still passes with `clean_id` | in `clean_id`, drop the length check → the 19-digit case fails |

## Steps, in order

1. **After 6 (priority) is merged**, make the branch in its own worktree from the newest `main`:
   `git fetch origin` then
   `git worktree add -b feature/details-pane .claude/worktrees/details-pane origin/main`.
   Check that `Todo.Priority` and `page_context` are there.
2. Change `helpers.py`: `titles` reads a link inside the title; add `selected_titles`, `panes`,
   `row()`, `title_element()`, `pane_element()`. Run `make test`: every old test still passes.
3. Write the unit tests, `test_details.py` and the CUJ step. Run `make test` and `make test-cuj`.
   See each new test fail as the tables say; the protecting tests pass.
4. Change `views.py` (`clean_id`, `list_params`, the helpers, `page_context`,
   `todo_delete_completed`), then the template and its CSS.
5. Run `make test`, then `make test-cuj`: every test passes.
6. Make each deliberate bug, one at a time. See the test fail. Put it back. Check `git diff`.
7. By hand, `make run`:
   - Wide window: the grey hint is on the right. Click a title: the pane is there, the row is
     marked, and the row's text does not move. Scroll a long list: the pane stays in view. Close:
     back at the row, and the list does not move.
   - Phone width (375 pixels): no hint. Click a title: the browser jumps to the pane under the
     list. Close: back at the row.
   - Keyboard only: Tab to a title, Enter. No ring around the pane; the next Tab is on Close.
   - A screen reader (VoiceOver: Control-Option-U, "Landmarks"): "Details" is listed.
   - Done, Undo, Delete, Delete completed, Add, the filter links: the pane behaves as in
     Decisions.
   - Type `?selected=abc`, `?selected=²`, `?selected=999`: the normal page, no error.
8. Update `AGENTS.md`.
9. Run `make check`. Commit.

## Risks

- **On a wide screen, a long list scrolls away from the row.** The reviewer measured it: clicking
  the 40th to-do of a long list jumps to `#details`, and the page scrolls so the pane is at the top
  of the window. The pane is fine, but the row the person clicked is now far below, off the screen
  (about 1,500 pixels down). Close (`#todo-<pk>`) brings it back. Without JavaScript we cannot
  jump only on phones; we accept this.
- **After a form, a phone opens at the top.** See "A limit, on purpose".
- **The page is wider on a computer** (`56rem`, also with nothing selected), so the list sits left
  of where it is today. This is the price of a list that never moves.
- **Clash with notes (7)** and **edit (4)**: their plans must take the changes in "For later
  features" first; otherwise notes go in two places, or the CUJ click finds two links.
- **The result cache.** A later step placed after `selected_todo` loads the rows twice and gives
  the pane a different object. The rule "everything that changes `todos` comes before
  `selected_todo`" and the query test guard it.
- **`aria-current="true"` is also used by sort (9)** for the chosen sort link. They are on different
  elements, and `selected_titles` only reads title links.

## Questions for the owner

The orchestrator answered these; the owner confirms:

1. **Layout on wide screens:** two columns **always**, with the grey hint "Click a to-do's title to
   see its details." when nothing is selected (not on phones). Recommended: yes.
2. **Edit:** keep the row link "Edit <title>" **and** add "Edit" in the pane. Recommended: yes.
3. **Search hint:** `<small class="match-hint">matches in notes</small>` on a row whose title does
   not match the search. Recommended: yes.

## What happened

The builder followed the plan. These are the places where it did something different, and why.

1. **The starting point.** (Fixed by the rebase, item 10.) Priority (6) was **not** on `main` yet when the branch started (the
   newest commit was "Ruff: leave Markdown files alone (#6)"). So this branch has **no Priority
   row** in the pane. The template has a comment where it goes. `pane_element(...)` has
   `priority=None`, which means "no Priority row". See "After the rebase" below.
2. **The CUJ step is in a new file.** The owner decided: no real-browser tests. `main` still had the
   Playwright journey (a small PR removes it). So the journey step is in a **new** test-client
   journey, `todos/tests/cuj/test_details_journey.py`, and the Playwright file is not touched. It
   adds Buy milk with a due date, "clicks" the title (it reads the link's address from the page and
   sends a `GET`), checks the whole pane, posts Done (the pane says Completed after the redirect),
   then Delete (no pane). Before the code it failed with "the title Buy milk is not a link".
3. **`pane_element` takes the to-do, not only its title.** The Close link ends with
   `#todo-<pk>`, so the builder needs the id: `pane_element(todo, *, status, due, priority, created,
   close_url)`. The heading is `escape(todo.title)`.
4. **`PageParts` also has `rows`**, the list behind `row(title)`. Each row is a small `Row` with
   `id`, `classes` and `title`.
5. **Edit (4).** The pane has a Django comment in `details-actions`, before Close, where the Edit
   link goes. A comment draws nothing, so the page is the same.
6. **The test data.** `Call home` gets `created_at` 3 Oct 2026 (01:00 UTC), and the escape test's
   to-do 4 Oct 2026, so every pane in the tests has a fixed Created date.
7. **Deliberate bugs.** Each one was made for a moment, seen failing, and put back (`views.py` was
   copied back and compared with `cmp`):
   - Lookup by id (`Todo.objects.filter(pk=wanted).first()`): the same-page test fails for
     `?show=active&selected=<completed>`.
   - No `params.pop("selected", None)`: the same-page test fails for the filtered-out id, `999` and
     `0` (the forms carry `selected=...`).
   - `todos.all()` in `selected_todo`: the query test fails, 5 queries instead of 4.
   - `clean_id` without `isascii()`: the wide 5 gives `{"selected": "5"}`, and `²` and `5²` crash with
     `ValueError`.
   - `clean_id` without the length check: `test_bad_ids_are_ignored` crashes with `OverflowError`,
     and the 19-digit `selected` is kept.
   - `PageParts` without the `<a>` case: six title checks in `test_filter.py` fail.
8. **Checked by eye** (Playwright was still installed, and was used only to take pictures, not as a
   test):
   - 1280 pixels, nothing selected: two columns; the grey hint "Click a to-do's title to see its
     details." is on the right; the focus is in the add box.
   - 1280 pixels, Buy milk selected: the pane is on the right, with a grey border and round corners:
     the title, Status, Due, Created and Close. The row has a light blue background, a blue bar on the
     left and a bold title. The focus is on the pane with no ring, and the next Tab goes to Close.
     The title's left edge is at the same place with and without the selection (200 pixels).
   - 375 pixels, nothing selected: one column, as before, and no hint.
   - 375 pixels, Buy milk selected: the pane is under the list and the footer; the browser jumped to
     it (the page is short, so it scrolls only a little). The row is marked the same way. The title
     does not move (24 pixels both times).
   - **Owner decision, after the first build:** the title links are **not** underlined normally.
     They are underlined only on hover and on keyboard focus (`.title a:hover, .title
     a:focus-visible`), and they keep `color: inherit` and the browser's focus outline. Checked by
     eye at 1280 pixels: no title is underlined; the hovered title (Book the dentist) is; a title
     reached with Tab is underlined and has the normal blue focus ring; the done title (Call home)
     is still crossed out and grey.

9. **The code review** (no blockers) asked for four more checks. Each new check was seen failing
   against its bug, and the bug was put back:
   - `test_close_keeps_the_filter`: `/?show=active&selected=<milk>` has Close to `/?show=active`.
     Bug: `close_url` without the list query.
   - `test_selected_shows_the_pane_and_marks_the_row` also checks that the hint is **not** there.
     Bug: the hint in its own `{% if has_todos %}`, so it is drawn next to the pane.
   - `test_title_is_escaped_in_the_pane` also checks the row's whole title link, escaped. Bug:
     `{{ todo.title|safe }}` in the row.
   - **A change:** the hint now needs `{% elif todos %}` (the list **on the page**), not
     `has_todos` (the whole table). On an empty filter there is no title to click, so no hint.
     `test_no_hint_when_the_shown_list_is_empty` failed before the change for the empty filter
     (the hint was there); the empty table already had no hint. `todos` is already loaded by the
     list loop above it, so there is no extra query (the query test still passes).

10. **The rebase on `main` with priority (6) and the test-client journeys.**
    - Clashes, combined by hand: `helpers.py` keeps main's `page_forms`/`PageForms`, and
      `PageParts` takes `post_actions` from `PageForms` (as on main) plus this feature's `titles`
      (with the link), `selected_titles`, `panes` and `row()`. The template keeps priority's
      select box, its CSS, and its label inside the title span, after the title link. `AGENTS.md`
      keeps both features' words in each row.
    - Main's own tests wrote the title span by hand (`test_priority.py`'s `title_with_label`, and
      `todo_row` in `cuj/test_journeys.py`). They now use `title_element(todo)` (the rule from this
      plan), and `todo_row` has the row's `id="todo-<pk>"`. The "space before the label" check is
      now `Call home</a> <span class="priority high">…`.
    - **The Priority row** is in the pane, after Due, and shows Medium too. `pane_element` has
      `priority="Medium"` by default; `Buy milk` is High in `test_details.py`, and `Call home`'s
      pane shows Medium (`test_pane_shows_completed_medium_and_no_due_date`). `title_element` adds
      the High/Low label from the to-do's own priority.
    - Before the Priority row: 5 pane tests and the details journey failed, because the pane had no
      `<dt>Priority</dt>`. Deliberate bugs, each seen failing and put back: no Priority row; the
      number (`selected.priority`) instead of the word; Medium hidden in the pane (like on the
      row: only the Call home test fails, so that test is the one that guards it); no label in the
      row's title (`title_element` checks in `test_details.py`, `test_priority.py` and the High
      journey fail).
    - Checked by eye at 1280 pixels with headless **Google Chrome** (`--screenshot`; Playwright is
      gone): Buy milk selected; the row has its red "High priority" label and is marked; the pane
      shows Status Active, Due 5 Oct 2026, Priority High, Created.
11. **Owner decision: phones get a light grey underline.** On a device without hover there is no
    way to see that a title is a link, so `@media (hover: none)` gives the title links a light grey
    (`#bbb`) underline, 2 pixels below the text. With hover, it stays hover-only. Checked by eye
    with headless Google Chrome told to act like a phone
    (`--blink-settings=primaryHoverType=1,availableHoverTypes=1,…`): every title has the grey
    underline, the selected one is bold, and the done title (Call home) is still crossed out. The
    same page without that setting has no underline. (Headless Chrome draws the page at least about
    500 pixels wide, so the "375" picture was a cut of a 500-pixel page; the 500-pixel picture shows
    the one-column phone layout in full.)

### Still to do after edit (4)

- Add the pane's Edit link in `details-actions`, before Close, and edit's
  `test_pane_has_an_edit_link` (see "For later features"). Move this feature's CSS into the list
  page's `{% block style %}`.

## PLAN CARD

- **Summary:** clicking a title selects the to-do with a GET link (`?selected=<id>#details`). The
  read-only pane (`<aside aria-label="Details">`) shows title, Status, Due, Priority, Created and
  Close. No JavaScript, no migration. Starts after 6 merges.
- **Key rule:** the pane's to-do comes only from the list already on the page. An id not in it
  gives the exact page without `selected`. No extra query, and everything that changes `todos`
  comes before `selected_todo`.
- **Decisions:** `clean_id` (ASCII digits ≤18, so `５`/`²` are dropped; reused by delete completed).
  `selected` is always the last list parameter. Change controls go in `details-actions` (sharing
  wraps them in `can_edit`). The fragment's focus wins over `autofocus`, with no focus ring on the
  pane. After a POST there is no `#details`.
- **Layout:** wide screens get a grid `minmax(0,32rem) | minmax(16rem,1fr)`. The pane is sticky,
  with `max-height` and its own scroll. With nothing selected, a grey hint fills the right column.
  Phones put the pane under the list. Every row has the same padding, so selecting moves nothing.
- **Files:** `views.py`, `todo_list.html` (+CSS), `tests/integration/helpers.py` (owns the title
  rule: `parts.titles`, `title_element()`, `pane_element()`, `panes`, `row()`), `AGENTS.md`.
- **Tests:** one new CUJ step (with `exact=True`). Unit tests for `list_params`, `filter_links` and
  `select_base`. Integration: 9 new tests that fail first, the sharing same-page test (passes
  today, two deliberate bugs), and a query-count guard.
- **Forwarded:** notes only in the pane. Edit adds the pane's "Edit" (one line, one test) and
  keeps its row link. Search adds the `match-hint` annotation and must use `title_element`.
  Steps/tags/repeat add one pane row each.
- **Risks:** on wide screens a long list scrolls the clicked row away (Close brings it back). A
  phone opens at the top after a POST. The page is wider.
- **Owner confirms:** Q1 two columns + hint, Q2 Edit in row and pane, Q3 the "matches in notes"
  hint.
