# Plan: notes on a to-do (feature 7)

Status: **approved, in progress.** The parts that do not need 6 (priority) and 21 (details pane)
are built; the rest waits for the rebase. See "What happened".

The first version was checked by an adversarial review (a reviewer whose job is to find what is
wrong), on Django 5.2.17. Every finding is fixed below. The third version follows an owner change:
the notes are shown **only in the details pane** (feature 21), not on the list rows.

This is feature 7, in wave 2 of [the rollout plan](feature-rollout.md). The merge order in wave 2
is: 6 priority → 21 details pane → **7 notes** → 4 edit → 10 search. The branch is `feature/notes`.

**The starting point.** The builder starts from `main` **after 6 (priority) and 21 (details pane)
are merged**, on top of wave 1 (5 due date, 12 count, 11 delete completed, 8 filter). On that
`main`:

- `todos/models.py`: `Todo` has `title`, `done`, `due_date`, `priority`, `created_at`.
  `TodoQuerySet` (with `remaining()` and `completed()`) is `Todo.objects`.
- `todos/forms.py`: `TodoForm`, with `fields` one name per line: `title`, `due_date`, `priority`.
- `todos/admin.py`: `TodoAdmin`, with 6's `list_display` and `list_filter`.
- `todos/views.py`: `page_context(request, form)`, the **one** place for the page's keys;
  `list_params`, `list_query`, `back_to_list`; and from 21, `selected_todo`, so `?selected=<id>`
  shows that to-do in the pane as `selected`.
- The template: each to-do's title is a link that selects it. When a to-do is selected, the page
  has `<aside class="details" aria-label="Details">` with a `<dl>` (Status, Due, Priority, Created)
  and a Close link.
- `todos/tests/integration/helpers.py`: `page_parts`/`PageParts` (`titles`, `selected_titles`,
  `panes`, `row()`), `title_element()`, `pane_element()`, `page_without_csrf()`, `list_footer()`.
- `todos/tests/unit/test_forms.py` exists (6 made it).

Every "How it fails today" below is true on **that** starting point.

## What we want

A to-do can have **notes**: a longer text, for example

```text
Low-fat. If there is none, get soy milk.
```

Notes are **optional**. A person can still add a to-do with only a title, as fast as today. When the
person clicks a to-do's title, the details pane shows its notes, with their line breaks. The list
rows do **not** show the notes: the list stays short and clean.

## Decisions

### The field: `TextField`, with a limit of 500 characters

```python
NOTES_LIMIT = 500

notes = models.TextField(
    blank=True,
    default="",
    max_length=NOTES_LIMIT,
    validators=[MaxLengthValidator(NOTES_LIMIT)],
)
```

- A **`TextField`** is Django's field for long text. A `CharField` (like `title`) is meant for
  short text, on one line. Notes can have several lines, so `TextField` is the right kind. Django
  also draws a `TextField` as a big text box with many lines (a `<textarea>`) by itself, in the
  admin and in our form.
- **Why a limit at all?** There are no accounts. Anyone who opens the site can post. Without a
  limit, one person could post a million characters. The notes are shown **in full** in the pane,
  so the limit also keeps the pane a sensible size. 500 characters is about 80 words.
