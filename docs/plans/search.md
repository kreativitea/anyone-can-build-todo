# Plan: search the list

Status: **approved.** No code has changed yet.

This is feature 10, the last one in wave 2 of [the rollout plan](feature-rollout.md). The merge
order in wave 2 is: 6 priority → 21 details pane → 7 notes → 4 edit → **10 search** (search is
last). An adversarial review (a reviewer whose job is to find what is wrong) checked the first
version, and ran its SQLite and Unicode claims. Every finding is fixed below. The third version adds
the owner's decision on wide letters, and the details pane (21).

**Where this starts.** The work starts on `main` **after wave 1 is merged**: 5 due date, 12 count,
11 delete completed and 8 filter. So "how it fails today" in the tests means: `main` with those
four features in it. On that `main`, `todos/views.py` has these helpers (see [the filter
plan](filter.md) and CONVENTIONS.md):

- `list_params(data)` reads the address. It returns a dictionary with **only checked values that
  are not the default**: `{}`, `{"show": "active"}` or `{"show": "completed"}`.
- `list_query(params)` turns that dictionary into text for an address: `"?show=active"`, or `""`.
- `FILTERS` is one table: for each filter, its value, its word, its empty message and its query.
- `filter_todos(todos, params)` is one step of the list query.
- `filter_links(params)` builds the All, Active and Completed links. Each link keeps the other
  parameters.
- `back_to_list(request)` sends the browser back to `/` plus the list query.
- `page_context(request, form)` makes the dictionary for the page. It has `list_query`, and
  `has_todos`, the count and `completed_ids`, which all use the **whole** table.
- Every `POST` form on the page ends its `action` with `{{ list_query }}`.
- Shared test helpers (`PageParts`, `page_parts`) are in `todos/tests/integration/helpers.py`.

Features 6, 21, 7 and 4 are built at the same time as this one, and merge **before** it. The
section "After 6, 21, 7 and 4 are on `main`" says what this feature must then do.

## What we want

Above the list, a **search box** and a **Search** button. A person types a word, for example
`milk`, and presses Search (or Enter). The list then shows only the to-dos that have that word in
their title (and, after the rebase, in their notes).

- The word stays in the box, so the person can see what they searched for.
- A **Clear search** link shows the list again without the search.
- If nothing matches, the page says so, with the word: `No to-dos match "milk".`
- Wide letters find normal ones: `ｍｉｌｋ` finds `Buy milk` (owner decision).
- Search works **together with the filter**. Active + `milk` shows the active to-dos with `milk`.
- When the person presses Add, Done, Undo, Delete, Delete completed or Edit, they **stay on the
  same search**.
- The page needs no JavaScript.

## Decisions

### The search is in the address, like the filter

- Searching only reads. So the search box is in a **`GET` form**: a form that puts what you typed
  into the address, for example `/?q=milk`. It changes nothing in the database.
- The **query parameter** (the part of an address after `?`) is called `q`. This is the usual
  name, and it is short.
- With the filter, the address is `/?show=active&q=milk`. `show` always comes first.
- A person can copy the address, or press Back, and get the same search again.
- **An empty search** sends `/?q=` (or `/?show=active&q=`). The browser always sends every field,
  also an empty one. We do not hide that. But the **page is the same as `/`** (or `/?show=active`):
  `list_params` drops the empty `q`, so the links, the forms and the redirects do not have it.

### `list_params` cleans `q`

`list_params` gets one more check. A new helper, `clean_search(text)`, does it in this order:

1. **Remove invisible characters.** These are removed completely:
   - **control characters** (Unicode category `Cc`) that are not white space, for example the
     "null" character `\0` or the bell `\a`;
   - **format characters** (category `Cf`), for example the zero-width space (U+200B) or the soft
     hyphen (U+00AD). You cannot see them, but a copied word often has one, and then it would never
     match.

   Why `\0` matters: SQLite stops reading the search at a `\0`. So `milk\0zzz` is searched as
   "ends with `milk`": it finds `Buy milk` but not `milkshake`. And `\0` alone finds **every**
   to-do. That is a wrong answer, with no error.
2. **Make all white space one normal space.** `" ".join(text.split())` does it. Python's `split()`
   with no argument breaks on **every** kind of white space: spaces, tabs, line breaks, and the
   wide Japanese space (U+3000, `　`) that a Japanese keyboard types. So `"  buy　milk\n"` becomes
   `"buy milk"`. This also trims the ends.
3. **Cut to 200 characters.** 200 is the longest title (`Todo.title` has `max_length=200`). So any
   title can be pasted in whole, and the address stays short. The number comes from the model, not
   written twice: `SEARCH_MAX_LENGTH = Todo._meta.get_field("title").max_length`. The search box
   has the same `maxlength`. After the cut, a space at the end is removed.
4. **Drop it if empty.** `q=`, `q=%20%20`, `q=%E3%80%80` (a wide space) and `q=%00` all mean "no
   search".

So `list_params(list_params(x))` is always the same as `list_params(x)`. This matters, because
`filter_links` calls `list_params` again on values it already checked.

