# Plan: repeating to-dos (feature 19)

Status: **approved**, with the owner's answers (below). Being built on `feature/repeating`.

## The owner's answers

1. **Undo keeps an edited copy.** Yes (as planned).
2. **Monthly: the last day stays the last day.** Yes (as planned).
3. **No catching up.** Yes. But the person must be able to **change the new copy's due date** on its
   edit page, like any field. It is: `due_date` is a normal field of `TodoForm`. A test checks it
   (`test_edit_the_copys_due_date`).
4. **Subtasks are copied** to the next copy, all set to **not done**. Feature 15 merges after this
   one, so 15 adds the copying (see "Subtasks (feature 15)").
5. **The admin's "done" makes no copy.** Yes (as planned).

There is **no production data** yet (CONVENTIONS): nobody uses the live site. So nothing special
is done for old rows; the migration Django makes is enough.

The first version was checked by an adversarial review (a reviewer whose job is to find what is
wrong), on a scratch copy with Django 5.2.17. Every finding is fixed below. The biggest change:
Done and Undo now post the state the person **wants**, instead of "flip it".

This is feature 19, in wave 3 of [the rollout plan](feature-rollout.md). The merge order in wave 3
is: 9 sort → **19 repeating** → 15 subtasks. Branch: `feature/repeating`.

**Where this starts.** The work starts on `main` **after waves 1 and 2 are merged**: 5 due date,
12 count, 11 delete completed, 8 filter, 6 priority, 7 notes, 4 edit, 10 search. So "how it fails
today" in the tests means: `main` with those eight features in it. On that `main`:

- `Todo` has `title`, `due_date`, `priority`, `notes`, `done`, `created_at`, and
  `objects = TodoQuerySet.as_manager()` (with `remaining()` and `completed()`).
- `TodoForm` (in `forms.py`) has `title`, `due_date`, `priority`, `notes`. `TodoEditForm` is a
  subclass of it, so the edit page shows every field of `TodoForm`.
- `views.py` has `page_context(request, form)`, `list_params`, `list_query`, `back_to_list`.
- `todo_toggle` **flips** `done` (`todo.done = not todo.done`) and saves.

Feature 9 (sort) is built at the same time and merges **before** this one. It changes how the list
is read, not the toggle, so the two touch different lines. Feature 15 (subtasks) merges
**after** this one; it must add one line here (see Undo).

## What we want

A to-do can **repeat**: every day, every week, or every month. Example: "Take out the rubbish",
due Monday 12 Oct, every week.

When the person presses **Done** on a repeating to-do:

- that to-do becomes **Completed**, like today, and stays on the list as history;
- a **new to-do** appears: the same title, notes, priority and repeat, with the **next** due date
  (Monday 19 Oct).

So the person never has to type a repeating job again.

## Decisions

### A `repeat` field with four choices

- The database keeps a short word: `none`, `daily`, `weekly`, `monthly`. The page shows
  `Does not repeat`, `Every day`, `Every week`, `Every month`.
- The default is `none`. A to-do already in a laptop's `db.sqlite3` gets `none` from the migration.
  There is no production data, so nothing more is needed.
- It goes into the one `TodoForm`. So the **add** form and the **edit** page (feature 4) both have
  it, with no more work.
- Why words and not numbers (priority uses numbers)? Priority needs an order, for sorting. Repeat
  has no order, and a word is easier to read in the database and the admin.

### Done makes a **new** to-do; it does not move the date of the old one

| | Make a new to-do (**chosen**) | Move the same to-do's date forward |
|---|---|---|
| History | the done one stays, so you can see you did it | lost: the to-do is never "Completed" |
| "Delete completed" (11) | works as it is: history goes, the next one stays | nothing to delete |
| Count (12), filter (8) | work as they are | work |
| Undo | must handle the new copy (see below) | must move the date back |

We choose **a new to-do**. It keeps history and fits every feature we already have.

The new to-do copies: `title`, `notes`, `priority`, `repeat`. It gets the next due date. It is not
done. `created_at` is new (Django sets it). Later, when lists (13) exist, the copy goes into the
**original's current list** (13 adds that line; a test makes it, see Tests).

### Done and Undo post the state the person **wants** (changes every to-do)

Today the Done/Undo button says "flip it". The review proved this is wrong for repeating to-dos:
a **double click**, or Done pressed in an **old tab** (a page opened before someone else already
pressed Done), sends a second "flip". The second flip is an Undo, and Undo deletes the new copy.
The person pressed Done twice and ends with **nothing done**.

So each button now says what it wants:

- The Done button sends a hidden field `done=1`. The Undo button sends `done=0`.
- Any other value, or no value, gets **400** ("bad request": the server will not do something it
  does not understand). Django's `HttpResponseBadRequest` gives this.
