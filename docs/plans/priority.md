# Plan: a priority on each to-do (High, Medium, Low)

Status: **done.** Built on branch `feature/priority`. See "What happened" at the end. The owner
approved the second version.

**The owner's answer:** Medium shows **no** label. Only High and Low get a label.

This is feature 6, the first one in wave 2 of [the rollout plan](feature-rollout.md). The merge
order in wave 2 is: **6 priority** → 7 notes → 4 edit → 10 search.

An adversarial review (a reviewer whose job is to find what is wrong) checked the first version,
in Django 5.2.17. Every finding is fixed below.

**Where this starts.** The work starts on `main` **after all of wave 1 is merged**: 5 due date,
12 count, 11 delete completed, 8 filter. So "how it fails today" in the tests means: `main` with
those four features in it. On that `main`:

- `todos/models.py` has `Todo` with `title`, `done`, `due_date`, `created_at`, and
  `objects = TodoQuerySet.as_manager()` (with `remaining()` and `completed()`).
- `todos/forms.py` has `TodoForm`, with the fields `title` and `due_date`.
- `todos/views.py` has `page_context(request, form)`, the **one** place for the page's keys, and
  `list_params` / `list_query` / `back_to_list` for the filter.
- The template draws the add form with `{{ form... }}`. Every `POST` form's `action` ends with
  `{{ list_query }}`. Under the list is `<div class="list-footer">`.
- The migrations end at `0002_todo_due_date.py`.

Feature 7 (notes) is built at the same time. It also adds a field to `TodoForm` and a migration.
It merges **after** this one.

## What we want

Each to-do has a **priority**: how important it is. There are three: **High**, **Medium** and
**Low**. Important to-dos stand out on the list, so a person sees at once what to do first.

## Decisions

### How the priority is stored: a small number, not a word

- The database keeps a **number**: High is `3`, Medium is `2`, Low is `1`. The page and the admin
  show the **word**.
- **Why a number.** Feature 9 (sort, in wave 3) will sort by priority. A database sorts words in
  the order of the alphabet: `high`, `low`, `medium`. That is the wrong order. Numbers sort
  correctly: `3, 2, 1` is High, Medium, Low. So feature 9 writes `order_by("-priority", ...)`. The
  `-` means "biggest first".
- **A bigger number means more important.** So "more important than" is the same as "bigger than",
  in code and in the database.
- Django has a tool for this: **`IntegerChoices`**. It is a list of named numbers, each with a word
  for people. We write `Todo.Priority.HIGH` in code, not the bare number `3`.

### The default is Medium

- A new to-do is **Medium**, unless the person chooses something else.
- **Old to-dos** (already in `db.sqlite3`) also become **Medium**. The migration fills in the
  default by itself.
- Medium is the normal case. "Stand out" only works if most to-dos look normal.

### How it looks on the list

- **High:** a label with the words `High priority`, in **bold**, dark red, on a light red
  background, with a border.
- **Low:** a label with the words `Low priority`, in grey.
- **Medium: no label.** The add form's box says Medium by default; no label means Medium. Medium is
  the normal case, so a label would add only noise. (The owner agreed: Medium shows no label.)
- **Not colour alone.** The meaning is always in the **words**. The colour, the bold and the border
  only help. A person who cannot see colour, and a screen reader (a program that reads the page
  aloud), both get `High priority`.
- We write `High priority`, not only `High`. After the title, a screen reader reads
  "Buy milk, High priority", which is clear. Only "High" would not be clear.
- **Contrast** is how different the text colour is from the background colour. Normal text needs at
  least 4.5 to 1. Dark red `#8b0000` on light red `#fde8e8` is about 8.5 to 1. Grey `#555` on white
  is about 7.5 to 1. The Low label's grey border is only decoration; it carries no meaning.
- A done to-do keeps its label. The title is crossed out as today.

### How it looks in the add form

- A **select** box (a drop-down list) with a visible label, `Priority:`.
- The order is **High, Medium, Low**: the most important first.
- The box starts on **Medium**. We must say this in the form (`initial=`). Django does **not** take
  it from the model's default for a new, empty form. Without it, no option is chosen, and the
  browser sends the **first** option: High.

### A missing or empty priority is Medium

- If the posted form has **no** priority, or an **empty** one, the to-do is saved as **Medium**.
  This keeps old pages and the existing tests working: they post only a title.