**How we tried it.** With a short Python script, using Python's own `sqlite3` module and an
in-memory database (one that lives only while the script runs): we added the to-dos from the tables
below, and ran the same `LIKE ... ESCAPE '\'` question that Django sends for `icontains`. We also
asked Python's `unicodedata.category()` for each character above.

### How a to-do matches

- One new step in the list query: `search_todos(todos, params)`. It runs **after**
  `filter_todos`.
- It looks for the search word in the title with `icontains`: "the title contains the word, big or
  small letters do not matter" (with the limits below).
- It looks for **two forms of the word**, and a to-do matches if it has **either** one (an **OR**):
  the word as typed, and its **NFKC form** (see the next section). Most words have one form only;
  then there is one search.
- The whole search text is one piece. `buy milk` finds `Buy milk`, but not `milk to buy`.
- **`%` and `_` are normal characters.** In the database language (SQL), a search like this uses
  `LIKE`, where `%` means "anything" and `_` means "any one character". Django **escapes** them
  for us (it puts a `\` in front, so they mean only themselves). So `q=%` finds `100% done`, not
  every to-do, and `q=file_name` finds `file_name` but not `file-name`. A test checks this.

### Wide letters find normal letters (owner decision)

A Japanese keyboard often types **wide letters**: `ｍｉｌｋ` instead of `milk`, `１２` instead of
`12`, and half-width katakana `ｷﾞｭｳﾆｭｳ` instead of `ギュウニュウ`. To the computer they are different
characters.

**NFKC** is a Unicode rule that turns these into their usual form: `ｍｉｌｋ` → `milk`, `ＭＩＬＫ` →
`MILK`, `ｷﾞｭｳﾆｭｳ` → `ギュウニュウ`. Python has it: `unicodedata.normalize("NFKC", text)`.

**The owner decided: wide letters should find normal ones.** So we search for the word as typed
**or** its NFKC form:

- `ｍｉｌｋ` finds `Buy milk` (through the NFKC form `milk`).
- `ＭＩＬＫ` finds `Buy milk` (through `MILK`) **and** still finds a title saved as `ＭＩＬＫ tea`
  (through the word as typed). If we searched **only** the NFKC form, `ＭＩＬＫ tea` would be lost.
- The OR can only **add** matches. Every to-do found before is still found.
- **No migration.** The titles in the database do not change. Only the search word gets a second
  form.
- The box, the message and the address still show the word **as typed**. NFKC is used only inside
  `search_todos`.

**The gap that remains.** A title **saved** in wide letters is not found by typing normal letters:
the title `ＭＩＬＫ tea` is not found by `milk`. Its NFKC form is not stored anywhere, so the database
cannot compare with it. Closing this gap needs a cleaned copy of each title in its own column (a
migration). That is in "What we will not do (yet)".

### Other differences that remain

**Only on SQLite** (our database). SQLite knows big and small letters only for A to Z. Another
database, like PostgreSQL, would find these:

| The to-do | The search | Found on SQLite? |
|---|---|---|
| `Buy milk` | `MILK` | yes |
| `CAFÉ` | `café` | **no** — `É` is not A to Z |
| `ＭＩＬＫ tea` | `ｍｉｌｋ` | **no** — wide `Ｍ` and wide `ｍ` are not A to Z, and NFKC gives `milk`, which is not in the title either |

**On any database.** These are different characters everywhere, also after NFKC:

| The to-do | The search | Found? |
|---|---|---|
| `牛乳を買う` | `牛乳` | yes — the text is the same |
| `ＭＩＬＫ tea` | `milk` | **no** — the gap above |
| `カイモノ` (katakana) | `かいもの` (hiragana) | **no** — NFKC does not change one into the other |

We tried every row with the script in "How we tried it", with both forms of the word.

We do **not** write a test that says `CAFÉ` or `ＭＩＬＫ tea` is not found. That would be a test for a
weakness, and it would break when we close the gap.

### The search form on the page

```html
<form class="search" role="search" method="get" action="{% url 'todo_list' %}">
  {% for name, value in search_keeps %}<input type="hidden" name="{{ name }}" value="{{ value }}">{% endfor %}
  <label for="search-q">Search to-dos</label>
  <input type="search" id="search-q" name="q" value="{{ q }}" maxlength="200">
  <button type="submit">Search</button>
  {% if q %}<a href="{{ clear_search_url }}">Clear search</a>{% endif %}
</form>
```

- `role="search"` tells a screen reader (a program that reads the page aloud) "this is the search".
- The label `Search to-dos` is **visible**. A search box with no label is hard to understand.
- `type="search"` is a normal text box. Some browsers add a small × to empty it. That is fine.
- No `autofocus`: the add box keeps it. Adding is still the main job of the page.
- `maxlength` is written from `SEARCH_MAX_LENGTH` (the view gives it to the template), not typed
  as a number.
- **The hidden inputs keep the other parameters.** A `GET` form sends **only** its own fields. So,
  on `/?show=active`, a form with only `q` would go to `/?q=milk` and lose the filter. The view
  gives the template `search_keeps`: every checked parameter except `q`, for example
  `[("show", "active")]`. On `/`, it is empty, so there is no hidden input. When sort (9) adds
  `sort`, it is kept with no change here.
- **The hidden inputs come before the box.** A browser puts the fields into the address in the
  order they are on the page. So the address is `/?show=active&q=milk`, with `show` first — the same
  order as `list_query`. The same view has one address, not two.
- **The word in the box is safe.** `{{ q }}` is **autoescaped**: Django turns `<`, `>`, `"`, `&` and
  `'` into codes like `&lt;` before it writes them into the page. So a search for
  `"><script>alert(1)</script>` is shown as text, and never runs.

### "Clear search"

- A normal link, shown only when there is a search.
- It goes to the same list **without `q`, but with the other parameters**. On
  `/?show=active&q=milk`, it goes to `/?show=active`. The view builds it from `list_params`, so it
  is always our own address.
- A link, not a button, because it only reads.

### The message when nothing matches

When there is a search, the message names the filter and the word:

| Filter | With a search | Without a search (as today) |
|---|---|---|
| All | `No to-dos match "milk".` | `Nothing to do yet. Add something above.` |
| Active | `No active to-dos match "milk".` | `Nothing left to do.` |
| Completed | `No completed to-dos match "milk".` | `Nothing completed yet.` |

"No active to-dos match" is more honest than "No to-dos match": a completed `Buy milk` may exist,
hidden by the filter.

The start of each message ("No active to-dos match") is one more column in the `FILTERS` table, next
to the empty message it already has. So each filter's words stay in one place. The word `q` is
added in the template, so it is autoescaped.

### The filter, the forms and the redirects keep the search by themselves

This is the reason for the filter plan's helpers. Because `q` is now in `list_params`:

- the filter links keep it: on `/?q=milk`, the Active link is `/?show=active&q=milk`;
- every `POST` form ends with `{{ list_query }}`, so it posts to `/5/toggle/?q=milk`;
- `back_to_list` sends the browser back to `/?q=milk`;
- after the rebase, the Edit link, the edit form and its Cancel link keep it too (4 uses
  `list_query`).

No code changes for these. Tests check each one.

**A to-do can leave the list after Add.** On `/?q=milk`, a person adds `Call home`. The browser goes
back to `/?q=milk`, so `Call home` is not shown. This is the same as adding on the Completed filter.
We keep it, so that every action works the same way. The box still shows `milk`, and "Clear
search" is right there.

### The count and "Delete completed" do not change

Decided in wave 1: both are about the **whole** table, not what is shown. Search keeps that:

- `2 items left` stays `2 items left` when the search shows only one to-do.
- The footer (`<div class="list-footer">`) is still there when the search finds nothing.
- **"Delete completed" deletes every completed to-do in the whole list, also the ones the search
  hides.** This is decided. The button says how many (`Delete 2 completed to-dos`), so the person
  is told before they press it.

`search_todos` only changes `todos`. `has_todos`, the count and `completed_ids` do not read
`todos`. Tests check this.

## What we will not do (yet)

- **No search in the due date or the priority.** Only the words a person typed: the title, and
  after the rebase the notes.
- **No "every word" search.** `milk buy` does not find `Buy milk`.
- **No finding of a title saved in wide letters by typing normal letters** (`ＭＩＬＫ tea` by
  `milk`), **no matching of `É` with `é` on SQLite, and no matching of katakana with hiragana.** See
  the tables above. The first two need a cleaned (NFKC, lower-case) copy of each title in its own
  column, which is a migration. Katakana and hiragana need more than NFKC.
- **No search while typing.** That needs JavaScript. The person presses Search or Enter.
- **No highlighting** of the word in the results, and **no "2 found"** count.
- **No full-text search** (a special database feature for big texts). The list is small;
  `icontains` is fast enough.

## Changes in behaviour

1. `/?q=milk` shows only the to-dos whose title contains `milk`. Before, `q` was ignored, and every
   to-do was shown. A word typed in wide letters (`ｍｉｌｋ`) also finds normal letters.
2. The page has a search form: a label, a box and a Search button.
3. With a search: the box shows the word, there is a "Clear search" link, and an empty result says
   `No to-dos match "milk".` (or `No active ...` / `No completed ...`).
4. The filter links, every `POST` form and every redirect keep `q`. Before, `q` was dropped.
5. After a failed add, the page is still searched.

What stays the same:

- `/`, `/?q=` and `/?q=%20` look like `/` today, plus the search form. Same empty message.
- The filter works as before. `/?show=active` without a search is unchanged.
- Add, toggle, delete and delete completed still accept `POST` only. Search changes nothing in the
  database.
- The count and "Delete completed" still use the whole table.
- The redirect still always starts with `/`. Nothing from the request reaches it unchecked.

## The changes, one file at a time

No model change, so **no migration**.

### 1. `todos/views.py` — the views

**A new helper and the `q` check in `list_params`**, after the `show` check. `show` first, then `q`,
so the address is always `?show=active&q=milk`:

```python
import unicodedata

SEARCH_MAX_LENGTH = Todo._meta.get_field("title").max_length  # 200: the longest title


def clean_search(text):
    """The search word: no invisible characters, one space between words, at most 200 characters."""
    text = "".join(
        ch for ch in text if ch.isspace() or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    text = " ".join(text.split())
    return text[:SEARCH_MAX_LENGTH].rstrip()


def list_params(data):
    params = {}
    # ... the show check, unchanged ...
    q = clean_search(data.get("q") or "")
    if q:
        params["q"] = q
    return params
```

- `ch.isspace()` keeps white space (a tab, a line break, `　`) for the next line, which turns it
  into one normal space. Other control and format characters are removed.
- `data.get("q") or ""`: no `q` in the address becomes an empty text.

**Two new helpers for the list query**, next to `filter_todos`:

```python
from django.db.models import Q


def search_words(q):
    """The search word as typed, and its NFKC form if that is different.

    NFKC turns wide letters into normal ones: "ｍｉｌｋ" becomes "milk".
    """
    words = [q]
    plain = unicodedata.normalize("NFKC", q)
    if plain != q:
        words.append(plain)
    return words


def search_todos(todos, params):
    """Only the to-dos whose title contains the search word, as typed or in its NFKC form."""
    q = params.get("q")
    if not q:
        return todos
    match = Q()
    for word in search_words(q):
        match |= Q(title__icontains=word)
    return todos.filter(match)
```

- `Q(...)` is Django's way to write one condition. `match |= Q(...)` adds "**or** this" to it.
- `search_words` needs no database, so it has its own unit test.
- `list_params` does **not** use NFKC. The address and the box keep the word as typed.

**In `FILTERS`**: one more column, the start of the "no match" message: `"No to-dos match"`,
`"No active to-dos match"`, `"No completed to-dos match"`. The filter code that reads `FILTERS`
gets one more name when it unpacks a row.

**In `page_context`**: one line for the query, and these keys, each on its own line:

```python
def page_context(request, form):
    params = list_params(request.GET)
    todos = Todo.objects.all()
    todos = filter_todos(todos, params)
    todos = search_todos(todos, params)                                  # new
    without_q = {k: v for k, v in params.items() if k != "q"}            # new
    return {
        ...  # every key from 5, 12, 11 and 8 stays
        "q": params.get("q", ""),                                        # new
        "search_max_length": SEARCH_MAX_LENGTH,                          # new
        "search_keeps": list(without_q.items()),                         # new
        "clear_search_url": reverse("todo_list") + list_query(without_q),  # new
        "no_match_start": ...,  # the FILTERS column for the chosen filter  # new
    }
```

`filter_links`, `back_to_list`, and the views `todo_add`, `todo_toggle`, `todo_delete` and
`todo_delete_completed`: **no change**. They keep `q` because `list_params` keeps it.

### 2. `todos/templates/todos/todo_list.html` — the page

- **The search form** (see Decisions), between the add form and the filter links. The order on the
  page is: add form, search form, filter links, list, footer.
- **The empty message** gets the search case first:

  ```html
  {% empty %}
    <li>{% if q %}{{ no_match_start }} "{{ q }}".{% else %}{{ ...the filter's empty message, as today... }}{% endif %}</li>
  ```

- **The CSS:**

  ```css
  form.search { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
  form.search input[type=search] { flex: 1 1 10rem; padding: 0.4rem; font-size: 1rem; }
  ```

  `flex: 1 1 10rem`: the box grows to fill the row, but is never smaller than about 10 letters.
  On a phone, "Clear search" moves to the next row by itself (`flex-wrap`).

### 3. `todos/urls.py`, `todos/models.py`, `todos/forms.py` — no change

We do not use a Django `Form` for the search box. `list_params` is the one place that checks every
list parameter, and a form would be a second place. The box is one input.

### 4. `todos/tests/integration/helpers.py` — maybe one small addition

The tests use `page_parts` to find the `action` of every `POST` form. If it does not have that yet
(the filter tests used one), move that function here. Do not copy it into the search test file.

### 5. `AGENTS.md`

- `todos/views.py` row: add "The list can be searched (`?q=milk`). `list_params` cleans `q`: no
  invisible characters, one space between words, at most 200 characters. `search_todos` looks for
  the word as typed or in its NFKC form, so wide letters find normal ones."
- Template row: "The one page: the add form, the search form, the filter links and the list."

## After 6, 21, 7 and 4 are on `main`

This feature merges last in wave 2. Before it joins the merge queue, the builder **rebases** on
`main` with 6 (priority), 21 (details pane), 7 (notes) and 4 (edit) in it. A **rebase** moves this
branch's commits so they start from the newest `main`. Then:

1. **`page_context` and the template.** Keep every key and every part of the page from 6, 21, 7 and
   4. Each one added its own lines, so the clash should be small.
2. **Notes (7): search the notes too. Decided.** In `search_todos`, each word looks in the title
   **or** the notes:

   ```python
   for word in search_words(q):
       match |= Q(title__icontains=word) | Q(notes__icontains=word)
   ```

   So wide letters find normal letters in the notes too. Change the docstring and the `AGENTS.md`
   row to "the title or the notes".
3. **Details pane (21): how the person sees why a to-do matched.** Notes are **not** shown on the
   list rows. They are shown in the details pane, when the person clicks a title
   (`?selected=<id>`). So a to-do that matches only in its notes shows a row whose title does not
   have the word. That can look like a mistake.
   - `selected` is part of `list_params`. So the search form keeps it (`search_keeps` is "every
     parameter except `q`"), and "Clear search" keeps it too. No change here.
   - **TODO at the rebase — align with `details-pane.md`.** That plan did not exist when this plan
     was written. At the rebase, read it, and follow what it decided for these two questions. If it
     decided nothing, ask the orchestrator before merging; do not decide alone:
     1. **The hint on the row.** Our recommendation: when the title does **not** contain the word
        but the notes do, the row shows a small grey `matched in notes` after the title (a
        `<span class="match-hint">`). The person clicks the title, and the pane shows the notes.
        The view knows this with no extra query: add `title_match=Q(...)` as an annotation (a value
        the database works out for each row) with `ExpressionWrapper(..., BooleanField())`, using
        the same `search_words`.
     2. **A selected to-do that the search hides.** On `/?q=milk&selected=5`, if to-do 5 does not
        match `milk`, does the pane still show it? That is the details pane's rule; search does not
        change it.
4. **Edit (4).** The Edit link, the edit form and its Cancel link use `list_query` (see the edit
   plan), so they keep `q` with no change here. The tests below check it.
5. **Priority (6).** Nothing to do: search does not look at the priority.
6. Write the tests in "After the rebase" below. Run them, then fix what fails.

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code. Every check on the page
is an **exact element**, with `assertContains(..., html=True)`: Django compares whole HTML elements,
not pieces of text. "Not shown" is the same exact element with `count=0`. For example, "`Call home`
is not shown" means `assertContains(response, '<span class="title">Call home</span>', html=True,
count=0)`. There is one page-wide check, on purpose: the escaping test checks that the raw text
`<script>alert(1)` is nowhere on the page.

Addresses with a search are built by the test client, not by hand:
`self.client.get("/", {"q": "%"})`. The client encodes the value correctly.

### Bottom: unit tests (`todos/tests/unit/test_list_params.py`, made by 8)

These need no database. They use `SimpleTestCase`, Django's test class for tests that do not use
the database. Each value is one `subTest`. The input is a `QueryDict` (what Django makes from an
address), for example `QueryDict("q=milk")`.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it checks | How it fails today |
|---|---|---|
| `test_list_params_keeps_the_search` | `q=milk` → `{"q": "milk"}`; `q=Buy+milk` → `{"q": "Buy milk"}`; `q=%E7%89%9B%E4%B9%B3` → `{"q": "牛乳"}`; `q=%3Cscript%3E` → `{"q": "<script>"}` (cleaning is not escaping; the template escapes); `q=%EF%BD%8D%EF%BD%89%EF%BD%8C%EF%BD%8B` → `{"q": "ｍｉｌｋ"}` (wide letters are kept as typed: NFKC is not done here) | `{}`: `q` is dropped today |
| `test_list_params_makes_white_space_one_space` | `q=%20%20milk%20` → `"milk"`; `q=buy%20%20%20milk` → `"buy milk"`; `q=buy%09milk` (a tab) → `"buy milk"`; `q=milk%0D%0A` (a line break) → `"milk"`; `q=buy%E3%80%80milk` (a wide space) → `"buy milk"` | `{}` |
| `test_list_params_removes_invisible_characters` | `q=mi%00lk` → `"milk"`; `q=mi%07lk` (bell) → `"milk"`; `q=mi%E2%80%8Blk` (zero-width space) → `"milk"`; `q=mi%C2%ADlk` (soft hyphen) → `"milk"` | `{}` |
| `test_list_params_cuts_a_long_search` | 250 × `a` → 200 × `a`; 199 × `a` + space + `b` → 199 × `a` (the cut ends on a space, which is removed) | `{}` |
| `test_list_params_keeps_search_and_filter_in_order` | `q=milk&show=active` → `{"show": "active", "q": "milk"}`, and `list(result)` is `["show", "q"]` | `{"show": "active"}` |

**Tests that protect what already works.** These **pass** before the change. Each one has a
**deliberate bug**: after the code is written, put the bug in for a moment, see the test fail, then
take it out.

| Test | What it checks | The deliberate bug that makes it fail |
|---|---|---|
| `test_list_params_drops_an_empty_search` | `q=`, `q=%20%20`, `q=%E3%80%80`, `q=%00`, `q=%E2%80%8B`, `q=%0D%0A`, no `q` → `{}` | in `list_params`, write `if q is not None:` instead of `if q:` |
| `test_list_params_twice_is_the_same` | for every value in the tests above, `list_params(list_params(x)) == list_params(x)` | in `clean_search`, leave out `.rstrip()` after the cut (199 × `a` + space + `b` then gives a space at the end the first time, and none the second time) |
| `test_list_query_with_search` | `{"q": "buy milk"}` → `"?q=buy+milk"`; `{"show": "active", "q": "milk"}` → `"?show=active&q=milk"`; `{"q": "牛乳"}` → `"?q=%E7%89%9B%E4%B9%B3"`; `{"q": "a&next=x"}` → `"?q=a%26next%3Dx"` | in `list_query`, write `"?" + "&".join(f"{k}={v}" for k, v in params.items())` (no encoding) |

### Bottom: unit tests (`todos/tests/unit/test_search_words.py`, new file)

A separate file, so that its `ImportError` today does not hide the `list_params` tests above.
`SimpleTestCase`, one `subTest` per value.

| Test | What it checks | How it fails today |
|---|---|---|
| `test_search_words_adds_the_nfkc_form` | `"ｍｉｌｋ"` → `["ｍｉｌｋ", "milk"]`; `"ＭＩＬＫ"` → `["ＭＩＬＫ", "MILK"]`; `"ｷﾞｭｳﾆｭｳ"` → `["ｷﾞｭｳﾆｭｳ", "ギュウニュウ"]`; `"１２"` → `["１２", "12"]` | `ImportError`: there is no `search_words` yet |
| `test_search_words_once_when_nothing_changes` | `"milk"` → `["milk"]`; `"牛乳"` → `["牛乳"]`; `"café"` → `["café"]` (one search, not the same one twice) | `ImportError` |

### Middle: integration tests (`todos/tests/integration/test_search.py`, new file)

A new file, so it does not clash with 6, 21, 7 and 4, which change `test_views.py`. The form helper
comes from `helpers.py`.

Unless a row says otherwise, the to-dos are `Buy milk` (active), `Milk the cow` (completed) and
`Call home` (active). Redirects are checked with `response["Location"]`, exactly.

**The search form, written out.** Two tests compare the **whole** form as one exact element. On
`/`, it is:

```html
<form class="search" role="search" method="get" action="/">
  <label for="search-q">Search to-dos</label>
  <input type="search" id="search-q" name="q" value="" maxlength="200">
  <button type="submit">Search</button>
</form>
```

This one check proves the label, the box, the button, **no hidden input** and **no Clear search
link**, all at once.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_search_finds_part_of_the_title_in_any_case` | `subTest` each: `q` = `milk`, `MILK`, `Milk` | `<span class="title">Buy milk</span>` and `<span class="title">Milk the cow</span>` once each; `<span class="title">Call home</span>` `count=0` | `Call home` is shown: `q` is ignored |
| `test_search_finds_japanese` | to-dos `牛乳を買う` and `Call home`; `q=牛乳` | `牛乳を買う` once; `Call home` `count=0` | `Call home` is shown |
| `test_wide_letters_find_normal_letters` | to-dos `Buy milk`, `ギュウニュウ`, `Call home`; `subTest` each: `q=ｍｉｌｋ` → `Buy milk`; `q=ＭＩＬＫ` → `Buy milk`; `q=ｷﾞｭｳﾆｭｳ` (half-width katakana) → `ギュウニュウ` | the expected title span once; the others `count=0` | every to-do is shown. (With a plain `title__icontains=q`, it still fails: `ｍｉｌｋ` finds nothing) |
| `test_typed_wide_letters_find_a_wide_title` | to-dos `ＭＩＬＫ tea`, `Buy milk`, `Call home`; `q=ＭＩＬＫ` | `ＭＩＬＫ tea` **and** `Buy milk` once each; `Call home` `count=0` | `Call home` is shown. Deliberate bug, to prove the OR: search **only** the NFKC form (`search_words(q)[-1]`). `ＭＩＬＫ tea` is then lost, and the test fails |
| `test_search_treats_wildcards_as_text` | to-dos `100% done`, `file_name`, `file-name`, `Call home`; `subTest` each: `q=%` → only `100% done`; `q=_` → only `file_name`; `q=file_name` → only `file_name` | each title span: once if expected, `count=0` if not. `file-name` matters: an unescaped `_` would match its `-` | every to-do is shown |
| `test_search_form_on_the_plain_list` | open `/` | the whole form above, exactly | there is no search form |
| `test_search_form_with_a_filter_and_a_word` | open `/?show=active&q=milk` | the whole form exactly: first `<input type="hidden" name="show" value="active">`, then the label, then `<input type="search" id="search-q" name="q" value="milk" maxlength="200">`, the button, and `<a href="/?show=active">Clear search</a>` | there is no search form |
| `test_empty_search_is_the_same_as_no_search` | `subTest` each: `/?q=`, `/?q=%20%20`, `/?q=%E3%80%80` | all three titles once each; the whole plain form above (so `value=""` and no Clear search); exactly `<a href="/" aria-current="page">All</a>` | there is no search form |
| `test_search_word_is_escaped` | `q` = `"><script>alert(1)</script>` | exactly `<input type="search" id="search-q" name="q" value="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;" maxlength="200">`; exactly `<li>No to-dos match "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;".</li>`; and (page-wide, on purpose) the raw text `<script>alert(1)` is not in the page | there is no search box and no message |
| `test_no_match_message_for_each_filter` | `subTest` each: `/?q=banana` → `<li>No to-dos match "banana".</li>`; `/?show=active&q=banana` → `<li>No active to-dos match "banana".</li>`; `/?show=completed&q=banana` → `<li>No completed to-dos match "banana".</li>` | the exact `<li>` | the list is not searched, so it is not empty: no message |
| `test_search_and_filter_together` | open `/?show=active&q=milk` | `Buy milk` once; `Milk the cow` and `Call home` `count=0` | `Call home` is shown |
| `test_filter_links_keep_the_search` | open `/?q=milk` | exactly `<a href="/?q=milk" aria-current="page">All</a>`, `<a href="/?show=active&amp;q=milk">Active</a>`, `<a href="/?show=completed&amp;q=milk">Completed</a>` | the links are `/`, `/?show=active`, `/?show=completed` |
| `test_every_post_form_keeps_the_search` | open `/?show=active&q=milk` | the helper finds at least 3 `POST` forms (add, toggle, delete; and Delete completed when there is a completed to-do: make `Milk the cow` match by opening `/?q=milk` as a second `subTest`), and **every** action ends with the page's query | the actions end with `?show=active`, or have no query |
| `test_actions_go_back_to_the_search` | one `subTest` per row: add `Milk again` to `/add/?q=milk` → `/?q=milk`; toggle `Buy milk` with `?q=milk` → `/?q=milk`; delete with `?show=active&q=milk` → `/?show=active&q=milk`; Delete completed (with `Milk the cow`'s id) with `?q=milk` → `/?q=milk`; toggle with `q=牛乳` → `/?q=%E7%89%9B%E4%B9%B3`; toggle with `q=buy milk` → `/?q=buy+milk`; toggle with `q=a&next=https://evil.example` → `/?q=a%26next%3Dhttps%3A%2F%2Fevil.example` (the `&` stays inside `q`) | `response["Location"]`, exactly | each one redirects without `q` |
| `test_add_error_keeps_the_search` | post title `New`, `due_date=not-a-date` to `/add/?q=milk` | status 200; `Enter a valid date.`; `Buy milk` once and `Call home` `count=0`; the exact search box with `value="milk"` | `Call home` is shown: the page is not searched |

**Tests that protect what already works.** These **pass** before the change, because today `q`
does nothing. Each one has a **deliberate bug** to see it fail:

| Test | What it checks | The deliberate bug |
|---|---|---|
| `test_search_changes_nothing` | a `GET` to `/?q=milk` leaves the number of to-dos, and each `done`, the same | in `search_todos`, write `todos.exclude(title__icontains=q).delete()` before the return |
| `test_count_and_footer_ignore_the_search` | `subTest` each: `/?q=milk` and `/?q=banana`: exactly `<p class="count">2 items left</p>` (the whole table has 2 active) | count from the shown list: `todos.filter(done=False).count()`, and `has_todos` from `todos.exists()` |
| `test_delete_completed_ignores_the_search` | to-dos `Buy milk` and `Call home`, both completed; open `/?q=banana` (nothing matches) | exactly `<button type="submit">Delete 2 completed to-dos</button>`, and both ids in 11's hidden inputs (exact elements) | make `completed_ids` read from the shown `todos` |

One more deliberate bug, for a test that fails today but for another reason:
`test_search_treats_wildcards_as_text` fails today because nothing is searched. To see it catch the
**real** bug, write the search without Django's escaping for a moment:
`todos.extra(where=["title LIKE %s"], params=["%" + q + "%"])`. The `%` and `_` rows fail. Put it
back.

`git diff` must not show any deliberate bug afterwards.

Every test that exists before this change must still pass. That includes all of `test_filter.py`:
none of them uses `q`, so their addresses do not change.

### After the rebase on 6, 21, 7 and 4

Added to `test_search.py` after the rebase:

| Test | What it does | What it checks | How it fails then |
|---|---|---|---|
| `test_wide_letters_find_words_in_the_notes` | to-do `Shopping` with notes `milk and eggs`; `Call home`; `q=ｍｉｌｋ` | `Shopping` once; `Call home` `count=0` | `Shopping` is not shown: the notes are not searched |
| `test_search_finds_words_only_in_the_notes` | to-do `Shopping` with notes `milk and eggs`; to-do `Call home`; `q=MILK` | `<span class="title">Shopping</span>` once; `Call home` `count=0` | `Shopping` is not shown: only the title is searched |
| `test_edit_link_keeps_the_search` | open `/?q=milk` | exactly `<a class="edit" href="/<id>/edit/?q=milk" aria-label="Edit Buy milk">Edit</a>` | passes at once if 4 used `list_query` (expected). Then put in a deliberate bug: the Edit link without `{{ list_query }}`. It fails |
| `test_edit_page_keeps_the_search` | `GET /<id>/edit/?show=active&q=milk` | the edit form's `action` is exactly `/<id>/edit/?show=active&q=milk` (with the helper); exactly `<a href="/?show=active&amp;q=milk">Cancel</a>` | the same as above: deliberate bug, Cancel built without `list_params` |

| `test_search_form_keeps_the_selected_todo` | open `/?q=milk&selected=<id of Buy milk>` | the search form has exactly `<input type="hidden" name="selected" value="<id>">`, and "Clear search" is exactly `<a href="/?selected=<id>">Clear search</a>` (the order in the address is the one 21 decided in `list_params`) | passes at once if 21 put `selected` in `list_params` (expected). Deliberate bug: build `search_keeps` from `show` only. It fails |
| **TODO** `test_notes_only_match_shows_a_hint` | to-do `Shopping` with notes `milk and eggs`; `q=milk` | the exact hint element that `details-pane.md` (or the orchestrator) decides, for example `<span class="match-hint">matched in notes</span>`, once; and `count=0` on a title match | there is no hint |

**Note for the rebase.** After 21, a title on the list is probably a link (to `?selected=<id>`), not
`<span class="title">`. Change the exact title element in every test of this file to the one 21
uses, in one place: a small helper `title_element(todo)` in `helpers.py`, if 21 did not add one.

`test_search_finds_part_of_the_title_in_any_case` keeps checking the title after the change to `Q`.
`test_every_post_form_keeps_the_search` also covers any new `POST` form from 6, 21, 7 or 4 on the list
page.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

**No change.** Search is a new way to look at the same list, not a new journey. The integration
tests above check every part of it.

The CUJ test still passes after the change. We checked each step:

- It opens `/`. With no search, the empty message is the same as today: `Nothing to do yet`.
- `get_by_label("New to-do")` finds the add box. The search box's label is `Search to-dos`, which
  does not contain `New to-do`.
- `get_by_role("button", name="Add")` finds the Add button. Playwright matches part of the name,
  without big and small letters. `Search` does not contain `add`.
- The Done, Undo and Delete buttons are found **inside** the to-do, as before.

## Steps, in order

1. Write the unit tests and the integration tests. Run `make test`:
   - the 5 new `list_params` tests fail as listed (`q` is dropped), and the 3 protecting unit tests
     pass,
   - `test_search_words.py` fails with `ImportError` (its 2 tests),
   - the 15 new-behaviour integration tests fail as listed,
   - the 3 protecting integration tests pass.
2. Change `views.py`: `SEARCH_MAX_LENGTH`, `clean_search`, the `q` check in `list_params`,
   `search_words`, `search_todos`, the new `FILTERS` column, and the new line and keys in `page_context`.
3. Change the template: the search form, the empty message, the CSS.
4. Run `make test`: every test passes. Run `make test-cuj`: the CUJ test passes, unchanged.
5. Put in each deliberate bug, one at a time (see the tables). Each named test fails. Take it out.
   Check `git diff`.
6. Run `make run` and open the page:
   - Add `Buy milk`, `牛乳を買う` and `Call home`. Finish `Buy milk`.
   - Search `MILK`, then `牛乳` (also with a Japanese keyboard, which types the wide space). Type
     `ｍｉｌｋ` in wide mode: `Buy milk` is found. Press Clear search.
   - Choose Active, then search `milk`: `No active to-dos match "milk".` Press All: `Buy milk`, and
     the address still has `q=milk`.
   - Search `<b>hi</b>`: it is shown as text, not in bold.
   - Make the window narrow, like a phone: the search row still fits.
7. Update `AGENTS.md`.
8. When 6, 21, 7 and 4 are on `main`: rebase, then do "After 6, 21, 7 and 4 are on `main`" with
   its tests, and its details-pane TODO. Run `make test` and `make test-cuj` again.
9. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected". This
   feature has no migration.
10. Run `make check`. Commit.

## Risks

- **A to-do "disappears" after Add** when it does not match the search. Decided (the same as the
  filter). The box and "Clear search" show why.
- **The gap: a title saved in wide letters is not found by normal letters** (`ＭＩＬＫ tea` by
  `milk`). Also `É` on SQLite, and katakana/hiragana. Written down; closing it needs a migration.
- **NFKC can add surprising matches.** For example `①` searches also for `1`, and `ﬁ` also for
  `fi`. It only ever adds matches, never loses one, so we accept it.
- **A notes-only match looks odd on the list**, because notes are in the details pane, not on the
  row. The hint is a TODO for the rebase, aligned with the details-pane plan.
- **Removing format characters** also removes the invisible joiner (U+200D) inside some emoji, like
  👩‍💻. A search for such an emoji then does not find it. This is rare in a to-do list; the gain
  (a copied word with a hidden zero-width space still matches) is bigger.
- **Many spaces become one.** A title saved with two spaces, `buy  milk`, is not found by
  `buy  milk`, only by `buy` or `milk`. Rare, and the add form does not stop it today.
- **Clashes when rebasing on 6, 21, 7 and 4.** All change `page_context` and the template. One key per
  line and one step per line keep the clash small.
- **Speed.** `icontains` reads every row. For a list of hundreds of to-dos, that is still fast.
