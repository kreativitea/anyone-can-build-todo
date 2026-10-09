# Plan: a due date on each to-do

Status: **done**. See "What happened" at the end. It was built after [the test-pyramid
plan](test-pyramid.md), and its tests are in the folders that plan made.

This is the second version of the plan. The first version was checked by an adversarial review (a
reviewer whose job is to find what is wrong). Every finding is fixed below.

## What we want

Each to-do can have a **due date**: the day it should be finished. The date is **optional**. A
person can still add a to-do with only a title, like today.

## Decisions

- **Date on the list:** shown as `due 12 Oct 2026`.
- **A bad date** (or any other mistake in the form): the page shows an error, and **keeps what the
  person typed**, so nothing is lost. Nothing is saved until the form is correct.
- **Past dates are allowed.** A person may add a to-do that is already late.
- **Typed dates must look like `2026-10-12`.** Almost every browser shows a date picker, which sends
  this form by itself. If a browser shows a plain text box instead, Django would read `12/10/2026` in
  the US way, as 10 December, which is wrong for someone in Japan or the UK. Accepting only
  `2026-10-12` stops that mistake.

## What we will not do (yet)

- No time of day — only a date.
- No editing the due date after the to-do is added. (Today there is no "edit" page at all.)
- No sorting by due date, and no "overdue" colour. A note for later: to know what "today" is, use
  `django.utils.timezone.localdate()`, not `date.today()`. Our time zone is `Asia/Tokyo`, and a
  server that runs in UTC would be wrong for 9 hours each day.

## Changes in behaviour

Changing the add view to a Django form changes three things. The tests below cover each one.