- If the to-do is **already** in the wanted state, nothing happens, and the browser goes back to
  the list. So Done twice = Done once. Undo on an open to-do = nothing.
- The address and its name stay the same (`/<id>/toggle/`, `todo_toggle`), so other branches do not
  collide here.

This changes the button for **every** to-do, not only repeating ones: a stale Done no longer flips a
completed to-do back to open. See "Changes in behaviour".

### Two requests at once never make two copies

If two requests ask for Done at the same moment (two tabs, two people — everyone sees one list),
both could read "not done", and both could make a copy. We stop it inside one **transaction** (a
group of database changes that all happen, or none happen):

1. **Claim the change.** `Todo.objects.filter(pk=pk, done=not target).update(done=target)`. The
   database does this in one step, and returns how many rows it changed.
2. If it changed **0** rows, the to-do is already in the wanted state (another request was first).
   We do **nothing more**.
3. Only the request that changed **1** row goes on: it reads the row again (fresh), then makes the
   next copy (Done) or maybe deletes it (Undo), and saves the link.

This works on SQLite (our database) and on PostgreSQL, with no locks to set by hand. The logic is
one model method, `Todo.set_done(target)`. The view only calls it.

### The next due date: counted from the **due date**, not from today

- **Daily:** one day after the due date. **Weekly:** seven days after.
- **Monthly:** the same day number, one month later, with two rules:
  - **The last day stays the last day.** If the due date is the last day of its month, the next
    one is the last day of the next month. 31 Jan → 28 Feb → 31 Mar → 30 Apr → 31 May. So "the end
    of every month" works, with no new field.
  - **Too short a month:** otherwise, if the next month does not have that day, use its last day.
    (This only happens for 29, 30, 31 in front of a short month, and those are already covered by
    the first rule, except 29 and 30 Jan → 28 Feb.)
- **What still moves (accepted):** a day that **happens** to be the last day is treated as "end of
  month". 30 Jan 2027 → 28 Feb 2027 → **31 Mar**. 30 Apr → **31 May**. 28 Feb 2027 (a 28th in a
  year that is not a leap year) → **31 Mar**. The person can fix the date once with Edit. Fixing it
  for good needs an "anchor day" field, which Edit must also keep right; we do not do that now.
- Why from the due date: a to-do due Monday that is done on Tuesday should still come back on
  Monday. Counting from today would slowly move the day.
- The date math is a **pure function** — a function that only takes values and gives back a value,
  and does not read the database or the clock. So it is easy to test with many dates. It lives in a
  new file, `todos/repeat.py`: `next_due_date(due, repeat)`.
- It uses only Python's own `datetime` and `calendar.monthrange` (which tells how many days a month
  has, and knows leap years). **No new package.**

### A repeating to-do **needs** a due date

- Without a date, "the next date" means nothing. So if `repeat` is not `none` and there is no due
  date, the form shows an error **under the "Repeats" box**: "A repeating to-do needs a due date."
  Nothing is saved. The person's input is kept (as for every form error since feature 5).
- The check is in `Todo.clean()` on the model, not only in the form. A **ModelForm** (a form Django
  builds from the model) calls the model's `clean()` by itself, so the add form, the edit page
  **and** the admin all get the same check, from one place.
- **A rule for later forms:** the error is tied to the field `repeat`. If a future `Todo` ModelForm
  leaves out `repeat`, Django cannot put the error anywhere and raises `ValueError` (a crash). So
  **every `Todo` ModelForm must include `repeat`** — or `clean()` must change to a non-field error
  (an error shown at the top of the form). This goes into `AGENTS.md`.
- If a to-do still has no date (for example, made in the Django shell), Done uses **today**
  (`timezone.localdate()`, in Tokyo time) as the start. It never crashes.

### Undo deletes the copy only when it is safe

**Undo** reopens the to-do. If Done made a next copy, Undo deletes that copy **only if all of these
are true**:

1. the copy is still **open** (not completed);
2. the copy has **no next copy of its own** (`next_todo` is empty);
3. the copy is **untouched**: its copied fields (`title`, `notes`, `priority`, `repeat`,
   `due_date`) still equal what `next_copy()` of the reopened to-do gives now;
4. (added by feature 15) the copy's **subtasks are untouched**: exactly the ones Done copied — the
   same titles, in the same order, all not done. A copy whose subtasks the person ticked, renamed,
   added or deleted is kept.

Otherwise the copy **and the link are kept**. Because the link is kept, pressing Done on the
reopened to-do again makes **no** new copy.

| Case | What Undo does |
|---|---|
| Done by mistake, Undo at once | copy deleted; the list is as before Done |
| The person **edited** the copy, then Undo on the old one | copy kept (their edit is not lost); two open to-dos, which the person can see |
| Chain: Done Monday, Done Tuesday (its copy), then Undo Monday | Tuesday is completed → kept; Wednesday stays; Monday is open again |
| The copy was deleted by hand | nothing to delete; Monday is open; Done again makes a fresh copy |