- **Two parts, because Django does two different things with them:**
  - `max_length=NOTES_LIMIT` goes to the **form**: the form field checks the length, and Django
    puts `maxlength="500"` on the text box, so the browser stops typing at 500 too. On a
    `TextField`, `max_length` does **nothing else**: neither the database nor the model checks it.
  - `validators=[MaxLengthValidator(NOTES_LIMIT)]` goes to the **model**. A **validator** is a
    small check that Django runs on a value. With it, `todo.full_clean()` (the model's own check)
    really rejects notes that are too long, even when the to-do is saved without our form.
- `NOTES_LIMIT` is one name for the number, so the form, the model and the tests never disagree.

### One line break counts as one character

- A browser sends each line break in a `<textarea>` as **two** characters, `\r\n`. But the
  browser's own `maxlength` counts it as **one**. Django counts it as two. So a person could type
  exactly 500 characters with a few line breaks, the browser would allow it, and Django would say
  "too long". That is a bug.
- The fix: a small form field, `NotesField`, a kind of Django's `CharField`. Its `to_python` step
  (the step that turns what the browser sent into a Python value) changes every `\r\n` into `\n`.
  Django runs `to_python` **before** the length check, so the length is counted the way the browser
  counts it.
- We save `\n`. The database never gets `\r\n` from our form.
- The admin also gets `NotesField` (see "The admin"), so it counts the same way.

### Empty notes are `""`, never `NULL`

- `blank=True`: the form accepts empty notes.
- **No `null=True`.** For text, Django's rule is: "no text" is the empty text `""`, not `NULL`
  (the database's "nothing"). Then there is only **one** way to have no notes.
- `default=""`: old to-dos in the database get `""`. It also lets `makemigrations` run **without
  asking a question**. Without a default, Django stops and asks what to put in the old rows. The
  merge queue runs `makemigrations` again by itself, so it must never stop to ask.
- Spaces around the notes are removed, like the title. Notes of only spaces are saved as `""`.
  Django's `CharField` does this by itself (`strip=True` is the default), and `NotesField` keeps it.

### On the add form: yes, but folded away

The quick add (type a title, press Enter) must stay quick. A big text box on the add form would
push the list down and make the form busy, most of all on a phone. But a field that nobody can fill
is not a feature: feature 4 (edit) merges **after** this one.

So the notes box is on the add form, but **folded away** inside a `<details>` element:

- `<details>` is an HTML element that hides its content until the person clicks its title, the
  `<summary>`. The browser does this by itself, with **no JavaScript**. It works with the keyboard
  and with screen readers.
- Closed, it is one short line: `Notes (optional)`. The person who wants notes clicks it, and the
  text box opens.
- **When the page comes back with an error** (for example a bad date) and the person had typed
  notes, the box is **open**, so they can see their notes were kept. It is also open when the notes
  themselves have an error (too long). Notes of only spaces count as "no notes": the box stays
  closed.
- That choice is one small method on the form, `notes_box_open()`. It looks at the **cleaned**
  notes (after the spaces are removed), not at the raw text. So the rule is in Python, where a unit
  test can check it, and the template only asks the form.
- The text box has `aria-label="Notes"`, like the title box has `aria-label="New to-do"`. An
  `aria-label` is the name a screen reader says for a box. The summary is the visible label.
- The text box has 3 rows. The person can drag its corner to make it taller, but not wider
  (`resize: vertical`), so it never goes off a phone screen.
- **The one-form rule.** `notes` goes into the one `TodoForm`. So feature 4 (edit) gets the notes
  box with no more work. See "For feature 4 (edit)".

### No label may contain a button's word

The CUJ test finds buttons and boxes by their names, with **Playwright** (a tool that drives a real
browser from a test). Playwright matches **part** of a name by default. So a summary `Add notes`
would also match "Add".

**Rule:** no label, summary, `<dt>` or `aria-label` that this feature adds may contain the words
"Add", "Done", "Undo", "Delete" or "Due date". The words we use are `Notes (optional)` and `Notes`.

### Shown only in the details pane, as one more row

In the pane's `<dl>` (a **description list**: pairs of a name, `<dt>`, and a value, `<dd>`), after
`Created`:

```html
{% if selected.notes %}<dt>Notes</dt><dd class="notes">{{ selected.notes|linebreaksbr }}</dd>{% endif %}
```

- **Not on the list rows** (owner decision). A row stays: title link, priority label, due date,
  buttons.
- No notes: no `Notes` row in the pane at all.
- `linebreaksbr` is a Django template filter. It turns each line break into `<br>`. It understands
  both `\n` and `\r\n` (old data, or data saved from the shell).
- **It is safe.** `linebreaksbr` first **escapes** the text. To **escape** means to change the
  characters that mean something in HTML into harmless codes: `<` becomes `&lt;`, and so on. So a
  note like `<script>alert(1)</script>` is shown as text, and never runs. Running someone's code in
  another person's browser is called **XSS** (cross-site scripting). The list is shared, so this
  matters: one person's notes are shown to everyone. A test checks it.
- **Never** add `|safe` or `{% autoescape off %}` around the notes.

### Long notes in the pane

Feature 21 already made the pane ready for long content. We check that it works with the longest
notes:

- On a wide screen, the pane is **sticky** (it stays in view while the list scrolls), at most as
  tall as the window (`max-height: calc(100vh - 2rem)`), and **scrolls inside itself**
  (`overflow-y: auto`). So 500 characters with many line breaks never push the Close link out of
  reach: the person scrolls inside the pane.
- The pane has `overflow-wrap: anywhere`. A very long word with no spaces (for example a web
  address) breaks onto the next line instead of making the pane wider. `anywhere` (not
  `break-word`) also lets the grid's value column get narrow, so the `<dl>` does not grow wider than
  the pane.
- On a phone, the pane is under the list, not sticky, and the page scrolls as usual.
- **No new CSS for the pane.** CSS cannot be checked by Django's tests, so step 9 checks it by hand
  with the worst case: 500 characters, 20 line breaks, and one 200-letter word.

### The admin

- The admin's edit page shows the notes as a big text box by itself.
- **One line in `TodoAdmin`** makes the admin use `NotesField` too, so a line break counts as one
  character there as well:

  ```python
  formfield_overrides = {models.TextField: {"form_class": NotesField}}
  ```

  `formfield_overrides` is Django's built-in way to tell the admin "for this kind of model field,
  use this form field". Notes are the only `TextField` on `Todo`.
- We do **not** add notes to `list_display` (the admin's table): a long text column would make it
  hard to read.

### Search (feature 10) — what we expect

Feature 10 searches the **title or the notes**. With notes only in the pane, a to-do that matches
only in its notes would look like a wrong result. Feature 21 decided the answer: a hint on the row,
exactly `<small class="match-hint">matches in notes</small>`, shown only when there is a search and
the title does not match. The person clicks the title, and the pane shows the notes. Search builds
the hint; this feature only adds the field it searches.

## What we will not do (yet)

- **No notes on the list rows** (owner decision). Only in the pane.
- **No editing notes after adding.** Feature 4 (edit) does that.
- **No formatting** (bold, links, lists, Markdown). Notes are plain text. A web address is shown as
  text, not as a link.
- **No search** in the notes. Feature 10 does that.
- **No notes column in the admin list.**

## Changes in behaviour

1. The add form has a folded `Notes (optional)` box. Its text box has a 500-character limit.
2. Notes are saved with the to-do. Spaces around them are removed. Each line break is saved as
   `\n`, and counts as one character.
3. Notes longer than 500 characters are **rejected with an error**, and nothing is saved.
4. The details pane shows a `Notes` row with the notes, line breaks and escaping, when the selected
   to-do has notes.
5. When the add form comes back with an error, the notes the person typed are kept, and the notes
   box is open (unless the notes were only spaces).
6. The admin counts a line break in the notes as one character.

What stays the same: the list rows look exactly as before, with or without notes. A to-do with only
a title is added as today. The add form still posts to `{% url 'todo_add' %}{{ list_query }}`, and a
good add still goes back with `back_to_list`, keeping `selected`. The pane of a to-do without notes
is exactly the same as today. The CUJ journey does not change.

## The changes, one file at a time

### 1. `todos/models.py` — the model

At the top:

```python
from django.core.validators import MaxLengthValidator
```

Above `class TodoQuerySet`, one constant:

```python
NOTES_LIMIT = 500
```

Add one field to `Todo`, **after `priority`** and before `created_at`:

```python
    notes = models.TextField(
        blank=True,
        default="",
        max_length=NOTES_LIMIT,
        validators=[MaxLengthValidator(NOTES_LIMIT)],
    )
```

Do not touch `TodoQuerySet` or the `objects = ...` line.

### 2. The migration

A **migration** is a small file that tells the database how to change its tables. Django makes it
from `models.py`; we never write or edit it by hand:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

It must run **without a question** (that is why the field has `default=""`). Old to-dos get `""`.
The merge queue deletes this file and runs `makemigrations` again before it merges (the migration
rule), so its number does not matter now.

### 3. `todos/forms.py` — the form

A new form field, above `TodoForm`:

```python
class NotesField(forms.CharField):
    """A text field that counts a line break as one character, like the browser does.

    A browser sends a line break as "\r\n" (2 characters), but its maxlength counts it as 1.
    to_python runs before the length check, so we change "\r\n" to "\n" here.
    """

    def to_python(self, value):
        value = super().to_python(value)
        return value.replace("\r\n", "\n").replace("\r", "\n")
```

In `TodoForm`, add `notes` at the end of `fields`, tell Django to use `NotesField` for it, and give
it its widget. A **widget** is the part of a Django form field that draws the HTML.

```python
    class Meta:
        model = Todo
        fields = [
            "title",
            "due_date",
            "priority",
            "notes",
        ]
        field_classes = {"notes": NotesField}
        widgets = {
            # "title" and "priority": as they are
            "notes": forms.Textarea(attrs={"rows": 3, "aria-label": "Notes"}),
        }

    def notes_box_open(self):
        """Open the folded notes box when there are notes to see, or an error about them."""
        if self["notes"].errors:
            return True
        return bool(getattr(self, "cleaned_data", {}).get("notes"))
```

- `field_classes` is Django's built-in way to say "build this model field with this form field".
  Django still gives `NotesField` the limit from the model (`max_length=500`) and `required=False`.
- `cleaned_data` only exists after the form has been checked. On a new, empty form it does not
  exist, so `getattr(..., {})` gives an empty dictionary, and the box is closed.

### 4. `todos/views.py` — no change

`todo_add` already uses `TodoForm` and `form.save()`, so the notes are saved. Its error path already
uses `page_context(request, form)`, so the typed notes come back. The pane already gets the whole
`selected` to-do, notes included. No new key, no new query.

### 5. `todos/admin.py` — one line

In `TodoAdmin`, add:

```python
    formfield_overrides = {models.TextField: {"form_class": NotesField}}
```

with `from django.db import models` and `from .forms import NotesField` at the top.

### 6. `todos/templates/todos/todo_list.html` — the page

**The add form.** The notes box goes **after** the priority box and **before** the Add button:

```html
  <details class="add-notes"{% if form.notes_box_open %} open{% endif %}>
    <summary>Notes (optional)</summary>
    {{ form.notes.errors }}
    {{ form.notes }}
  </details>
  <button type="submit">Add</button>
```

Do not change the form's `action`. It keeps `{{ list_query }}`.

**Exactly what Django draws** for the text box (checked on Django 5.2.17; the tests use these):

- On a new page (an **unbound** form: one with no data sent yet):

  ```html
  <textarea name="notes" cols="40" rows="3" aria-label="Notes" maxlength="500" id="id_notes"></textarea>
  ```

- After a bad date, with notes typed (a **bound** form, no error on the notes):

  ```html
  <textarea name="notes" cols="40" rows="3" aria-label="Notes" maxlength="500" id="id_notes">Ring Ana first</textarea>
  ```

- When the notes are too long (bound, with an error on the notes). Django 5.2 adds
  `aria-invalid="true"` (it tells a screen reader "this box has a mistake") and `aria-describedby`
  (it points to the error message by its `id`):

  ```html
  <ul class="errorlist" id="id_notes_error"><li>Ensure this value has at most 500 characters (it has 501).</li></ul>
  <textarea name="notes" cols="40" rows="3" aria-label="Notes" maxlength="500" aria-invalid="true" aria-describedby="id_notes_error" id="id_notes">aaa…(501 letters)…</textarea>
  ```

With `html=True`, the order of the attributes does not matter. If a Django update changes this, the
tests fail, and the builder copies the new HTML from `TodoForm(data=...)["notes"]` in
`uv run python manage.py shell`.

**The pane.** In the pane's `<dl>`, right after the `Created` row, on **one line**:

```html
      {% if selected.notes %}<dt>Notes</dt><dd class="notes">{{ selected.notes|linebreaksbr }}</dd>{% endif %}
```

**The list rows: no change.**

**The CSS.** Only for the add form (in the list page's styles):

```css
details.add-notes { flex: 0 0 auto; }
details.add-notes[open] { flex: 1 1 100%; }
details.add-notes textarea { display: block; width: 100%; box-sizing: border-box; margin-top: 0.5rem; padding: 0.5rem; font: inherit; resize: vertical; }
```

- The add form is a **flex** row. **Flex** is a CSS layout that puts the items of a box side by
  side, and can let them wrap onto a new line. Closed, the notes box is one short line next to the
  priority box. Open, it takes the whole row, and the Add button moves under it.
- `font: inherit`: a `<textarea>` uses a different font by default; this makes it match the page.
- The pane needs no new CSS (see "Long notes in the pane").

(If feature 4 has already made `base.html` when this one is built, these rules go in the list page's
`{% block style %}`. In the normal order, 4 merges after this one and moves them.)

### 7. `todos/tests/integration/helpers.py` — the shared helpers

Feature 21 made these. This feature **adds to them**; it does not copy them into its own file.

- `pane_element(...)` gets one keyword, `notes=None`. When `notes` is given, the builder puts
  `<dt>Notes</dt><dd class="notes">…</dd>` right after the `Created` row. Inside the `<dd>`, each
  line of `notes` (split on `"\n"`) is escaped with `django.utils.html.escape`, and the lines are
  joined with `<br>`. With `notes=None`, the pane is exactly as before.
- `PageParts` gets two parts, named like 21's pane parts:
  - `pane_notes`: the text inside the pane's `<dd class="notes">`, with each `<br>` as `"\n"`, and
    with HTML codes turned back into characters (`&lt;` becomes `<`). `None` when there is no such
    `<dd>`.
  - `pane_tags`: the names of every element inside the pane `<aside>`, for example
    `["h2", "dl", "dt", "dd", …]`. `[]` when there is no pane.

### 8. `AGENTS.md` — the file table

- `todos/models.py` row: the fields are now `title`, `done`, `due_date`, `priority`, `notes`,
  `created_at`. Notes are at most `NOTES_LIMIT` (500) characters.
- `todos/forms.py` row: the form also has the notes box. `NotesField` counts a line break as one
  character.
- `todos/admin.py` row: the admin uses `NotesField` for the notes.
- Template row: "the add form (the notes box is folded in a `<details>`); the details pane shows the
  notes".
- Rules:
  - "Show text that people typed **only** through Django's escaping. Never use `|safe` or
    `{% autoescape off %}` on it."
  - "No label, summary, `<dt>` or `aria-label` may contain a button's word: Add, Done, Undo, Delete,
    Due date. The CUJ test finds buttons by part of their name."

## For feature 4 (edit)

Feature 4 merges **after** this one, and its `TodoEditForm` is built from `TodoForm`. So the notes
box reaches the edit page by itself. The orchestrator forwards this section to feature 4's planner
and builder.

- On the edit page, the notes box is **not** folded: the person came to change the to-do, so every
  field should be in view. Feature 4 draws every field with a visible label (`Notes:`), which is
  right.
- `NotesField` and the limit come with the form, so the edit page counts line breaks the same way.
- After Save, the person is back on the list with the same pane open (21 keeps `selected`), so they
  see the new notes at once.

**Three tests for feature 4 to add** (in its own integration test file):

| Test | What it does | What it checks | How it fails before feature 4 |
|---|---|---|---|
| `test_edit_changes_the_notes` | a to-do `Buy milk` with notes `Low-fat`; post to its edit page: title `Buy milk`, notes `"Soy\r\nOr oat"` | the saved notes are `"Soy\nOr oat"` | 404: there is no edit page |
| `test_edit_can_empty_the_notes` | the same to-do; post title `Buy milk`, notes `""` | the saved notes are `""` | 404 |
| `test_edit_title_keeps_the_notes` | the same to-do; post title `Buy oat milk`, notes `Low-fat` (as the edit page sends it) | the title changed, the notes are still `Low-fat` | 404 |

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code.

- A **`subTest`** is a smaller case inside one test. If one case fails, the others still run, and
  the report says which case failed.
- Every check on the page is a **whole element** with `assertContains(..., html=True)` (often the
  whole pane, from `pane_element`), a part read by `PageParts`, or the **whole page** compared to
  another whole page with `page_without_csrf`. There are **no** page-wide "not on the page" checks.
- To open the pane, a test opens `/?selected=<pk>`. A small function in `test_notes.py`,
  `pane_for(todo, notes=None)`, calls the shared `pane_element` with that to-do's values (title,
  status, due, priority, created date, `close_url="/"`). It only fills in the keywords; it does not
  copy the helper.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

The **CUJ test** (critical user journey) is the one slow test that uses a real browser, through
Playwright, to do the main things a person does: add, select, Done, Undo, Delete.

**No change.** Notes are optional, and the journey adds a to-do without them. The integration tests
below check notes fully, and fast. It still passes after the change:

- The summary says `Notes (optional)`, with no "Add" in it, so `get_by_role("button", name="Add")`
  still finds only the Add button.
- The to-do in the journey has no notes, so its row and its pane look the same.

### Bottom: unit tests

**`todos/tests/unit/test_models.py`** — add to `TodoModelTests`:

| Test | What it checks | How it fails today |
|---|---|---|
| `test_new_todo_has_empty_notes` | `Todo.objects.create(title="Buy milk").notes` is `""` (not `None`) | `AttributeError`: there is no `notes` yet |
| `test_full_clean_checks_the_notes_limit` | `subTest`s: `Todo(title="Buy milk", notes="a" * 500).full_clean()` passes; with `"a" * 501` it raises `ValidationError` with the key `notes` | `TypeError`: `Todo()` has no `notes` |

**`todos/tests/unit/test_forms.py`** — add a new class, `TodoFormNotesTests`, next to 6's class.
(It uses `TestCase`, because a ModelForm may use the database when it checks itself.) Each test
gives the form a title `Buy milk` and the notes below.

| Test | Notes it gives the form | What it checks | How it fails today |
|---|---|---|---|
| `test_notes_are_optional` | none | the form is valid; `cleaned_data["notes"]` is `""` | `KeyError`: the form has no `notes` |
| `test_notes_are_trimmed` | `subTest`s: `"  Low-fat  "`; `"   "` | `"Low-fat"`; `""` | `KeyError` |
| `test_line_break_becomes_one_character` | `"Low-fat\r\nOr soy"` | `cleaned_data["notes"]` is `"Low-fat\nOr soy"` | `KeyError` |
| `test_notes_limit` | `subTest`s: `"a" * 500` → valid; `"a" * 501` → not valid, error on `notes`; `"a" * 498 + "\r\n" + "a"` (501 characters sent, 500 after the change) → valid | as listed | the 501 case: `AssertionError`, the form is valid because it ignores `notes` |
| `test_notes_box_open` | `subTest`s: a new empty form → `False`; date `not-a-date` and notes `Ring Ana first` → `True`; date `not-a-date` and notes `"   "` → `False`; notes `"a" * 501` → `True` | `form.notes_box_open()` (after `is_valid()` for the bound ones) | `AttributeError`: there is no `notes_box_open` |

**`todos/tests/unit/test_admin.py`** — a new file, one test:

| Test | What it checks | How it fails today |
|---|---|---|
| `test_admin_notes_count_a_line_break_once` | `TodoAdmin(Todo, admin.site).formfield_for_dbfield(Todo._meta.get_field("notes"), request=None)` is a `NotesField` | `ImportError`: there is no `NotesField` yet (the whole file fails as one error, which is expected) |

### Middle: integration tests (`todos/tests/integration/test_notes.py`, new file)

A new file, so it does not clash with features 4 and 10, which change other test files at the same
time.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it posts or does | What it checks | How it fails today |
|---|---|---|---|
| `test_add_a_todo_with_notes` | title `Buy milk`, notes `"Low-fat\r\nOr soy"` | the saved notes are `"Low-fat\nOr soy"` | `AttributeError`: there is no `notes` yet |
| `test_add_a_todo_without_notes` | title only | the to-do is saved, its notes are `""` | `AttributeError` |
| `test_notes_over_the_limit_are_not_added` | title `Buy milk`, notes `"a" * 501` | status 200; nothing is saved; the exact error list and the exact bound-with-error text box (above); the notes box is open (exact `<summary>` inside an open `details`, read with `PageParts`) | today the to-do is saved, and the answer is a redirect (302) |
| `test_list_page_has_a_notes_box` | opens `/` | the exact unbound text box (above), and exactly `<summary>Notes (optional)</summary>` | `AssertionError`: there is no notes box |
| `test_notes_box_is_closed_on_a_new_page` | opens `/` | the `details` with class `add-notes` has no `open` | there is no such `details` |
| `test_bad_date_keeps_the_notes` | `subTest`s, each with title `Buy milk` and date `not-a-date`: notes `Ring Ana first`; notes `"   "` | status 200 and nothing saved in both. First: the exact bound text box with `Ring Ana first`, and the box is open. Second: the box is closed | the page has no notes box |
| `test_pane_shows_notes_with_line_breaks` | `subTest`s: a to-do with notes `"Low-fat\nOr soy"`; one with `"Low-fat\r\nOr soy"` (as old data could have); open `/?selected=<pk>` | the whole pane is exactly `pane_for(todo, notes="Low-fat\nOr soy")` (so the `<dd>` is `Low-fat<br>Or soy`); and `parts.pane_notes` is `"Low-fat\nOr soy"` | `TypeError`: `Todo` has no `notes` to create with |
| `test_pane_notes_are_escaped` | a to-do with notes `<script>alert(1)</script>`; open `/?selected=<pk>` | the whole pane is exactly `pane_for(todo, notes="<script>alert(1)</script>")` (the builder escapes it: `&lt;script&gt;…`); `parts.pane_notes` is exactly `"<script>alert(1)</script>"` (shown as text); `"script"` is **not** in `parts.pane_tags` (no real script element in the pane) | `TypeError` |
| `test_notes_are_not_on_the_list` | a to-do `Buy milk` with notes `Low-fat`; open `/` (nothing selected); then set its notes to `""` and open `/` again | the two whole pages are equal (`page_without_csrf`): notes change nothing on the list | `TypeError` |

**Tests that protect what already works.** These **pass** before the change, and must still pass
after.

| Test | What it checks |
|---|---|
| `test_pane_without_notes_has_no_notes_row` | a to-do `Buy milk` with only a title; open `/?selected=<pk>`: the whole pane is exactly `pane_for(todo)` (no `Notes` row), and `parts.pane_notes` is `None` |

**Deliberate bugs.** A **deliberate bug** is a small mistake the builder makes on purpose, for a
moment, after the code is written, to see a test fail. This proves the test can catch it. Then the
builder puts the code back, and `git diff` must not show the mistake.

| Deliberate bug | The test that must fail |
|---|---|
| remove `{% if selected.notes %}…{% endif %}` around the pane row, so every pane gets an empty `Notes` row | `test_pane_without_notes_has_no_notes_row` |
| write `{{ selected.notes\|safe\|linebreaksbr }}` | `test_pane_notes_are_escaped` (it fails today only because the field is missing; this proves it catches XSS) |
| add `{% if todo.notes %}<p>{{ todo.notes }}</p>{% endif %}` to the list row | `test_notes_are_not_on_the_list` |
| remove the `formfield_overrides` line | `test_admin_notes_count_a_line_break_once` |
| remove the `.replace(...)` in `NotesField.to_python` | `test_line_break_becomes_one_character`, `test_add_a_todo_with_notes` |
| remove `validators=[...]` from the model field | `test_full_clean_checks_the_notes_limit` |

Every test that exists before this change must also still pass (21's pane tests too: `pane_element`
with `notes=None` is unchanged), and the CUJ test with no change.

## Steps, in order

1. Make the branch in its own **worktree** (a second folder for the same git repository, on its own
   branch), from an up-to-date `main` on GitHub, with 6 and 21 in it:

   ```bash
   git fetch origin
   git worktree add -b feature/notes .claude/worktrees/notes origin/main
   ```

   Check that `priority` is in `TodoForm`, and that the pane and `pane_element` are there.
2. Add `notes=None` to `pane_element`, and `pane_notes` and `pane_tags` to `PageParts`, in
   `helpers.py`. Run `make test`: every old test still passes.
3. Write the unit tests and the integration tests. Run `make test`:
   - `test_admin.py` fails with `ImportError` (one error),
   - the two model tests and five form tests fail as listed,
   - the nine integration tests for new behaviour fail as listed,
   - `test_pane_without_notes_has_no_notes_row` passes.

   Show this to the person.
4. Change `models.py`. Run `makemigrations` (it must not ask a question), then `migrate`. Do not
   edit the new migration file.
5. Change `forms.py`, then `admin.py`, then the template (add form, pane row, CSS). `views.py` does
   not change.
6. Run `make test`: every test passes. Run `make test-cuj`: it passes, unchanged.
7. Make each deliberate bug in the table above, one at a time. Each time, the named test fails. Put
   the code back. Check `git diff`.
8. Check the migration on old data: copy a `db.sqlite3` that has to-dos in it, run `migrate` on the
   copy, and check in `uv run python manage.py shell` that every old to-do has `notes == ""`.
9. Run `make run` and open the page:
   - Add a to-do with only a title, by typing and pressing Enter: as fast as before.
   - Open `Notes (optional)`, and add a to-do with two lines of notes. Click its title: the pane
     shows both lines. The list row shows no notes.
   - Type 500 characters with a few line breaks: the browser stops at 500, and Django saves it.
   - **The worst case in the pane:** notes with 500 characters, 20 line breaks and one 200-letter
     word. Select it on a wide window: the pane stays in the window, scrolls inside itself, the long
     word breaks, and the Close link can be reached. Then on a narrow window, like a phone: nothing
     is wider than the screen.
   - Add one with a bad date and some notes: the error shows, the notes box is open, the notes are
     still there.
   - Open `/admin/`, and add notes with line breaks there too.
10. Update `AGENTS.md`.
11. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected".
12. Run `make check`. Commit, including the new migration file.

## Risks

- **Clashes with 4 and 10.** Edit (4) reuses the form and adds an Edit link to the pane; search (10)
  adds the match hint. Both merge after this one, and both plans already expect the notes field and
  the pane row. The merge queue makes this feature's migration again.
- **A future change adds `|safe` to the notes.** Then any visitor could run code in everyone's
  browser. `test_pane_notes_are_escaped` catches it, and the new rule in `AGENTS.md` says why.
- **Saving without a form.** Code that saves a `Todo` without a form (the shell, a future import)
  is checked only if it calls `full_clean()`, like all Django models. Then the model's validator
  rejects notes over 500. Such code could still save `\r\n`; the pane shows it correctly anyway.
- **`formfield_overrides` is for every `TextField` in the admin.** Today notes are the only one. A
  future `TextField` on `Todo` would also count line breaks as one character, which is what we
  want.
- **The pane's CSS is checked only by hand** (step 9). It belongs to feature 21; this feature adds
  no pane CSS.
- **The add form gets one more line.** On a narrow phone, the closed `Notes (optional)` line may
  wrap onto its own row. That is acceptable.
- **Closed owner question.** "Full notes or a preview on the list?" is answered by the owner: notes
  are not on the list at all, only in full in the pane.

## What happened

The builder followed the plan for the parts that do not need 6 (priority) and 21 (details pane).
Those two were still being built, so the branch starts from `main` **without** them. These are the
places where it did something a little different, and why.

1. **The starting point.** `main` had wave 1 only: no `priority`, no pane, no `pane_element`, and
   no `test_forms.py`. So this branch builds now: the model field, `NOTES_LIMIT` and the
   validator; the migration; `NotesField`; the `notes` field in `TodoForm` (fields `title`,
   `due_date`, `notes`, one per line); the folded `Notes (optional)` box with `notes_box_open()`;
   the CSS for the add form; the admin's `formfield_overrides`; and their tests.
2. **Waiting for the rebase on 6 and 21** (the person who rebases does these):
   - the `Notes` row in the pane (the `{% if selected.notes %}…{% endif %}` line);
   - in `helpers.py`: `pane_element(..., notes=None)`, and `pane_notes` and `pane_tags` in
     `PageParts`; and `pane_for()` in `test_notes.py`;
   - the pane tests: `test_pane_shows_notes_with_line_breaks`, `test_pane_notes_are_escaped`,
     `test_notes_are_not_on_the_list`, `test_pane_without_notes_has_no_notes_row`, and their
     deliberate bugs (no `{% if %}`, `|safe`, notes on the row);
   - `"priority"` goes back between `"due_date"` and `"notes"` in `fields`; the notes box goes
     after the priority box;
   - `test_forms.py` is new here, and 6 also makes it: keep both classes;
   - the migration is made again by the merge queue (after 6's migration);
   - `AGENTS.md`: the template row also says "the details pane shows the notes", and the models
     row lists `priority` before `notes`.
   - The three tests for feature 4 (edit) stay in "For feature 4 (edit)": feature 4 adds them.
3. **"The notes box is open" is checked with the whole `<details>` element**, with
   `assertContains(..., html=True)`: the summary, the error list (if any) and the exact text box,
   inside `<details class="add-notes" open>` or `<details class="add-notes">`. This is one exact
   element, so the open and the closed box can not be confused. It needed no new `PageParts` part,
   so `helpers.py` (which 21 changes) is not touched before the rebase.
4. **No real-browser test** (owner decision): the CUJ test was not changed. It still passes.
5. **One more deliberate bug**, not in the plan's table: the template without
   `{% if form.notes_box_open %} open{% endif %}`. `test_bad_date_keeps_the_notes` and
   `test_notes_over_the_limit_are_not_added` failed. It was put back.
6. **Step 9 (look at the page by hand)** was not done by the builder agent: it can not see a
   browser. The CSS for the add form is checked by eye after the rebase, with the pane.

Results:

- **Before the code:** `test_admin.py` failed with one `ImportError` (no `NotesField`); the two
  model tests failed with `AttributeError` / `TypeError` (no `notes`); the five form tests failed
  with `KeyError: 'notes'` or `AttributeError` (no `notes_box_open`), and the 501-character case
  with `AssertionError` (the form ignored `notes`); the six integration tests failed: the to-do
  had no `notes`, the over-the-limit add was saved (302, not 200), and the page had no notes box.
- **Deliberate bugs:** no `formfield_overrides` → `test_admin_notes_count_a_line_break_once`
  failed; no `.replace(...)` → `test_line_break_becomes_one_character`, `test_notes_limit` (the
  line-break case) and `test_add_a_todo_with_notes` failed; no `validators` →
  `test_full_clean_checks_the_notes_limit` failed. Each was put back.
- **The migration on old data:** with three to-dos made before `0003_todo_notes`, `migrate` ran
  with no question, the three to-dos were kept, and every one has `notes == ""`.
  `makemigrations --check` says "No changes detected".
- **After the code:** `make test` (Integration 70, Unit 20), `make test-cuj` (CUJ 1) and
  `make check` all pass.