1. A bad date shows an error page. Before, there was no date, so there was nothing to get wrong.
2. A title longer than 200 characters is **rejected with an error**. Before, it was saved, because
   SQLite does not check the length. (The browser's own limit of 200 already stops most people.)
3. Any error shows a message. Before, an empty title was dropped with no message.

What stays the same: spaces around a title are removed, a title of only spaces is not added,
add/toggle/delete accept `POST` only, and a good form sends the browser back to the list.

## The changes, one file at a time

### 1. `todos/models.py` — the model

Add one field to `Todo`:

```python
due_date = models.DateField(null=True, blank=True)
```

- `DateField` stores a date (year, month, day), with no time.
- `null=True` lets the database keep "no date".
- `blank=True` lets a form accept an empty date. Together, these two make the date optional.

### 2. `todos/migrations/0002_todo_due_date.py` — the migration

A **migration** is a small file that tells the database how to change its tables. We do not write
it by hand, and we never edit it. Django makes it from `models.py`:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

Old to-dos in `db.sqlite3` are safe: they get "no date". The new migration file **is** committed to
git.

### 3. `todos/forms.py` — a new file, the form

A **ModelForm** is a form that Django builds from the model. It checks the input for us:

```python
from django import forms

from .models import Todo


class TodoForm(forms.ModelForm):
    due_date = forms.DateField(
        label="Due date (optional)",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Todo
        fields = ["title", "due_date"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "aria-label": "New to-do",
                    "placeholder": "What needs doing?",
                    "autofocus": True,
                }
            ),
        }
```

- `required=False`: an empty date is fine.
- `input_formats=["%Y-%m-%d"]`: only `2026-10-12` is accepted (see Decisions).
- `type="date"`: the browser shows its own date picker.
- Django adds `maxlength="200"` and `required` to the title box by itself, from the model.
- The title: spaces around it are removed, and only spaces counts as empty.

### 4. `todos/views.py` — the views

Both views now give the page a form. If the form has errors, `todo_add` shows the page again with
the errors and the person's input, instead of sending them away:

```python
def todo_list(request):
    return render(
        request,
        "todos/todo_list.html",
        {"todos": Todo.objects.all(), "form": TodoForm()},
    )


@require_POST
def todo_add(request):
    form = TodoForm(request.POST)
    if form.is_valid():
        form.save()
        return redirect("todo_list")
    return render(
        request,
        "todos/todo_list.html",
        {"todos": Todo.objects.all(), "form": form},
    )
```

This is the standard Django way to handle a form. It still accepts `POST` only.

### 5. `todos/templates/todos/todo_list.html` — the page

**The add form** is now drawn by Django from `TodoForm`, instead of written by hand. This is how
the date picker from step 3 reaches the page:

```html
<form class="add" method="post" action="{% url 'todo_add' %}">
  {% csrf_token %}
  {{ form.non_field_errors }}
  {{ form.title.errors }}
  {{ form.title }}
  {{ form.due_date.errors }}
  {{ form.due_date.label_tag }}
  {{ form.due_date }}
  <button type="submit">Add</button>
</form>
```

- `label_tag` writes a **visible** label, `<label for="id_due_date">Due date (optional):</label>`. A
  date box shows no hint text, so without a label nobody can tell what it is for.
- The browser still checks the form first (title required, at most 200 characters). Django checks
  it again on the server, because a browser's checks can be skipped.

**The list:** after the title, show the date only if there is one:

```html
{% if todo.due_date %}<span class="due">due {{ todo.due_date|date:"j M Y" }}</span>{% endif %}
```

Without `"j M Y"`, Django would show `Oct. 12, 2026`.

**Layout on a phone:** the title box, the label, the date box and the button do not fit in one row.

- Add `flex-wrap: wrap` to `form.add`, so the row can break.
- The title box takes the whole first row: `flex: 1 1 100%`. (Change the CSS rule from
  `form.add input` to `form.add input[name=title]`, so the date box does not stretch too.)
- The label, the date box and the button share the second row.
- Error messages get a red colour, so they are easy to see.

### 6. `todos/admin.py` — the admin (optional)

`Todo` is already in the admin, so the date box appears on its edit page by itself. To show the
date as a column in the admin's list too, `admin.site.register(Todo)` must become a small class:

```python
@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ["title", "done", "due_date"]
```

(`list_display` cannot be passed to `register()` directly.) This step is nice to have, not needed.

### 7. `AGENTS.md` — the file table

- `todos/models.py` row: the fields are now `title`, `done`, `due_date`, `created_at`.
- `todos/views.py` row: if the add form has errors, the page is shown again with the errors.
- A new row: `todos/forms.py` — the add form, built from the model.
- The template row: the add form is drawn by Django.

The README does not list fields, so it does not change.

## Tests (`todos/tests/`)

We write all of these **first** and run them **before** changing the code. They go into the three
levels from [the test-pyramid plan](test-pyramid.md).

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

We change the one journey, `test_plan_and_finish_a_todo`. We do not add a new one, because adding a
to-do with a date is the same journey with one more step:

- In step 2, also fill the date box with `2026-10-12` before pressing Add.
- Then check the list shows `due 12 Oct 2026`.

How it fails today: there is no date box, so Playwright cannot find it to fill it.

### Bottom: a unit test (`todos/tests/unit/test_models.py`)

| Test | What it checks | How it fails today |
|---|---|---|
| `test_new_todo_has_no_due_date` | a new to-do's `due_date` is `None` | `AttributeError`: there is no `due_date` yet |

### Middle: integration tests (`todos/tests/integration/test_views.py`)

The form rules are tested here, through a request with Django's test client. It is fast, and it
checks the whole path a person uses.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it posts or does | What it checks | How it fails today |
|---|---|---|---|
| `test_add_a_todo_with_a_due_date` | title `Buy milk`, date `2026-10-12` | the saved date is 12 Oct 2026 | `AttributeError`: there is no `due_date` yet |
| `test_add_a_todo_without_a_due_date` | title only | the to-do is saved, its date is `None` | `AttributeError`: there is no `due_date` yet |
| `test_bad_due_date_is_not_added` | title `Buy milk`, date `not-a-date` | nothing is saved | today the to-do is saved (count is 1) |
| `test_bad_due_date_shows_an_error_and_keeps_the_title` | same as above | status 200, the page says `Enter a valid date.`, and the title box still has `Buy milk` | today the answer is a redirect (302) |
| `test_us_style_date_is_not_accepted` | title `Buy milk`, date `12/10/2026` | nothing is saved | today the to-do is saved |
| `test_title_over_200_chars_is_not_added` | a title of 201 letters | nothing is saved | today it is saved |
| `test_list_page_has_a_date_box` | opens the list | the page has `type="date"` | the page has no date box yet |
| `test_due_date_is_shown_on_the_list` | a to-do with date 12 Oct 2026 | the page says exactly `due 12 Oct 2026` | `TypeError`: there is no `due_date` yet |

The first two fail because the field is missing, not because of a wrong answer. That is expected:
it shows the tests are looking for something that does not exist yet.

**Tests that protect what already works.** These **pass** before the change, and must still pass
after. They make sure the switch to a Django form does not break anything:

| Test | What it checks |
|---|---|
| `test_title_is_trimmed` | posting `"  Buy milk  "` saves `"Buy milk"` |
| `test_no_due_date_shows_no_due_text` | a to-do without a date: the page does not contain `due ` |

Every test that exists before this change must also still pass — especially
`test_empty_title_is_not_added`.

## Steps, in order

1. Write the new tests and change the CUJ test. Run `make test`: the unit test and the eight
   integration tests for new behaviour fail with the errors listed, and the two protecting tests
   pass. Run `make test-cuj`: the CUJ test fails, because it cannot find the date box.
2. Change `models.py`. Run `makemigrations`, then `migrate`. Do not edit the new migration file.
3. Add `forms.py`. Change `views.py`, then the template. Then, if we want it, the admin.
4. Run `make test`, then `make test-cuj`: every test passes.
5. Run `make run` and open the page. Add one to-do with a date and one without. Then make the window
   narrow, like a phone, and check that the form still fits.
6. Update `AGENTS.md`.
7. Run `uv run python manage.py makemigrations --check --dry-run`. It should say "No changes
   detected", which means no migration is missing.
8. Run `make check`. Commit, including `todos/migrations/0002_todo_due_date.py`.

## What happened

The tests were written first and committed alone. Before the code changed, `make test` showed
`Integration: 10 passed, 5 failed, 3 errors` and `Unit: 3 passed, 1 error`. Every new test failed
for the reason in the tables above, and the two protecting tests passed. `make test-cuj` failed
because Playwright could not find the "Due date" box. After the code: `Unit: 4 passed`,
`Integration: 18 passed`, `CUJ: 1 passed`, and `makemigrations --check --dry-run` said "No changes
detected". Django wrote `0002_todo_due_date.py`; nobody edited it.

Differences from the plan:

- **One helper for the page's data.** The orchestrator asked for this after the plan was approved.
  `views.py` has a small function, `page_context(request, form)`, that returns what the page needs,
  one key per line. It takes `request` but does not use it yet: the filter feature needs it next.
  Both `todo_list` and the error path of `todo_add` use it. About 15 later features add a key to
  the page, so each one now adds **one line in one place**, not two, and two branches are less
  likely to change the same line. The behaviour does not change, so no test was added. AGENTS.md
  says every key the list page needs goes in `page_context`.
- **`test_no_due_date_shows_no_due_text` looks for the element, `class="due"`, not the text
  `due `.** The page's CSS has the rule `li .due { ... }`, which contains `due ` too, so the plan's
  check would fail for the wrong reason. (A first try, `>due `, depended on spaces in the template,
  and the code review showed a bug that it missed.)
- **The error list had a line under it.** Django draws errors as a `<ul class="errorlist">` with
  `<li>` items, so the page's own `li` rule (padding and a bottom border) hit them. A rule
  `.errorlist li { padding: 0; border: 0; }` stops that.
- **On a narrow phone (375 px), the Add button goes to a third row.** The label, the date box and
  the button need about 10 px more than the row has. Everything still fits on the screen, with no
  sideways scrolling, so we left it. (In a flex row that wraps, a box moves to the next row before
  it shrinks, so making the date box "shrink if needed" does not help.) At 800 px, the label, date
  box and button share the second row, as planned.
- The plan's optional admin step (step 6) was done: the admin list shows the due date as a column.
- A small grey style for the date in the list (`li .due`) was added, so it reads as extra detail.
- The visual check (step 5) used a screenshot of the page at 375 px and 800 px, with a bad date,
  instead of `make run` by hand.

### After the code review

An adversarial code reviewer checked the branch. Its findings were fixed in new commits, without
changing the earlier ones:

- **Phone layout.** At 320 px, a long title was squeezed to one word per line, and the date broke
  over two lines. The date is now a `<small class="due">` **inside** the title, on its own line
  (`display: block`), and the title may break inside a very long word (`overflow-wrap: anywhere`).
  Checked with a 320 px screenshot. Note for later features: the title's text now ends with the
  date, so a test that matches the title text *exactly* must allow for it.
- **Stronger tests.** The date in the tests and the CUJ is now **5 Oct**, a day with one digit, so
  the wrong date format (`d`, which gives `05`) is caught. New tests: the error page still shows the
  list; an empty title shows "This field is required."; a past date (1 Jan 2000) is allowed. The
  over-200 test now also checks the error message. The date box is checked as a whole `<input>`.
- **Each new test was shown failing against a deliberate bug** (put back afterwards): always
  showing the date; the format `d M Y`; an empty list on the error page; deleting the title's
  errors from the template; rejecting dates before 2020; a date box without `type="date"`.

After the fixes: `Unit: 4 passed`, `Integration: 21 passed`, `CUJ: 1 passed`.

## Risks

- **The error page is shown at `/add/`.** When the form has errors, the browser's address bar shows
  `/add/`. Reloading that page sends the form again (the browser asks first), and opening `/add/`
  directly gives `405 Method Not Allowed`, because it accepts `POST` only. We accept this: it is the
  standard Django way, and nothing is saved until the form is correct.