This is the simplest rule that never deletes anything the person worked on.

### Each to-do remembers its next copy: `next_todo`

- A new field: `next_todo`, a link to the to-do that Done made from this one.
- It is a **OneToOneField** (a link where each target belongs to at most one row) to `Todo` itself,
  `null=True`, `on_delete=SET_NULL`: if the next copy is deleted, the link becomes empty, and the
  old to-do is not touched.
- `related_name="+"`: we never need to go from the copy back to the old one, so Django makes no
  reverse name.
- `editable=False`: it never appears in a form or the admin. This matters: feature 4 has a unit test
  that says "the edit form has every model field that is editable, except `done`". With
  `editable=False`, that test stays true without a change.

### Subtasks (feature 15)

Feature 15 merges **after** this one, so this branch has no subtasks. The owner decided that
subtasks **are copied**. Feature 15 adds, in `models.py`:

- In `set_done`, right after `copy.save()`: one `bulk_create` (one query for all of them) of new
  subtasks on the copy, one for each subtask of the original, in the same order, with the same
  title and `done=False`.
- A method `has_untouched_subtasks_of(original)`: true when the copy's subtasks, as a list of
  `(title, done)` in order, equal `[(title, False)` for each subtask of the original`]`. It is added
  to the Undo rule (rule 4 above). So a copy with exactly the copied, untouched subtasks still counts
  as untouched and is deleted by Undo; a copy whose subtasks the person changed is kept.
- Tests in 15: Done copies the subtasks, all not done; Undo deletes a copy with untouched subtasks
  (and its subtasks); Undo keeps a copy after one of its subtasks was ticked; the field-copy test
  still passes (subtasks are another table, not a field).
- 15 also updates `test_delete_completed_does_not_load_each_todo` for its own queries.

### On the list and in the add form

- **Add form:** a select box (a drop-down list) with a visible label `Repeats:`, after Notes. It
  starts on `Does not repeat`.
- **List:** an open repeating to-do shows `<span class="repeat">Every week</span>` after the due
  date. A **completed** one does not show it: history does not repeat any more, its next copy does.
- Done and Undo buttons each get one hidden input. No JavaScript.

## What we will not do (yet)

- No "every 2 weeks", no weekdays only, no yearly, no end date. Four choices only.
- **No catching up.** A daily to-do due 1 Oct, done on 9 Oct, comes back due 2 Oct (already late).
  A later option: **step forward** with `next_due_date` again and again until the date is today or
  later (so a weekly Monday to-do stays on Mondays). Not `max(next, today)`, because that would
  move a weekly Monday to-do to another weekday.
- **No anchor day** for monthly (see the date rules).
- Marking a to-do done **in the admin** makes no next copy. Only the Done button does.
- Changing `repeat` on an already completed to-do (with Edit) makes no copy. Only Done does.
- Editing a copy (its due date, title, anything) never makes or deletes a to-do. Only Done and Undo
  do. So a person who does not want the "no catch-up" date simply edits the copy's due date.
- No "stop this series" button. To stop, the person edits the open copy to `Does not repeat`, or
  deletes it.

## Changes in behaviour

1. **Done and Undo, for every to-do.** The buttons post `done=1` or `done=0`. A second Done (double
   click, old tab) does **nothing**; before, it flipped the to-do back to open. A post without
   `done`, or with another value, gets **400**; before, any post flipped.
2. The add form and the edit page have a **Repeats** box. Before, there was none.
3. A to-do with a repeat but no due date is **rejected** with an error.
4. **Done** on a repeating to-do also makes the next to-do. Done on a non-repeating to-do: no
   other change.
5. **Undo** on a repeating to-do deletes its next copy if that copy is still open, has no next copy
   and was not changed.
6. **A post without `repeat` sets it to `none`.** This is true for add **and** edit: the field is
   `required=False` with `empty_value="none"`, so a missing value becomes `none`, and Django saves
   it. (It does **not** keep the saved value. Priority works the same way: missing → Medium.) The
   page always sends the select, so a person never sees this.

What stays the same: Done and Undo accept `POST` only, they go back to the same list view
(`back_to_list`), a to-do that does not exist gives 404, a form with only a title still works
(repeat is `none`).

## The changes, one file at a time

### 1. `todos/repeat.py` — new file, the date math