- This is true **also when editing** a saved to-do: a missing or empty priority always becomes
  Medium, not the saved value. A test pins this.
- If the priority is **not** one of `3`, `2`, `1` (for example `9` or `high`), the page shows an
  error and **keeps what the person typed**, and nothing is saved. This is the same as a bad date
  (feature 5).

### Ready for "edit" (feature 4)

Feature 4 will use the same `TodoForm` to edit a to-do. A form made from a saved to-do
(`TodoForm(instance=todo)`) shows that to-do's priority as chosen. A test checks this.

**A note for feature 4:** the edit page always posts the select box, so the "missing means Medium"
rule never changes a saved priority by accident in practice. Only a hand-made post without the
field would do that.

### The admin

- The admin's list shows a **Priority** column, with the word, not the number.
- The admin's list has a **filter by priority** on the side (and by done).
- The admin's edit page shows the select box by itself. No code is needed for that.
- An integration test checks the admin's Priority column and its High filter link (added after
  the code review; see "What happened").

## What we will not do (yet)

- **No sorting by priority.** That is feature 9. The list stays oldest first.
- **No changing the priority after adding.** That is feature 4 (edit). The admin can change it.
- **No filter by priority on the page.** The page filter (feature 8) stays All / Active /
  Completed.
- **No more than three levels**, and no "urgent". Adding a level later would need its own plan.
- **No JavaScript.**

## Changes in behaviour

1. The add form has a **Priority** box that starts on Medium. Before, there was none.
2. A to-do is saved with the chosen priority. With no priority, or an empty one, it is Medium.
3. An unknown priority shows an error page, keeps the person's input, and saves nothing. Before,
   the extra value was ignored, and the to-do was saved.
4. The list shows `High priority` or `Low priority` after the title. Medium shows nothing.
5. The admin list has a Priority column and a priority filter.
6. Every old to-do becomes Medium.

What stays the same: a title-only post still adds the to-do and goes back to the list. Add, toggle
and delete still accept `POST` only. The filter, the count and "delete completed" work as before.
The list order does not change.

## The changes, one file at a time

### 1. `todos/models.py` — the model

Inside `class Todo`, at the top, add the three priorities. Right after `due_date`, add the field:

```python
class Todo(models.Model):
    class Priority(models.IntegerChoices):
        HIGH = 3, "High"
        MEDIUM = 2, "Medium"
        LOW = 1, "Low"

    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TodoQuerySet.as_manager()
    ...
```

- `class Priority(models.IntegerChoices)`: the three named numbers. Each line is
  `NAME = number, "word"`.
- We write them **High first**. Django keeps this order for the select box and the admin filter.
- `PositiveSmallIntegerField`: a small whole number, 0 or more. It is enough for 1, 2 and 3.
- `choices=Priority.choices`: only these three numbers are allowed. Django also gives each to-do a
  method `get_priority_display()`, which returns the word, for example `"High"`.
- `default=Priority.MEDIUM`: a new to-do is Medium. The migration uses it for old to-dos too.
- `priority` goes **right after** `due_date`. Feature 7 puts `notes` after `priority`.
- Do not change `TodoQuerySet`, `objects` or `Meta.ordering`.

### 2. The migration

Django makes it from `models.py`. We do not write it by hand, and we never edit it:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

- On our starting point, Django calls it `0003_todo_priority.py`. The number may change: the merge
  queue deletes it and runs `makemigrations` again before it merges (the migration rule).
- It is a normal `AddField` with a default. Django fills `2` (Medium) into every old row by itself.
  So there is **no data migration**, and nothing extra to do when the merge queue makes it again.
- **The guard for the default.** The tests make their database from the migrations, but no test
  reads the default **in the migration file**. If someone changed `default=2` to `default=1`
  there, every test would still pass. `makemigrations --check --dry-run` (part of `make check` and
  CI) catches it: the model says 2 and the migration says 1, so it asks for a new migration and
  fails.
- Commit the migration file.

### 3. `todos/forms.py` — the form

Add one field to `TodoForm`, and add `"priority"` to `fields`. Write `fields` **one name per
line**, with a comma after the last one, so feature 7 adds one line after it:

```python
class TodoForm(forms.ModelForm):
    due_date = ...  # no change

    priority = forms.TypedChoiceField(
        label="Priority",
        choices=Todo.Priority.choices,
        coerce=int,
        required=False,
        empty_value=Todo.Priority.MEDIUM,
        initial=Todo.Priority.MEDIUM,
    )

    class Meta:
        model = Todo
        fields = [
            "title",
            "due_date",
            "priority",
        ]
        widgets = ...  # no change
```

- A **TypedChoiceField** is a form field that allows only values from a list (`choices`), and then
  turns the text from the browser into another type. `coerce=int` turns `"3"` into `3`.
- `initial=Todo.Priority.MEDIUM`: a new, empty form starts on Medium. **This line is needed.**
  Django does not read the model's default for a new form. Without it, the browser would show and
  send High, the first option.
- A form for a saved to-do (`TodoForm(instance=todo)`) starts on **that** to-do's priority. Django
  takes it from the to-do, and it wins over `initial`.
- `required=False` and `empty_value=Todo.Priority.MEDIUM`: a missing or empty priority becomes
  Medium, with no error. This is true for a new to-do and for a saved one.
- A value that is not in the list, like `9` or `high`, gives Django's own error:
  `Select a valid choice. 9 is not one of the available choices.`
- **Why we write the field ourselves.** Django would make a select box from the model by itself,
  but that box would be **required**. Then a post with only a title would fail, and the existing
  tests that post only a title would break.

### 4. `todos/views.py` — no change

`todo_add` already saves the whole form. `page_context` needs no new key: the template reads the
priority from each to-do.

### 5. `todos/templates/todos/todo_list.html` — the page

**The add form.** After `{{ form.due_date }}`, before the Add button:

```html
{{ form.priority.errors }}
{{ form.priority.label_tag }}
{{ form.priority }}
```

`label_tag` writes a visible label, `<label for="id_priority">Priority:</label>`. The form's
`action` does not change: it already ends with `{{ list_query }}`. Feature 7 puts its lines **after**
`{{ form.priority }}`.

**The list.** After the title, and **before** the due date, one rule:

```html
{% if todo.priority != todo.Priority.MEDIUM %}<span class="priority {{ todo.get_priority_display|lower }}">{{ todo.get_priority_display }} priority</span>{% endif %}
```

- For High it writes `<span class="priority high">High priority</span>`. For Low it writes
  `<span class="priority low">Low priority</span>`. For Medium it writes nothing.
- Keep it on **one line**, so the tests can match the whole `<span>` element.
- `todo.Priority.MEDIUM` works in a template: Django marks `IntegerChoices` so the template does
  not try to call it.
- `|lower` makes the CSS class: `High` becomes `high`.

**The CSS:**

```css
form.add select { padding: 0.4rem; font-size: 1rem; }
li .priority { font-size: 0.8rem; padding: 0.1rem 0.4rem; border-radius: 0.25rem; white-space: nowrap; }
li .priority.high { font-weight: bold; color: #8b0000; background: #fde8e8; border: 1px solid #8b0000; }
li .priority.low { color: #555; border: 1px solid #bbb; }
```

- `white-space: nowrap`: the two words of a label stay on one line, even on a phone.

**Layout on a phone.** The add form already wraps (`flex-wrap: wrap`, from feature 5). The second
row now has the date label, the date box, the priority label, the select and the Add button. On a
narrow phone this may become a third row. That is fine. Check it by hand (Steps, below).

### 6. `todos/admin.py` — the admin

```python
@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ["title", "done", "due_date", "priority"]
    list_filter = ["priority", "done"]
```

- `list_display`: the columns in the admin's list. For a field with choices, the admin shows the
  word (`High`), not the number.
- `list_filter`: the filter box on the right side of the admin's list.

### 7. `todos/urls.py` — no change

### 8. `AGENTS.md` — the file table

- `todos/models.py` row: the fields are now `title`, `done`, `due_date`, `priority`,
  `created_at`. Add: "`priority` is a number (High 3, Medium 2, Low 1), so it sorts in the right
  order. Use `Todo.Priority.HIGH`, not `3`."
- `todos/forms.py` row: the form has `title`, `due_date` and `priority`. A missing or empty
  priority is Medium.
- The template row: the list shows `High priority` or `Low priority` after the title.

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

We do **not** add a step: the select box starts on Medium, so the journey works as before (type a
title, pick a date, press Add). We add **one check** to `test_plan_and_finish_a_todo`, right after
the check for `due 12 Oct 2026`:

```python
expect(item).not_to_contain_text("priority")
```

It checks what a person sees: a new to-do is Medium, so its row has no priority label.

- **It passes today**, because there are no labels yet. It guards the default: if the box started
  on High (the bug in the first version of this plan), the row would say `High priority`, and this
  check would fail.
- The CUJ test finds the date box by its label `Due date`. The new label `Priority` does not clash
  with it.

### Bottom: unit tests

**`todos/tests/unit/test_models.py`** — add these to the existing `TodoModelTests` class:

| Test | What it checks | How it fails today |
|---|---|---|
| `test_new_todo_is_medium_priority` | a to-do made with only a title has `priority == Todo.Priority.MEDIUM` | `AttributeError`: `Todo` has no `Priority` yet |
| `test_priority_sorts_high_to_low_in_the_database` | make Low, then High, then Medium. `list(Todo.objects.order_by("-priority"))` is `[high, medium, low]`. This guards the "number, not word" decision for feature 9. | `AttributeError`: `Todo` has no `Priority` yet |

**`todos/tests/unit/test_forms.py`** — a **new file**, with one class, `TodoFormPriorityTests`.
Feature 7 adds its own class to this file when it rebases. These tests use the form directly,
without a request. They use `TestCase`, because a ModelForm checks against the model.

| Test | What it checks | How it fails today |
|---|---|---|
| `test_new_form_starts_on_medium` | `TodoForm()["priority"].value()` is `Todo.Priority.MEDIUM`, and `str(TodoForm()["priority"])` is exactly `<select name="priority" id="id_priority"><option value="3">High</option><option value="2" selected>Medium</option><option value="1">Low</option></select>` (`assertHTMLEqual`). The order is High, Medium, Low. | `AttributeError`: `Todo` has no `Priority` yet |
| `test_each_priority_is_accepted` | `TodoForm({"title": "Buy milk", "priority": v})` for `"3"`, `"2"`, `"1"` (a `subTest` each) is valid, and `cleaned_data["priority"]` is High, Medium, Low | `AttributeError`: `Todo` has no `Priority` yet |
| `test_missing_or_empty_priority_is_medium` | title only, and `priority=""` (a `subTest` each): the form is valid, and `form.save().priority` is Medium | `AttributeError`: `Todo` has no `Priority` yet |
| `test_unknown_priority_is_an_error` | `priority` `"9"`, `"0"`, `"high"` (a `subTest` each): the form is not valid, and `form.errors["priority"]` is `["Select a valid choice. 9 is not one of the available choices."]` (with that value) | `KeyError`: there is no `priority` error, because the form has no `priority` field, and the form is valid |
| `test_form_shows_the_saved_priority` | a saved High to-do: `TodoForm(instance=todo)["priority"].value()` is High. For feature 4 (edit). | `AttributeError`: `Todo` has no `Priority` yet |
| `test_editing_without_priority_makes_it_medium` | a saved High to-do; `TodoForm({"title": "y"}, instance=todo).save()`; reload it: its priority is Medium. This pins the rule "missing means Medium, also when editing". | `AttributeError`: `Todo` has no `Priority` yet |

### Middle: integration tests (`todos/tests/integration/test_priority.py`, new file)

A **new file**, so it does not clash with feature 7. One class, `PriorityTests`. These tests check
the **path**: a request goes in, the page or the redirect comes out. The form rules themselves are
tested in the unit tests above.