```python
import calendar
from datetime import date, timedelta

NONE = "none"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"


def days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def next_due_date(due: date, repeat: str) -> date:
    """The due date of the next copy, counted from this due date.

    Monthly keeps the day number. The last day of a month goes to the last day of the next
    month. If the next month is too short, it uses its last day.
    """
    if repeat == DAILY:
        return due + timedelta(days=1)
    if repeat == WEEKLY:
        return due + timedelta(days=7)
    if repeat == MONTHLY:
        year, month = (due.year + 1, 1) if due.month == 12 else (due.year, due.month + 1)
        last = days_in_month(year, month)
        if due.day == days_in_month(due.year, due.month):
            return date(year, month, last)
        return date(year, month, min(due.day, last))
    raise ValueError(f"Not a repeat: {repeat!r}")
```

- `calendar.monthrange(year, month)[1]` is the number of days in that month (28, 29, 30 or 31).
- `none` or an unknown word is a **programming mistake**, so it raises `ValueError` instead of
  guessing.
- The four words are kept here, and the model's choices use them, so there is one spelling.

### 2. `todos/models.py` — two fields, `clean()`, `next_values()`, `next_copy()`, `set_done()`

Field order: `title`, `due_date`, `priority`, `notes`, then `repeat`, then `next_todo`.

```python
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from . import repeat as rp


class Todo(models.Model):
    class Repeat(models.TextChoices):
        NONE = rp.NONE, "Does not repeat"
        DAILY = rp.DAILY, "Every day"
        WEEKLY = rp.WEEKLY, "Every week"
        MONTHLY = rp.MONTHLY, "Every month"

    # ... title, due_date, priority, notes: no change ...
    repeat = models.CharField(
        max_length=10,
        choices=Repeat.choices,
        default=Repeat.NONE,
    )
    next_todo = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # ... done, created_at: no change ...

    @property
    def repeats(self):
        return self.repeat != self.Repeat.NONE

    def clean(self):
        super().clean()
        if self.repeats and self.due_date is None:
            # Tied to the field "repeat": every Todo ModelForm must include it.
            raise ValidationError({"repeat": "A repeating to-do needs a due date."})

    def next_values(self):
        """The fields of the next copy: what is copied, and the next due date."""
        start = self.due_date or timezone.localdate()
        return {
            "title": self.title,
            "notes": self.notes,
            "priority": self.priority,
            "repeat": self.repeat,
            "due_date": rp.next_due_date(start, self.repeat),
        }

    def next_copy(self):
        """The next to-do of a repeating one, not saved yet."""
        return Todo(**self.next_values())

    def is_untouched_copy_of(self, original):
        """True if this to-do is still exactly what Done made from `original`."""
        return all(getattr(self, name) == value for name, value in original.next_values().items())

    def set_done(self, target):
        """Done (target=True) or Undo (target=False). Does nothing if it is already so.

        Safe when two requests come at once: only one of them can claim the change.
        """
        with transaction.atomic():
            claimed = Todo.objects.filter(pk=self.pk, done=not target).update(done=target)
            if not claimed:
                return
            fresh = Todo.objects.get(pk=self.pk)
            if target:
                if fresh.repeats and fresh.next_todo_id is None:
                    copy = fresh.next_copy()
                    copy.save()
                    Todo.objects.filter(pk=fresh.pk).update(next_todo=copy)
            elif fresh.next_todo_id is not None:
                copy = fresh.next_todo
                if (
                    not copy.done
                    and copy.next_todo_id is None
                    and copy.is_untouched_copy_of(fresh)
                    # Feature 15 adds: and copy.has_untouched_subtasks_of(fresh)
                ):
                    copy.delete()  # SET_NULL empties fresh.next_todo
```

- `ValidationError({"repeat": ...})` puts the message **under the Repeats box**, not at the top.
- `next_values()` is used twice: to **make** the copy, and to check that the copy is **untouched**.
  So the two can never disagree.
- Feature 13 (lists) adds `"list": self.list` to `next_values()`. The field-copy test (below) fails
  until it does.

### 3. The migration

Django makes it. We never write or edit it by hand:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

It adds `repeat` (default `none`) and `next_todo` (empty). No data migration: there is no
production data, and both fields have a default. In the merge queue, it is made again after the rebase on 9 (sort).

### 4. `todos/forms.py` — the Repeats box

Add the field, and the name at the end of `fields`, one name per line:

```python
    repeat = forms.TypedChoiceField(
        label="Repeats",
        choices=Todo.Repeat.choices,
        required=False,
        empty_value=Todo.Repeat.NONE,
    )

    class Meta:
        model = Todo
        fields = [
            "title",
            "due_date",
            "priority",
            "notes",
            "repeat",
        ]
```

- A **TypedChoiceField** is a form field that allows only values from a list (`choices`), and can
  turn an empty value into a value we choose (`empty_value`). We use it like priority does.
- Empty or **missing** → `none`, with no error (see "Changes in behaviour", point 6).
- A value not in the list (`yearly`) gives Django's own error: `Select a valid choice. yearly is not
  one of the available choices.`
- The "needs a due date" check comes from `Todo.clean()` by itself. Nothing to add here.
- `TodoEditForm` needs **no** change: it is a subclass of `TodoForm`.

### 5. `todos/views.py` — `todo_toggle` reads the wanted state

```python
from django.http import HttpResponseBadRequest

WANTED = {"1": True, "0": False}


@require_POST
def todo_toggle(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    target = WANTED.get(request.POST.get("done"))
    if target is None:
        return HttpResponseBadRequest("done must be 1 or 0")
    todo.set_done(target)
    return back_to_list(request)
```

`page_context` needs **no** new key.

### 6. `todos/templates/todos/todo_list.html` — the page

**The Done / Undo form** gets one hidden input:

```html
<form method="post" action="{% url 'todo_toggle' todo.pk %}{{ list_query }}">
  {% csrf_token %}
  <input type="hidden" name="done" value="{% if todo.done %}0{% else %}1{% endif %}">
  <button type="submit">{% if todo.done %}Undo{% else %}Done{% endif %}</button>
</form>
```

**The add form**, after Notes (one field per line, like the others):

```html
{{ form.repeat.errors }}
{{ form.repeat.label_tag }}
{{ form.repeat }}
```

**The list**, after the due date:

```html
{% if todo.repeats and not todo.done %}<span class="repeat">{{ todo.get_repeat_display }}</span>{% endif %}
```

**The edit page** draws its fields with a loop, so it needs **no** change.

CSS (in `base.html`, where feature 4 put the shared CSS): `.repeat` looks like `.due` (small,
grey). The add form already wraps on a phone (`flex-wrap: wrap`), so the new box goes onto the
second row.

### 7. `todos/admin.py`

Add `"repeat"` to `list_display` and `list_filter`. The admin edit page shows the Repeats box by
itself (and not `next_todo`, because it is `editable=False`). Ticking "done" in the admin makes no
copy.

### 8. `AGENTS.md`

- `todos/models.py` row: add `repeat` and `next_todo`. Add: "`set_done(True/False)` is Done and
  Undo. Done on a repeating to-do makes the next one; Undo deletes it only if it is open, has no
  next copy and was not changed."
- A new row: `todos/repeat.py` — "the date math for repeating to-dos: `next_due_date`."
- `todos/views.py` row: Done/Undo post `done=1` or `done=0`; anything else is 400.
- Rules: "**Every `Todo` ModelForm must include `repeat`.** `Todo.clean()` ties its error to that
  field; without it, Django raises `ValueError`."

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code. Exact elements
(`assertContains(..., html=True)`), never loose text. Shared helpers come from
`todos/tests/integration/helpers.py`.

Two test words:

- **`subTest`**: one test runs many cases from a table; if one case fails, the report names that
  case, and the other cases still run.
- **`mock.patch`**: for one test, it replaces a function (here, "what is today") with a fake one
  that gives a fixed answer.

### Bottom: unit tests

**`todos/tests/unit/test_next_due_date.py`** (new). `SimpleTestCase` (no database).

| Test | Dates (from → to) |
|---|---|
| `test_daily` | 12 Oct 2026 → 13 Oct; 31 Oct → 1 Nov; **31 Dec 2026 → 1 Jan 2027**; 28 Feb 2027 → 1 Mar 2027; **28 Feb 2028 → 29 Feb 2028** (leap); 29 Feb 2028 → 1 Mar 2028 |
| `test_weekly` | 12 Oct 2026 → 19 Oct; **28 Dec 2026 → 4 Jan 2027**; 25 Feb 2027 → 4 Mar 2027; 26 Feb 2028 → 4 Mar 2028 (leap) |
| `test_monthly_same_day` | 12 Oct 2026 → 12 Nov; **15 Dec 2026 → 15 Jan 2027**; 28 Jan 2027 → 28 Feb 2027; 28 Feb 2028 → 28 Mar 2028 (in a leap year, 28 Feb is not the last day) |
| `test_monthly_last_day_stays_last_day` | **31 Jan 2027 → 28 Feb 2027**; **31 Jan 2028 → 29 Feb 2028**; **28 Feb 2027 → 31 Mar 2027**; **29 Feb 2028 → 31 Mar 2028**; 31 Mar → 30 Apr; 30 Apr → 31 May; 30 Jun → 31 Jul; 31 Aug → 30 Sep; 30 Sep → 31 Oct; 30 Nov → 31 Dec; **31 Dec 2026 → 31 Jan 2027** |
| `test_monthly_short_month` | 29 Jan 2027 → 28 Feb 2027; 30 Jan 2027 → 28 Feb 2027; 30 Jan 2028 → 29 Feb 2028 |
| `test_monthly_29_and_30_move_to_month_end_after_february` | 30 Jan 2027 → 28 Feb → **31 Mar**; 29 Mar → 29 Apr (not the last day: stays) ; 30 Mar → 30 Apr → **31 May** (documents the accepted drift) |
| `test_monthly_twelve_steps_from_the_31st` | start 31 Jan 2027, call 12 times: 28 Feb, 31 Mar, 30 Apr, 31 May, 30 Jun, 31 Jul, 31 Aug, 30 Sep, 31 Oct, 30 Nov, 31 Dec 2027, 31 Jan 2028 |
| `test_monthly_twelve_steps_from_the_15th` | start 15 Dec 2026, 12 times: always the 15th, ending 15 Dec 2027 |
| `test_none_is_a_mistake` | `none` raises `ValueError` |
| `test_unknown_word_is_a_mistake` | `yearly` raises `ValueError` |

How they fail today: `ImportError`, there is no `todos/repeat.py`. After the file exists, to show
each test can fail: remove the "last day stays last day" `if` for a moment → `28 Feb 2027 → 31 Mar`
and the 12-step chain fail; swap `min(due.day, last)` for `due.day` → the short-month tests fail
with `ValueError: day is out of range`; drop the December branch → the Dec → Jan tests fail.

**`todos/tests/unit/test_models.py`** (add):

| Test | What it checks | How it fails today |
|---|---|---|
| `test_new_todo_does_not_repeat` | `Todo().repeat == "none"`, `Todo().repeats` is false | `AttributeError` |
| `test_repeat_without_due_date_is_invalid` | `Todo(title="x", repeat="weekly").full_clean()` raises, with the message on `repeat` | no error |
| `test_next_copy_copies_every_field_a_person_can_change` | see below | `AttributeError`: no `next_copy` |
| `test_next_copy_is_open_with_the_next_date` | weekly, due 12 Oct 2026 → copy not done, due 19 Oct 2026, not saved (`pk is None`) | `AttributeError` |
| `test_next_copy_without_due_date_starts_from_today` | `mock.patch("django.utils.timezone.localdate", return_value=date(2026, 10, 12))`; daily, no date → due 13 Oct 2026 | `AttributeError` |

**The field-copy test.** It has a dictionary `SAMPLES` with one sample value per field name
(`"title": "Bins"`, `"notes": "blue bag"`, `"priority": Todo.Priority.HIGH`,
`"repeat": "weekly"`). It goes through the model's fields that a person can change: `editable`,
not `auto_created` (**auto_created** means Django made the field by itself, like `id`), and not
`done`, `due_date` or `created_at`. For each one:

- if the name is **not** in `SAMPLES`, the test fails with: "New field `<name>`: add a sample value
  here, and decide whether `next_values()` copies it."
- otherwise it sets the sample, makes `next_copy()`, and checks the copy has the same value.

So a new field from a later feature (for example `list` from 13) fails with a clear message, not a
silent bug. Feature 13 copies the list: the copy goes into the **original's current list**.

**`todos/tests/unit/test_forms.py`** (add, optional): `test_missing_repeat_on_edit_becomes_none` —
`TodoEditForm` for a weekly to-do, posted with title and date but no `repeat` → saved as `none`.
It documents point 6 of "Changes in behaviour".

### Middle: integration tests (`todos/tests/integration/test_repeat.py`, new)

**Done and Undo, through the test client** (`POST` to `todo_toggle` with `done=1` or `done=0`):

| Test | Setup → action | What it checks | How it fails today |
|---|---|---|---|
| `test_done_on_a_weekly_todo_makes_the_next_one` | "Bins", weekly, due 12 Oct 2026, High, notes "blue bag" → Done | the old one is done; exactly one open to-do, "Bins", due 19 Oct, weekly, High, "blue bag"; the old `next_todo` is the new one | `TypeError`: no `repeat` field |
| `test_done_posted_twice_makes_one_copy` | weekly → `done=1`, then `done=1` again (double click, old tab) | exactly 2 to-dos: the old one **done**, one open copy | with the flip design: the second post is an Undo, the copy is deleted, and the old one is **open** again |
| `test_undo_on_an_open_todo_does_nothing` | open to-do → `done=0` | still open, nothing deleted, 302 | with the flip design: it becomes done |
| `test_done_without_a_wanted_state_is_400` | `POST` with no `done`; with `done=2`; with `done=yes` (subTest) | status 400; the to-do is unchanged | today it flips (302) |
| `test_done_on_a_todo_that_does_not_repeat_makes_no_copy` | no repeat → Done | still 1 to-do, done | **protecting**: passes today (after adding `done=1`); must still pass |
| `test_undo_deletes_the_untouched_open_copy` | weekly → Done → Undo | exactly 1 to-do again, open, due 12 Oct, `next_todo` empty | `TypeError` |
| `test_done_undo_done_makes_one_open_copy` | weekly → Done → Undo → Done | exactly 1 open (due 19 Oct) and 1 done | `TypeError` |
| `test_undo_keeps_an_edited_copy` | weekly → Done → edit the copy's title → Undo on the old one | the copy is kept with its new title; the old one is open; its link is kept; Done on it again → **no** new to-do | `TypeError` |
| `test_undo_in_a_chain_keeps_the_completed_copy` | Monday weekly → Done → Done on Tuesday (its copy) → Undo on Monday | Monday open; Tuesday still done; Wednesday still open; Monday's link kept; Done on Monday again → no new to-do | `TypeError` |
| `test_undo_after_the_copy_was_deleted` | Done → Delete the copy → Undo | 1 to-do, open, no error | `TypeError` |
| `test_two_requests_at_once_make_one_copy` | load the same open to-do into `a` and `b` (two Python objects, like two requests that read at the same moment); `a.set_done(True)`, then `b.set_done(True)` | exactly 2 to-dos: one done, one open copy | `AttributeError`: no `set_done` |
| `test_done_keeps_the_filter` | `?show=active`, Done | redirects to `/?show=active`; the copy is on that page | `TypeError` (the filter part already works) |
| `test_delete_completed_keeps_the_next_copy` | Done a weekly one → "Delete completed" with the done id | only the open copy is left | `TypeError` |

**Showing the race tests fail.** For a moment, write `set_done` the old way: read `done`, change
it in Python, `save()`. Then `test_two_requests_at_once_make_one_copy` makes a second copy and
fails. And for the double-click test: for a moment, make the view ignore `done` and flip; then
`test_done_posted_twice_makes_one_copy` and `test_undo_on_an_open_todo_does_nothing` fail. Put
both back.

**Existing tests that change.** Every existing test that posts to `todo_toggle` must now send
`done=1` or `done=0`. Without it, it gets 400. This is part of the change, not a broken test. The
existing CUJ presses the real buttons, so it needs no change.

**`test_delete_completed_does_not_load_each_todo` changes on purpose** (in
`todos/tests/integration/test_views.py`, from feature 11). Today it says: "delete completed sends
a `DELETE`, and **no** `SELECT` on `todos_todo`". The new `next_todo` link breaks that, and that is
expected:

- Because of `on_delete=SET_NULL`, Django must first find the rows to delete, and then empty every
  link that points at them. So `Todo.objects.completed().filter(pk__in=ids).delete()` now sends
  **three** queries on `todos_todo`, always three, however many ids:
  1. one `SELECT` of the rows to delete (one query for all of them, not one per to-do);
  2. one `UPDATE todos_todo SET next_todo_id = NULL WHERE next_todo_id IN (...)`;
  3. one `DELETE FROM todos_todo WHERE id IN (...)`.
- The test's real purpose stays: **no query per to-do** (no "N+1", where the number of queries grows
  with the number of rows). The new version checks exactly 1 `SELECT`, 1 `UPDATE` and 1 `DELETE` on
  `todos_todo`, with 2 ids, and again with 5 ids: the numbers must be the **same**.
- **Show it:** after step 3 (the model change), run the old test and show it failing (it finds one
  `SELECT`). Then change it as above, and show the new version passing. Before the model change,
  the new version fails too (it finds no `UPDATE`), so it really tests the link.
- Tell feature 15: subtasks will add their own queries here; it must update the same test.

**The form**:

| Test | Posts / opens | What it checks | How it fails today |
|---|---|---|---|
| `test_add_a_weekly_todo` | title, date 2026-10-12, `repeat=weekly` | saved with `weekly` | `AttributeError` reading `repeat` |
| `test_add_without_repeat_does_not_repeat` | title only | saved with `none` | `AttributeError` |
| `test_repeat_without_due_date_is_rejected` | title, `repeat=daily`, no date | status 200; nothing saved; the exact error list `<ul class="errorlist"><li>A repeating to-do needs a due date.</li></ul>` right before the Repeats label; the title box still has the title | today it is saved and redirects (302) |
| `test_unknown_repeat_is_rejected` | `repeat=yearly` | nothing saved | today it is saved |
| `test_list_page_has_a_repeats_box` | `GET /` | the exact `<label for="id_repeat">Repeats:</label>` and the `<select name="repeat" id="id_repeat">` with its four `<option>`s, `none` selected | no box |
| `test_done_and_undo_buttons_send_the_wanted_state` | one open, one done to-do | the exact hidden inputs `value="1"` in the open row's form and `value="0"` in the done row's form | no hidden input |
| `test_open_repeating_todo_shows_its_repeat` | open, weekly | exact `<span class="repeat">Every week</span>` | no span |
| `test_completed_repeating_todo_does_not_show_repeat` | a done weekly to-do | that row's `<li>` has no `span.repeat` (checked on the row, not the whole page) | `TypeError` |
| `test_edit_the_copys_due_date` | weekly, due 12 Oct → Done → `POST` the copy's edit page with due date `2026-10-14` (other fields unchanged) | the copy is due 14 Oct; still exactly 2 to-dos (nothing made, nothing deleted); the old one still done and still linked to the copy | `TypeError`: no `repeat` (the edit part already works) |
| `test_edit_page_shows_the_saved_repeat` | `GET /<id>/edit/` of a monthly to-do | the `monthly` option is selected (exact element) | no box |
| `test_edit_removing_the_date_of_a_repeating_todo_is_rejected` | `POST` edit with empty date, repeat weekly | 200, the error, the to-do in the database unchanged | today the date is cleared |

### Top: a CUJ test (`todos/tests/cuj/test_journeys.py`)

This is a **new journey**, so it gets its own test, `test_a_weekly_todo_comes_back`:

1. Open the list. Type "Take out the rubbish", date `2026-10-12`, choose `Every week`, press Add.
2. See the row with `due 12 Oct 2026` and `Every week`.
3. Press Done on it.
4. See the completed row, and a new open row "Take out the rubbish" with `due 19 Oct 2026`.
5. Press Undo on the completed row. See exactly one row again, open, `due 12 Oct 2026`.

How it fails today: Playwright cannot find the Repeats box.

## Steps, in order

1. Start from `main` after wave 2, on `feature/repeating`. Write the new tests, and add `done=1` /
   `done=0` to the existing toggle tests. Run `make test`: the new tests fail with the errors
   listed; the protecting test passes. Run `make test-cuj`: the new journey fails.
2. Add `todos/repeat.py`. Run the date tests: they pass. Break the function on purpose (see above),
   see them fail, put it back.
3. Change `models.py`. Run `makemigrations`, then `migrate`. Do not edit the migration. Run
   `test_delete_completed_does_not_load_each_todo`: it fails (one `SELECT`). Change it to the new
   expected SQL (see Tests) and show it passing.
4. Change `forms.py`, `views.py`, the template, then the admin.
5. Run `make test` and `make test-cuj`: every test passes, **including feature 4's
   `test_edit_form_has_every_field_a_person_can_change`** (it now expects `repeat` too, by itself).
6. Break `set_done` and the view on purpose (see "Showing the race tests fail"), see the tests
   fail, put them back.
7. `make run`: add a monthly to-do due 31 Jan 2027, press Done, see 28 Feb 2027; Done again on the
   copy, see 31 Mar 2027. Press Done twice fast on a weekly one: one copy. Make the window narrow
   like a phone, and check the add form still fits.
8. Update `AGENTS.md`.
9. `uv run python manage.py makemigrations --check --dry-run` says "No changes detected".
10. `make check`. Commit, including the migration.

## Risks

- **The toggle changes for every to-do.** Any page, script or test that posts to `todo_toggle`
  without `done` now gets 400. In this repo, only the template and the tests post there; both are
  updated in this branch. A branch built at the same time (9, 15) that adds a toggle test must add
  `done=` after the rebase.
- **An edited copy is kept on Undo**, so two open to-dos can exist. This is on purpose: nothing the
  person typed is deleted. The person sees both and can delete one.
- **Monthly drift for 28 (not leap year), 29 and 30.** Such a day that is the last day of its month
  becomes "end of month": 30 Jan → 28 Feb → 31 Mar; 30 Apr → 31 May. The person fixes it once with
  Edit. A real fix needs an anchor-day field.
- **No catching up.** A daily to-do that is a week late comes back still late, once per Done. The
  person fixes it by editing the copy's due date (tested). The later option is the step-forward
  loop (see "What we will not do").
- **Every `Todo` ModelForm must include `repeat`**, or `clean()` makes Django raise `ValueError`.
  Written in `AGENTS.md`. The other way: change `clean()` to a non-field error.
- **Subtasks (15).** Subtasks are copied, all not done (owner). Feature 15 must add the copying and
  `has_untouched_subtasks_of` to `set_done` (related name `subtasks`). If 15 forgets, Undo could
  delete a copy whose subtasks the person changed: 15's tests must cover it.
- **Lists (13).** The copy must go into the original's current list; the field-copy test forces 13
  to decide.
- **Delete completed sends more SQL.** The `next_todo` link adds one `SELECT` and one `UPDATE` to
  every delete of to-dos (still a fixed number, not one per to-do). Feature 11's query test is
  changed on purpose (see Tests).
- **The admin** can tick "done" without making a next copy. Accepted: the admin is for fixing data.
- **Migration clash** with 9 (sort) and 15 (subtasks): handled by the merge queue (make the
  migration again after the rebase).
- **SQLite and two writers.** Python's `sqlite3` module, by default, waits up to 5 seconds for the
  other writer to finish; after that, the request fails with "database is locked". With one shared
  list and few users, that is fine.