Every check on the page matches the **whole element** (`assertContains(..., html=True)`), never a
loose piece of text.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_list_page_has_a_priority_box` | opens `/` | the page has `<label for="id_priority">Priority:</label>`, and exactly the `<select>` from `test_new_form_starts_on_medium`, with Medium `selected` | `assertContains` fails: the page has no priority label |
| `test_add_a_high_priority_todo` | posts title `Buy milk`, `priority` `3` | a redirect to `/` exactly; the saved to-do is High | the redirect check passes; then `AttributeError`: `Todo` has no `Priority` yet |
| `test_unknown_priority_shows_an_error_and_keeps_the_title` | posts title `Buy milk`, `priority` `9` | status 200; nothing is saved; the page has `<li>Select a valid choice. 9 is not one of the available choices.</li>`; the title box still has `Buy milk` (checked the same way as `test_bad_due_date_shows_an_error_and_keeps_the_title`) | status is 302, not 200: today the extra value is ignored, the to-do is saved, and the browser is sent to the list |
| `test_high_label_is_shown_and_medium_has_none` | one High to-do `Call home` and one Medium to-do `Buy milk`; open `/` | `<span class="priority high">High priority</span>` is on the page **exactly once** (`count=1`); `<span class="priority medium">Medium priority</span>` and `<span class="priority low">Low priority</span>` are on the page **zero** times (`count=0`) | `AttributeError`: `Todo` has no `Priority` yet |
| `test_low_label_is_shown` | one Low to-do; open `/` | `<span class="priority low">Low priority</span>`, exactly once | `AttributeError`: `Todo` has no `Priority` yet |

**Tests that protect what already works.** These **pass** before the change, and must still pass
after:

| Test | What it checks |
|---|---|
| `test_title_only_post_still_goes_back_to_the_list` | post title only to `/add/`: a redirect to `/` exactly, and one to-do is saved |

Every test that exists before this change must also still pass, in every level. That includes
`test_add_a_todo`, the filter tests and the count tests, which all post only a title.

### Break it on purpose

Some tests fail today only because the field is missing. That does not prove they catch the real
bug. So, after the code is written, make each bug **for a moment**, see the test fail, and put the
code back. `git diff` must not show a broken line.

| The bug to make | The test that must fail |
|---|---|
| In `forms.py`, delete `initial=Todo.Priority.MEDIUM` (the browser would send High) | `test_new_form_starts_on_medium`, `test_list_page_has_a_priority_box` |
| In `forms.py`, change `required=False` to `required=True` | `test_missing_or_empty_priority_is_medium`, `test_title_only_post_still_goes_back_to_the_list`, and older tests that post only a title |
| In the template, delete the `{% if ... %}` and `{% endif %}`, so every to-do gets a label | `test_high_label_is_shown_and_medium_has_none` (a Medium label appears) |
| In the template, delete `\|lower` (the class becomes `priority High`) | `test_high_label_is_shown_and_medium_has_none`, `test_low_label_is_shown` |

## Steps, in order

1. Make the branch `feature/priority` from the newest `main`, in its own worktree. Write the
   unit tests, the new file `test_forms.py`, the new file `test_priority.py`, and the one
   CUJ check. Run `make test`:
   - the 2 model tests fail with `AttributeError`,
   - the 6 form tests fail as listed,
   - the 5 new-behaviour integration tests fail as listed,
   - the protecting test passes.
   Run `make test-cuj`: it passes (see the CUJ section).
2. Change `models.py`. Run `makemigrations`, then `migrate`. Do not edit the new migration file.
3. Change `forms.py`, then the template, then `admin.py`.
4. Run `make test`, then `make test-cuj`: every test passes.
5. Make each bug from "Break it on purpose", one at a time. See the test fail. Put it back. Check
   `git diff`.
6. **Old data.** Copy a `db.sqlite3` that has to-dos in it, from before this change. Run `migrate`
   on the copy. Open the admin: every old to-do is Medium.
7. **The admin, by hand** (now also covered by an integration test). Log in to `/admin/`. The Todo list has a Priority column that shows the
   word. The filter on the right has High, Medium and Low, and choosing High shows only High
   to-dos. The edit page has a Priority select box.
8. Run `make run` and open the page:
   - The Priority box says Medium.
   - Add one High, one Medium and one Low to-do. High shows a bold label, Low a grey label, Medium
     none.
   - Press Done on the High one: it keeps its label.
   - Try the page on Active and Completed: the labels are the same.
   - Make the window narrow, like a phone: the add form wraps, and nothing goes off the screen.
9. Update `AGENTS.md`.
10. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected".
11. Run `make check`. Commit, including the new migration file.

## Risks

- **Clash with feature 7 (notes).** Both change `models.py`, `fields` in `forms.py`, the add form
  in the template, and `test_forms.py`. This one merges first. To keep the clash small: `notes`
  goes after `priority` in the model, one more line at the end of `fields`, its template lines after
  `{{ form.priority }}`, and its own class in `test_forms.py`. The merge queue makes the migration
  again.
- **The database does not enforce the three values** (accepted). `choices` is checked by the form
  and the admin, not by the database. A `9` saved from a Python shell would be stored, and the
  list would show `9 priority` (with the class `priority 9`). Every way a person changes data
  goes through the form or the admin, so we accept this. A database constraint (a rule the
  database itself checks) can be added later if a new way to write data appears.
- **Feature 4 (edit).** A post to the edit page **without** a priority makes a saved to-do Medium
  (a test pins this rule). The edit page always posts the select box, so this does not happen in
  practice; only a hand-made post would do it. Also, the title box has
  `aria-label="New to-do"` and `autofocus`: a question for feature 4, not for this plan.
- **Feature 4 moves the CSS.** Edit (4) makes `todos/templates/base.html` for the shared CSS. It
  merges after this one, so it moves the four priority CSS rules there with the rest.
- **Feature 9 (sort).** Many to-dos have the same priority. A database may return equal rows in any
  order. So feature 9 must **always** add a tie-breaker after `-priority`, for example
  `order_by("-priority", "created_at")`. Then the list does not jump around when the page loads
  again.
- **Owner decision: no label for Medium.** The owner agreed. If this changes later, the template
  rule loses its `{% if %}`, and one test changes.

## What happened

The builder followed the plan. `main` was the same as the plan expected (`page_context`,
`FILTERS`, `list_params`, `TodoForm` with `title` and `due_date`, migrations ending at `0002`).
These are the places where it did something a little different, and why.

1. **The CUJ check.** The plan says to add the check after `due 12 Oct 2026`. On `main` the CUJ
   test types `2026-10-05`, so the check is after `due 5 Oct 2026`. Same place in the journey.
2. **The select box is in `helpers.py`.** The exact `<select>` is needed by a unit test
   (`test_forms.py`) and an integration test (`test_priority.py`). It is written once, as
   `PRIORITY_SELECT` in `todos/tests/integration/helpers.py`, where shared test parts live.
3. **"The title box still has `Buy milk`"** is checked on the **whole** `<input>` element
   (`html=True`), not on the loose text `value="Buy milk"`, because the conventions ask for whole
   elements.
4. **How the new tests failed first.** All 13 new tests failed because there is no priority yet.
   Some messages were a little different from the plan: `KeyError: 'priority'` (the form has no
   such field) or `'Todo' object has no attribute 'priority'`, instead of `no attribute
   'Priority'`. The reason is the same. The protecting test and the CUJ test passed.
5. **The label is inside `<span class="title">`.** The due date is already inside that span, so
   "after the title, before the due date" means inside it. A done to-do's title has a line
   through it, and that line would also cross out the label. So the label's CSS also has
   `display: inline-block` (a line through the parent does not reach an inline-block child). After
   the code review, a space in the template replaced the first version's `margin-left` (see 9).
6. **Break it on purpose.** All four bugs were caught:
   - no `initial=`: `test_new_form_starts_on_medium` and `test_list_page_has_a_priority_box`
     failed. The CUJ test failed too, because the browser sent High and the row said
     `High priority`.
   - `required=True`: `test_missing_or_empty_priority_is_medium`,
     `test_editing_without_priority_makes_it_medium`,
     `test_title_only_post_still_goes_back_to_the_list`, and 6 older tests that post only a title
     (`test_add_a_todo`, the due-date tests, `test_title_is_trimmed`, `test_add_keeps_the_filter`).
   - no `{% if %}`: `test_high_label_is_shown_and_medium_has_none` (a Medium label appeared).
   - no `|lower`: `test_high_label_is_shown_and_medium_has_none` and `test_low_label_is_shown`.
   Each bug was put back, and the files were compared with the good copies.
7. **Old data.** A database was moved back to `0002`, two to-dos were added with plain SQL, and
   then `migrate` ran `0003_todo_priority`. Both old to-dos have `priority = 2` (Medium), and
   nothing else changed.
8. **Steps 7 and 8 (the admin and the page, by hand in a browser)** were not done by the builder
   agent. The admin is now covered by a test (see 9); the page by the tests, the CUJ test, and a
   screenshot (see 10).
9. **After the code review.** An adversarial code reviewer found no blockers, and these gaps.
   Each new test was seen failing against its own bug, and each bug was put back:
   - **The label is in its own row.** The label tests also match the whole
     `<span class="title">…</span>` of the right to-do. Bug: all labels moved after `</ul>`; both
     label tests failed.
   - **The admin.** New test `test_admin_list_has_a_priority_column_and_filter` (a superuser,
     `force_login`, the admin list page): it finds `<td class="field-priority">High</td>` and
     `<a href="?priority__exact=3">High</a>`. Bugs: `priority` taken out of `list_display`, then out
     of `list_filter`; the test failed each time.
   - **The choice is kept after an error.** New test `test_error_page_keeps_the_chosen_priority`:
     a bad date with Low chosen gives back the whole select with Low `selected`. Bug: a
     hand-written select that always says Medium; the test failed.
   - **A space before the label.** The text read `Pay rentHigh priority`. Now the template has a
     space before the label, and the label's `margin-left` is gone (the space makes the gap). A
     new CUJ test, `test_a_high_priority_todo_stands_out_until_it_is_done`, checks the title's text
     is `Pay rent High priority`. It failed before the fix.
   - **A done label fades.** New CSS `li.done .priority { opacity: 0.6; }`, so a finished High
     to-do does not stand out more than open ones. The words stay. The same CUJ test checks the
     opacity is `1`, then `0.6` after Done. Bug: the rule taken out; it failed.
   - **The label is not crossed out on a done row.** The reviewer asked to check the label's
     computed `text-decoration-line` is `none`. That check can never fail: `text-decoration` is
     not inherited, so the label's own value is `none` even when the title's line is drawn
     through it (a small browser script showed `none` for both `inline` and `inline-block`). So
     the CUJ test instead walks up from the label: if the label and its parents up to the first
     non-inline box have no `line-through`, the line does not reach it. Bug: `display: inline`;
     the test failed with `True is not false`.
   - **The CUJ's Medium check** is now `expect(item.locator(".priority")).to_have_count(0)`.
     Bug: no `{% if %}`, so Medium gets a label; the first journey failed.
   - **The migration default.** Bug: `default=1` in the migration file for a moment.
     `makemigrations --check --dry-run` wanted a new migration (`0004_alter_todo_priority`) and
     exited with code 1. See "The guard for the default" in section 2.
   - **Risks** now say that the database does not enforce the three values (accepted), and that
     an edit post without a priority makes it Medium.
   - **A CUJ run that was not explained.** Once, right after the template change, the first
     journey ended with an error. The message was not saved. The next 16 runs in a row passed.
     (Later the owner removed the real browser; see 10.)
10. **Rebased on `main` without a real browser.** The owner decided: no real-browser tests. Main
    (`8c39353`) removed Playwright, and the journeys now use Django's test client with the
    `page_forms` helper. So, on the rebase:
    - The browser commit (the Playwright journey for priority) was dropped. Its checks moved into
      the test-client journeys in `todos/tests/cuj/test_journeys.py`:
      - `test_plan_and_finish_a_todo`: the person types no priority, so `page_forms` sends the
        option the page selected. The new row has **no** label, which proves the box starts on
        Medium. Bug: no `initial=`, so the page selects nothing and sends High; the journey failed.
      - `test_a_high_priority_todo_keeps_its_label_when_done` (new): choose priority `3`, and the
        row is exactly the row with `<span class="priority high">High priority</span>` in its
        title. After Done, the row is done and keeps the label. Bug: all labels moved after
        `</ul>`; this journey failed.
    - **The space before the label** was checked by the browser's text. `html=True` ignores
      spaces, so `test_high_label_is_shown_and_medium_has_none` now also checks the exact text
      `Call home <span class="priority high">High priority</span>` (without `html=True`). Bug: no
      space; the test failed.
    - **Checked by eye, not by a test** (only a browser can draw them; both CSS rules stay):
      on a done row the label is **not** crossed out (`display: inline-block`), and it is
      **faded** (`li.done .priority { opacity: 0.6; }`). The screenshot
      [priority-labels.png](priority-labels.png) shows the real page with two open to-dos (Pay
      rent High, Buy milk Medium) and two done ones (Call the bank High, Water the plants Low).
      The done titles are crossed out, and their labels are not, and look lighter.
    - **Seen in the screenshot, not fixed here:** at this width, `Priority:` ends one row of the
      add form and its select box starts the next. The label still points at its box (`for=`), so
      it works, but it looks split. A small layout fix (keep the label and the box together) could
      go with feature 4, which moves the CSS to `base.html`.
    - The migration is still `0003_todo_priority`: `main` has only `0001` and `0002`.
      `makemigrations --check --dry-run` says "No changes detected".
