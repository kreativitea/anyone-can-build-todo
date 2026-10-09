# Plan: subtasks — small steps inside one to-do (feature 15)

Status: **approved, in progress.** Built on `main` before sort (9) and repeating (19) merged. The
parts that need repeating wait for the rebase. See "What happened".

Owner answers: (1) **yes** — when a repeating to-do comes back, its steps are copied to the new
copy, all not done; (2) **yes** — the Steps link on the edit page is enough to find the first step.

This is feature 15, in wave 3 of [the rollout plan](feature-rollout.md). The merge order in wave 3
is: 9 sort → 19 repeating → **15 subtasks**. It merges last in the wave. Branch:
`feature/subtasks`.

**Where this starts.** The work starts on `main` **after waves 1 and 2 are merged**: 5 due date,
12 count, 11 delete completed, 8 filter, 6 priority, 7 notes, 4 edit, 10 search. So "how it fails
today" in the tests means: `main` with those eight features in it. On that `main`:

- `todos/models.py` has `TodoQuerySet` as the manager, with `remaining()` and `completed()`.
- `todos/views.py` has `page_context(request, form)`, `list_params`, `list_query`,
  `back_to_list(request)`, and the edit view `todo_edit`.
- `todos/templates/base.html` is the page frame (from 4). Every page extends it.
- The edit page is at `/<id>/edit/`. Each row on the list has an **Edit** link.
- `todos/tests/integration/helpers.py` has the shared test helpers (`page_parts`).
- The test `test_delete_completed_does_not_load_each_todo` (from 11; 19 changes it, see below).
- The details pane (21, wave 2) is on `main`: `?selected=<id>` is one of the list settings.

Features 9 (sort) and 19 (repeating) merge **before** this one. Step 10 in "Steps, in order" says
what to do after the rebase on them.

## What we want

A to-do can have **steps**: small parts of the job, each with its own Done / Undo. For example, the
to-do "Bake a cake" has the steps "Buy flour", "Buy eggs", "Bake".

- On the **list**, a to-do with steps shows how far it is: **"1 of 3 steps"**. That text is a link
  to the to-do's steps page. The list stays light.
- Each to-do has its own small **steps page**, `/<id>/subtasks/`. There the person adds a step,
  marks a step done (or undoes it), and deletes a step. A **Back to the list** link goes back.
- The edit page has a **Steps** link to the same page. This is how a person adds the **first**
  step (a to-do with no steps shows no progress link on the list).
- No JavaScript.

**Words.** In the code and in addresses, the word is **subtask** (`Subtask`, `/5/subtasks/`,
`subtask_add`). Only the words a person reads on the page say **step**, because it is shorter and
plainer English.

## Decisions

### A new table, `Subtask`

A **model** is a Python class that Django turns into a database table. We add one:

| Field | Kind | Why |
|---|---|---|
| `todo` | `ForeignKey(Todo, on_delete=models.CASCADE, related_name="subtasks")` | Every step belongs to one to-do. |
| `title` | `CharField(max_length=200)` | The same limit as a to-do's title. |
| `done` | `BooleanField(default=False)` | The same field name as on `Todo`. |
| `created_at` | `DateTimeField(auto_now_add=True)` | For the order: oldest step first. |

- A **ForeignKey** (FK) is a field that points to a row in another table: "this step belongs to
  to-do number 5".
- `on_delete=models.CASCADE`: **when a to-do is deleted, its steps are deleted too.** A step without
  its to-do means nothing.
- `related_name="subtasks"` lets us write `todo.subtasks.all()`.
- The order is `["created_at", "pk"]`: oldest first. `pk` (the id) breaks a tie when two steps have
  the same time, which happens in fast tests.
- **A `SubtaskQuerySet`, empty for now**, used as the manager (`objects =
  SubtaskQuerySet.as_manager()`), like `TodoQuerySet`. It is the place for later step queries. Making
  it now means 17 adds one method and changes no other line.
- **One migration**, made by Django with `makemigrations`. Never written by hand.

### Steps have their own small page, `/<id>/subtasks/`

- The list row is already full (title, due date, priority, notes, Edit, Done, Delete). Step
  buttons there would make each row very long, mostly on a phone. So the list shows only the
  progress link.
- We do **not** put the steps on the edit page. If they were there, a person could type a new title
  in the edit form, then press "Add step" — the page reloads and the typed title is **lost**,
  because the two forms are separate. A separate page has no such trap. It also keeps the edit
  page's "Cancel" true: Cancel means "change nothing", but step buttons there would already have
  changed things.
- The steps page shows the to-do's title as its heading: `<h1>Steps: Bake a cake</h1>`. It has no
  edit form, so the title it shows is always the saved one.
- **The view passes `pk` and `title`, never the to-do object**, like the edit page (4). The template
  cannot then reach other fields by mistake.
- It extends `base.html`. Its own CSS goes in `{% block style %}`.
- **Back to the list** goes to `list_url`: the list address with the same list settings (filter,
  search, sort), for example `/?show=active`.

### Links to the steps page

- **On the list**, when a to-do has steps: `<a class="progress" href="/5/subtasks/"
  aria-label="1 of 3 steps for Bake a cake">1 of 3 steps</a>`. "1 of 3" is plain English; "1/3"
  is harder to read, and a screen reader says "1 slash 3".
- The **accessible name** (what a screen reader says for a link) adds the to-do's title, so two
  rows with "1 of 3 steps" are not the same to a screen reader user. The visible words come first,
  so voice control ("click 1 of 3 steps") still works.
- **On the edit page**, after the form: `<a href="/5/subtasks/">Steps</a>`. It is outside the edit
  form. If the person typed something in the edit form and then follows this link, the typing is
  lost — the same as with Cancel. That is normal for a link.
- Every link to the steps page ends with `{{ list_query }}`, so "Back to the list" later returns to
  the same filter.

### A step's "checkbox" is a Done / Undo button

- A real `<input type="checkbox">` only sends something when a form is submitted. Making it send by
  itself on a click needs JavaScript. We do not need it: we use the list's own pattern, a small
  form with one button, **Done** or **Undo**. A done step has a line through it (class `done`).
- **The button posts the state the person wants** (`done=1` or `done=0`), not "flip". This is the
  rule from repeating (19): a double click or an old tab then cannot undo a Done. Any other value
  gets **400**. We reuse 19's `WANTED` table.
- Each button's accessible name has the step's title: "Done Buy flour", "Undo Buy flour", "Delete
  Buy flour". The visible word is first.

### Three `POST` views, and one page view

| Address | Name | Method | What it does |
|---|---|---|---|
| `/<id>/subtasks/` | `subtask_list` | GET | The steps page. |
| `/<id>/subtasks/add/` | `subtask_add` | POST | Adds a step to to-do `<id>`. |
| `/<id>/subtasks/<subtask_id>/done/` | `subtask_done` | POST | Sets Done or Undo (`done=1` / `0`). |
| `/<id>/subtasks/<subtask_id>/delete/` | `subtask_delete` | POST | Deletes the step. |

- Changes are **`POST` only** (`require_POST`), with the CSRF token. `GET` gets 405.
- The page and `subtask_add` find the to-do with `get_object_or_404(Todo, pk=pk)`.
- **The step must belong to the to-do in the address.** `subtask_done` and `subtask_delete` use
  `get_object_or_404(Subtask, pk=subtask_pk, todo_id=pk)`. So `/7/subtasks/3/delete/`, where step 3
  belongs to to-do 5, gives **404** and changes nothing. A wrong or old link can never change a
  step of another to-do. Later features keep this `todo_id=pk` (see "Accounts and sharing").
- After each change, the browser goes back to the steps page with the same list settings, for
  example `/5/subtasks/?show=active`. A new helper, `back_to_subtasks(request, pk)`, builds it from
  `reverse()` and `list_params` only — **never** an address from the request, so it can never be
  an open redirect (a bug where a site sends the browser to any address someone put in a link).
- `SubtaskForm` is a `ModelForm` with only `title`. Django checks: not empty, at most 200
  characters, spaces around it removed. Its visible label is **New step** (`<label>`), so everyone
  sees what the box is for.
- **A bad step** (empty, too long): nothing is saved. The steps page is shown again with the error
  and with what the person typed.
- **One place for the page's keys:** `subtask_page(request, pk, title, subtask_form)`, used by
  `subtask_list` and by `subtask_add`'s error path. One key per line. (Like `page_context`.)

### Accounts (17) and sharing (20): what they must write

The lookups keep the rule "the step belongs to the to-do in the address" (`todo_id=pk` now, `todo.subtasks` in 17 and 20).

| View | Now (15) | Accounts (17) | Sharing (20) |
|---|---|---|---|
| `subtask_list` | `get_object_or_404(Todo, pk=pk)` | `get_object_or_404(Todo.objects.for_user(request.user), pk=pk)` | `todo = get_todo_or_deny(request.user, pk, need=SEE)` |
| `subtask_add` | `get_object_or_404(Todo, pk=pk)` | `get_object_or_404(Todo.objects.for_user(request.user), pk=pk)` | `todo = get_todo_or_deny(request.user, pk, need=EDIT)` |
| `subtask_done`, `subtask_delete` | `get_object_or_404(Subtask, pk=subtask_pk, todo_id=pk)` | `todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)`, then `get_object_or_404(todo.subtasks, pk=subtask_pk)` | `todo = get_todo_or_deny(request.user, pk, need=EDIT)`, then `get_object_or_404(todo.subtasks, pk=subtask_pk)` |

- 17 adds **no** `Subtask.objects.for_user`. A step has no owner of its own: 17 first finds the
  person's to-do, then the step through `todo.subtasks`. `todo.subtasks` only holds that to-do's
  steps, so it is the same check as `todo_id=pk`.
- 20 swaps the to-do lookup for `get_todo_or_deny` and keeps `todo.subtasks`. The template hides
  the step forms from viewers.
- **`test_step_of_another_todo_is_404` must keep passing in 17 and 20, unchanged.** It is the test
  that proves the `todo_id=pk` rule.

### Finishing every step does **not** finish the to-do

No automatic magic. The person presses **Done** on the to-do themselves. Why:

- **Steps are often not complete.** A person may tick 3 of 3 and still have more to do, or plan to
  add more steps.
- **Magic is hard to undo well.** If the last step made the to-do Done, Undo on one step would have
  to reopen it. And if the person had pressed Done on the to-do by hand? Two places would decide one
  thing, and they would disagree. With repeating (19), an automatic Done would also make a next copy.
- **One button, one change.** A beginner can read each view and know what it does.
- The same the other way: **Done on the to-do does not tick its steps.**

"3 of 3 steps" on the list already tells the person: you can press Done now.

### "1 of 3 steps" with no extra query per row

An **N+1 problem** is when a page sends 1 query for the list and then 1 more for **each** row. With
50 to-dos, that is 51 queries. We must not do that.

```python
def with_subtask_progress(self):
    return self.annotate(
        subtask_count=Count("subtasks", distinct=True),
        subtask_done_count=Count("subtasks", filter=Q(subtasks__done=True), distinct=True),
    )
```

- **`annotate`** adds a computed value to each row, in the **same** query.
- To count, the database uses a **JOIN** (it puts each to-do next to each of its steps, one line
  per pair) and a **GROUP BY** (it folds the lines of one to-do back into one row, and counts them).
- **`distinct=True`** counts each step **once**. Why it matters: if the same query also joins
  another table — for example tags (14), where a to-do with two tags appears on two lines — a plain
  `Count` would count each step twice ("2 of 6" instead of "1 of 3"). `distinct=True` counts
  different step ids, so it stays right.
- `page_context` starts the list from `Todo.objects.with_subtask_progress()` instead of
  `Todo.objects.all()`. Filter, search and sort work on it as before.
- The list template uses `todo.subtask_count` and `todo.subtask_done_count`, **never**
  `todo.subtasks.count` (that is one query per row). A test counts the queries.

### Delete completed (11): its query test must change, on purpose

Today the test says "**no** `SELECT` reads `todos_todo`". With a table that points to `Todo` with
`CASCADE`, that cannot stay true. Checked on Django 5.2.17 (with 19's `next_todo` link), deleting
the completed to-dos sends:

```sql
SELECT "todos_todo"."id", "todos_todo"."title", ... FROM "todos_todo" WHERE (... "id" IN (1, 2))
DELETE FROM "todos_subtask" WHERE "todos_subtask"."todo_id" IN (1, 2)
UPDATE "todos_todo" SET "next_todo_id" = NULL WHERE "todos_todo"."next_todo_id" IN (1, 2)
DELETE FROM "todos_todo" WHERE "todos_todo"."id" IN (2, 1)
```

- Before Django deletes the to-dos, it must know which ones they are, to delete their steps. So it
  sends **one** `SELECT` that reads the **whole rows** of the to-dos to delete (all at once, not one
  each — and every column, not only the ids). Then **one** `DELETE` for all their steps. Then
  **one** `DELETE` for the to-dos.
- This is Django's own **cascade**, and it is correct. Writing our own SQL to avoid the `SELECT`
  would mean doing by hand what Django already does right.
- **Repeating (19) already changed this test.** Its `next_todo` link (`SET_NULL`) alone makes
  Django send the `SELECT` and the `UPDATE`. 19's version checks exactly 1 `SELECT`, 1 `UPDATE` and
  1 `DELETE` on `todos_todo`, with 2 ids and again with 5 ids. **We start from 19's version** and
  keep all of it: the steps add no query on `todos_todo`.
- We **add** the step parts. The test gives each completed to-do two steps and the open to-do one
  step. Then, with each SQL text in upper case and trimmed, for 2 ids and for 5 ids:
  1. exactly **one** statement starts with `DELETE FROM "TODOS_SUBTASK" WHERE` (one for all steps);
  2. **no** statement starts with `SELECT` and contains `FROM "TODOS_SUBTASK"` (steps are deleted,
     never loaded);
  3. 19's checks on `todos_todo` are unchanged;
  4. the steps of the completed to-dos are gone; the open to-do's step is still there.
- Its docstring adds: *"Steps go in one DELETE, and are never loaded. It must never be one query per
  to-do or per step."*
- Deleting one to-do (`todo.delete()`) also deletes its steps, with one more `DELETE`.

### The admin: steps inside the to-do

`SubtaskInline(admin.TabularInline)`: `model = Subtask`, `extra = 0`, `fields = ["title", "done"]`.
`TodoAdmin` gets `inlines = [SubtaskInline]`. An **inline** shows the steps as a small table on the
to-do's admin page. `Subtask` is **not** registered alone: a step is always seen with its to-do.

### Repeating (19): steps come back with the next copy (owner: yes)

When Done on a repeating to-do makes the next copy, **its steps are copied too, all not done**.
Example: "Weekly clean" with the steps kitchen (done), bath (done), floor → Done → the new "Weekly
clean" has kitchen, bath, floor, all open. A weekly checklist is the main reason to have both
features.

- **Where.** 19's `next_copy()` returns a to-do that is **not saved yet** (19's test checks
  `pk is None`). A step needs a saved to-do to point to. So we add one method,
  `copy_subtasks_to(copy)`, and `set_done` calls it right **after** `copy.save()`, inside the same
  transaction (so the copy and its steps are made together, or not at all). `next_copy()` itself
  does not change.
- **One query for all the steps:** `Subtask.objects.bulk_create([...])`. Only the titles are
  copied; `done` is `False`; `created_at` is new. The order stays the same (they are made in
  order).
- The steps of the **old** (completed) to-do are not changed. They are its history.

**Undo: when is a copy with steps still "untouched"?** 19's rule: Undo deletes the next copy only if
it is open, has no next copy of its own, and is **untouched**. We make "untouched" include the
steps:

- The copy's steps must be **exactly** what `copy_subtasks_to` would make now: the same titles, in
  the same order, **all not done**. A method, `subtask_titles()`, gives the list of titles, oldest
  first. Untouched means: `copy.subtask_titles() == fresh.subtask_titles()` and no step of the copy
  is done.
- If the person **ticked** a step on the copy, **added** one, or **deleted** one, the copy is
  **kept** (with its steps), like an edited copy. Nothing the person did is lost.
- If the copy is untouched, Undo deletes it, and CASCADE deletes its copied steps with it.
- This **replaces** 19's placeholder "and the copy has no steps" (19's comment says
  `copy.steps.exists()`; we do not add that line).
- It is checked in the same place as the other fields, `is_untouched_copy_of`, so there is one
  rule in one method.

## Owner answers

1. **Copy the steps to the next repeating copy, all not done:** yes. See "Repeating (19)" above.
2. **The Steps link on the edit page is enough** to find the first step: yes. No "Add steps" link on
   the list.

## What we will not do (yet)

- **No automatic Done** for the to-do, and no automatic ticking of steps.
- **No steps on the list** other than the "1 of 3 steps" link.
- **No editing a step's title.** Delete it and add it again.
- **No reordering of steps.** Oldest first.
- **No due date, priority or notes on a step**, and no steps inside steps.
- **No JavaScript**, so no checkbox that sends itself.
- Steps are **not** searched (10) and **not** counted by "items left" (12).
- **No steps in the details pane (21)** yet. See "Notes for later".

## Changes in behaviour

1. A new table, `Subtask`, and one migration.
2. A new page, `/<id>/subtasks/`: the to-do's steps, oldest first, each with Done / Undo and
   Delete; a "New step" box with an **Add step** button; **Back to the list**.
3. Three new `POST` addresses: add, done, delete. A step of another to-do gives 404. `GET` gives 405.
   A Done / Undo without `done=1` or `done=0` gives 400.
4. The list shows "**1 of 3 steps**" (a link) for a to-do with steps.
5. The edit page has a **Steps** link.
6. Deleting a to-do, or deleting the completed to-dos, deletes their steps.
7. The admin shows a to-do's steps on its page.
8. Repeating: Done copies the steps to the next copy, all not done. Undo deletes the copy only if
   its steps are still exactly the copied ones, untouched.

What stays the same: add, Done / Undo, delete, delete completed (what it deletes), filter, search,
sort, count, the edit form. Done on a to-do does not touch its steps, and the other way.

## The changes, one file at a time

### 1. `todos/models.py`

```python
from django.db.models import Count, Q


class TodoQuerySet(models.QuerySet):
    # ... remaining(), completed() stay

    def with_subtask_progress(self):
        """Each to-do with its number of steps, and of done steps, in the same query."""
        return self.annotate(
            subtask_count=Count("subtasks", distinct=True),
            subtask_done_count=Count("subtasks", filter=Q(subtasks__done=True), distinct=True),
        )


class SubtaskQuerySet(models.QuerySet):
    """Queries for steps. Empty for now; later step queries go here."""


class Subtask(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SubtaskQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return self.title
```

`SubtaskQuerySet` and `Subtask` go **below** `Todo`.

In `Todo` (19's methods), two new methods and two small changes:

```python
    def subtask_titles(self):
        """The titles of this to-do's steps, oldest first."""
        return list(self.subtasks.values_list("title", flat=True))

    def copy_subtasks_to(self, copy):
        """Give the next copy the same steps, all not done. One query."""
        Subtask.objects.bulk_create(
            [Subtask(todo=copy, title=title) for title in self.subtask_titles()]
        )

    def is_untouched_copy_of(self, original):
        """True if this to-do is still exactly what Done made from `original`, steps too."""
        return (
            all(getattr(self, name) == value for name, value in original.next_values().items())
            and self.subtask_titles() == original.subtask_titles()
            and not self.subtasks.filter(done=True).exists()
        )
```

In `set_done`, right after `copy.save()`: `fresh.copy_subtasks_to(copy)`. Do **not** add 19's
placeholder line `and not copy.subtasks.exists()`.

- `Subtask` is defined below `Todo` in the same file. Using it inside a method is fine: Python looks
  the name up when the method runs, not when the class is made.
- `bulk_create` makes all the steps in one `INSERT`. It does not call `save()`, which is fine:
  `Subtask` has no custom `save()`. `created_at` (`auto_now_add`) is still filled in.

### 2. The migration — made by Django

`uv run python manage.py makemigrations`, then `migrate`. Do not edit the file.

### 3. `todos/forms.py`

```python
class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = [
            "title",
        ]
        labels = {
            "title": "New step",
        }
```

### 4. `todos/urls.py`

```python
path("<int:pk>/subtasks/", views.subtask_list, name="subtask_list"),
path("<int:pk>/subtasks/add/", views.subtask_add, name="subtask_add"),
path("<int:pk>/subtasks/<int:subtask_pk>/done/", views.subtask_done, name="subtask_done"),
path("<int:pk>/subtasks/<int:subtask_pk>/delete/", views.subtask_delete, name="subtask_delete"),
```

### 5. `todos/views.py`

In `page_context`, the list starts from `Todo.objects.with_subtask_progress()`.

```python
def subtask_page(request, pk, title, subtask_form):
    """The steps page of one to-do. subtask_list and subtask_add's error path use this."""
    params = list_params(request.GET)
    return render(
        request,
        "todos/subtask_list.html",
        {
            "pk": pk,
            "title": title,
            "subtasks": Subtask.objects.filter(todo_id=pk),
            "subtask_form": subtask_form,
            "list_query": list_query(params),
            "list_url": reverse("todo_list") + list_query(params),
        },
    )


def back_to_subtasks(request, pk):
    """Back to the steps page, with the same list settings. Always our own page."""
    return redirect(reverse("subtask_list", args=[pk]) + list_query(list_params(request.GET)))


def subtask_list(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    return subtask_page(request, pk, todo.title, SubtaskForm())


@require_POST
def subtask_add(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    form = SubtaskForm(request.POST)
    if form.is_valid():
        form.instance.todo = todo
        form.save()
        return back_to_subtasks(request, pk)
    return subtask_page(request, pk, todo.title, form)


@require_POST
def subtask_done(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, todo_id=pk)
    target = WANTED.get(request.POST.get("done"))
    if target is None:
        return HttpResponseBadRequest("done must be 1 or 0")
    subtask.done = target
    subtask.save(update_fields=["done"])
    return back_to_subtasks(request, pk)


@require_POST
def subtask_delete(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, todo_id=pk)
    subtask.delete()
    return back_to_subtasks(request, pk)
```

- `subtask_list` has no decorator: a `GET` only reads. (If 4 used `require_GET` on read pages,
  match it.)
- `subtask_done` never touches the to-do (no magic).
- If 4 made a `list_url(request)` helper, use it for `"list_url"` instead of building it here.

### 6. `todos/templates/todos/subtask_list.html` — new

```html
{% extends "base.html" %}

{% block title %}Steps{% endblock %}

{% block style %}
  .steps li { display: flex; align-items: center; gap: 0.5rem; }
  .steps li.done .title { text-decoration: line-through; color: #888; }
{% endblock %}

{% block content %}
  <h1>Steps: {{ title }}</h1>
  <ul class="steps">
    {% for subtask in subtasks %}
      <li class="{% if subtask.done %}done{% endif %}">
        <span class="title">{{ subtask.title }}</span>
        <form method="post" action="{% url 'subtask_done' pk subtask.pk %}{{ list_query }}">
          {% csrf_token %}
          {% if subtask.done %}
            <input type="hidden" name="done" value="0">
            <button type="submit" aria-label="Undo {{ subtask.title }}">Undo</button>
          {% else %}
            <input type="hidden" name="done" value="1">
            <button type="submit" aria-label="Done {{ subtask.title }}">Done</button>
          {% endif %}
        </form>
        <form method="post" action="{% url 'subtask_delete' pk subtask.pk %}{{ list_query }}">
          {% csrf_token %}
          <button type="submit" aria-label="Delete {{ subtask.title }}">Delete</button>
        </form>
      </li>
    {% empty %}
      <li>No steps yet.</li>
    {% endfor %}
  </ul>
  <form class="add-step" method="post" action="{% url 'subtask_add' pk %}{{ list_query }}">
    {% csrf_token %}
    {{ subtask_form.title.errors }}
    {{ subtask_form.title.label_tag }}
    {{ subtask_form.title }}
    <button type="submit">Add step</button>
  </form>
  <p><a href="{{ list_url }}">Back to the list</a></p>
{% endblock %}
```

`label_tag` writes `<label for="id_title">New step:</label>`. The "New step" box has no
`autofocus`: the person may first want to tick a step.

### 7. `todos/templates/todos/todo_list.html` — the progress link

In each row, after the due date (and priority):

```html
{% if todo.subtask_count %}<a class="progress" href="{% url 'subtask_list' todo.pk %}{{ list_query }}" aria-label="{{ todo.subtask_done_count }} of {{ todo.subtask_count }} steps for {{ todo.title }}">{{ todo.subtask_done_count }} of {{ todo.subtask_count }} steps</a>{% endif %}
```

CSS in the list page's `{% block style %}`: `.progress { color: #666; font-size: 0.85rem; }`.

### 8. `todos/templates/todos/todo_edit.html` — the Steps link

After the edit `</form>`: `<p><a href="{% url 'subtask_list' pk %}{{ list_query }}">Steps</a></p>`.

### 9. `todos/admin.py`

```python
class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 0
    fields = ["title", "done"]
```

`TodoAdmin` gets `inlines = [SubtaskInline]`.

### 10. `AGENTS.md`

- `models.py` row: "`Subtask`: a step inside a to-do (`todo`, `title`, `done`, `created_at`),
  deleted with its to-do. `with_subtask_progress()` counts the steps in the list query."
- `urls.py` / `views.py` rows: the steps page and its three `POST` addresses; "a step is always
  looked up with `todo_id=pk`".
- A new row: `todos/templates/todos/subtask_list.html` — the steps page of one to-do.
- Under Rules, one line: "In code and addresses say *subtask*; on the page say *step*."

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code. Elements are checked
exactly, with `assertContains(..., html=True)`; checks that something is **not** there look inside
one row or one form (with `page_parts`), never the whole page. Redirects are checked with
`response["Location"]`, exactly. In the integration tests, `Bake a cake` has the steps `Buy flour`
(done), `Buy eggs` and `Bake`. After the rebase on 19, every Done / Undo post sends `done=`.

### Top: a CUJ test (`todos/tests/cuj/test_journeys.py`)

Breaking a to-do into steps is a **new journey**: `test_split_a_todo_into_steps`.

1. Add `Bake a cake`. Press **Edit Bake a cake**, then **Steps**.
2. Fill **New step** with `Buy flour`, press **Add step**. The same for `Bake`.
3. Press **Done Buy flour**. The button **Undo Buy flour** is there.
4. Press **Back to the list**. The row of `Bake a cake` has the link **1 of 2 steps for Bake a cake**,
   and its own button is still **Done** (the to-do is not done by itself).

How it fails today: there is no **Steps** link, so Playwright waits and fails with a timeout. The
real browser also checks the CSRF token on the new forms.

### Bottom: unit tests (3)

| Test | File | What it checks | How it fails today |
|---|---|---|---|
| `test_with_subtask_progress_counts_steps` | `unit/test_models.py` | `Bake a cake` has `subtask_count == 3`, `subtask_done_count == 1`; a to-do with no steps has `0` and `0` | `ImportError`: no `Subtask` |
| `test_deleting_a_todo_deletes_its_steps` | `unit/test_models.py` | `todo.delete()`: its steps are gone; another to-do's steps stay | `ImportError` |
| `test_step_form` | `unit/test_subtask_form.py` (new, `SimpleTestCase`) | fields are exactly `["title"]`; `"  Bake  "` becomes `Bake`; `"   "` is not valid; the label is `New step` | `ImportError` |

### Middle: integration tests (`todos/tests/integration/test_subtasks.py`, new — 17)

On today's `main`, every test that makes a `Subtask` fails with `ImportError`, and every test that
uses `reverse("subtask_…")` with `NoReverseMatch`.

| # | Test | What it does | What it checks |
|---|---|---|---|
| 1 | `test_steps_page_shows_the_steps` | `GET /<id>/subtasks/` | exactly `<h1>Steps: Bake a cake</h1>`; the three titles in order; exactly `<button type="submit" aria-label="Undo Buy flour">Undo</button>` and `<button type="submit" aria-label="Done Bake">Done</button>`; exactly `<label for="id_title">New step:</label>`; exactly `<a href="/">Back to the list</a>` |
| 2 | `test_steps_page_with_no_steps` | a to-do with none | exactly `<li>No steps yet.</li>` |
| 3 | `test_steps_page_of_a_missing_todo_is_404` | `GET /999/subtasks/` | 404 |
| 4 | `test_add_a_step` | post `title=Buy sugar` | saved on **this** to-do, not done; redirect to `/<id>/subtasks/` exactly |
| 5 | `test_bad_step_is_not_saved` | `subTest`: `"   "`, and 201 letters | status 200; the error inside the add form; the box keeps the input (201 letters case); no new step |
| 6 | `test_done_and_undo_a_step` | post `done=1` for `Bake`, then `done=0` | done, then not done; redirect to the steps page |
| 7 | `test_done_posted_twice_stays_done` | post `done=1` twice | still done |
| 8 | `test_done_needs_a_wanted_state` | `subTest`: no `done`, `done=yes` | 400; not changed |
| 9 | `test_steps_and_the_todo_are_separate` | tick every step; then Done on the to-do with one step open | the to-do stays open after all steps are done; Done on the to-do leaves the open step open |
| 10 | `test_delete_a_step` | post delete for `Bake` | gone; the other steps stay |
| 11 | `test_step_of_another_todo_is_404` | second to-do `Shop`; done and delete `/<Shop id>/subtasks/<Bake id>/…` (`subTest` each) | 404; `Bake` is not changed and not deleted. **Must pass unchanged in 17 and 20.** |
| 12 | `test_get_cannot_change_steps` | `GET` add, done, delete (`subTest` each) | 405; nothing changed |
| 13 | `test_add_step_needs_the_csrf_token` | `Client(enforce_csrf_checks=True)`, no token | 403; no new step |
| 14 | `test_step_actions_keep_the_list_settings` | post add, done, delete to `…?show=active&next=https://evil.example`, with `next` in the data too (`subTest` each) | redirect to `/<id>/subtasks/?show=active` exactly |
| 15 | `test_links_keep_the_list_settings` | `GET /<id>/subtasks/?show=active` and `GET /<id>/edit/?show=active` | every `POST` form `action` on the steps page ends with `?show=active` (`page_parts`); exactly `<a href="/?show=active">Back to the list</a>`; on the edit page exactly `<a href="/<id>/subtasks/?show=active">Steps</a>` |
| 16 | `test_list_shows_step_progress` | open `/?show=active&q=cake&sort=due` (the to-do matches the filter, the search and the sort) | exactly `<a class="progress" href="/<id>/subtasks/?show=active&amp;q=cake&amp;sort=due" aria-label="1 of 3 steps for Bake a cake">1 of 3 steps</a>`; in the row of a to-do with no steps (`page_parts`), no `a.progress` |
| 17 | `test_list_queries_do_not_grow_with_rows` | count the queries of `GET /` with 1 to-do with steps, then 6 (`CaptureQueriesContext`) | the two numbers are **equal**. We compare, not `assertNumQueries(n)`, so accounts (17) can add its own queries |

Write the exact `href` in test 16 in the order `list_query` gives after 9 and 10 merged.

Plus, in other files:

- **Changed on purpose:** `test_delete_completed_does_not_load_each_todo` (`integration/test_views.py`),
  as in "Decisions". It also checks the completed to-dos' steps are gone and the open one's stays.
- **Added to 19's file** (`integration/test_repeat.py`). "Weekly clean", weekly, with the steps
  `Kitchen` (done) and `Floor`. How they fail today: `ImportError` (no `Subtask`).

  | Test | What it does | What it checks |
  |---|---|---|
  | `test_done_copies_the_steps_not_done` | Done | the new copy has exactly `Kitchen`, `Floor`, in that order, **both not done**; the old to-do still has `Kitchen` (done) and `Floor` |
  | `test_undo_deletes_a_copy_with_untouched_steps` | Done → Undo | exactly 1 to-do, open; its 2 steps are as before; no other step exists (the copied ones went with the copy) |
  | `test_undo_keeps_a_copy_whose_steps_changed` | `subTest` each: tick `Floor` on the copy; add `Bath` to the copy; delete `Kitchen` from the copy — then Undo on the old one | the copy is **kept**, with its steps as the person left them; the old one is open; Done on it again makes **no** new to-do |
  | `test_done_on_a_todo_without_steps_copies_none` | a weekly to-do with no steps → Done → Undo | the copy had no steps; Undo deletes it (19's case still works) |
- **Admin:** `test_admin_shows_steps_inline` (`integration/test_subtasks.py`): a superuser made in the
  test, `force_login` (no password); `GET` the to-do's admin page → 200, the inline's
  `subtasks-TOTAL_FORMS` input, and the step titles in their input boxes (exact elements).

**Note for tags (14):** its query test (or test 16 above, after 14 merges) must give the to-do
**two tags**, so a missing `distinct=True` would show "2 of 6 steps".

### Proving the tests can fail

- The changed delete-completed test: (1) the new step parts fail before the model exists
  (`ImportError`). (2) After the model, they pass, and 19's parts still pass. (3) **Break it on
  purpose for a moment:** in `todo_delete_completed`, delete the to-dos one by one in a loop. The
  test fails (more queries with 5 ids than with 2). Put it back.
- Test 17: change `todo.subtask_count` to `todo.subtasks.count` in the list template for a moment.
  It fails. Put it back.
- `distinct=True`: remove it for a moment and run 14's two-tag test (after 14). Before 14, the
  reviewer script showed the double count with two tags.
- Test 11: change the lookup to `get_object_or_404(Subtask, pk=subtask_pk)` for a moment. It fails.
  Put it back.
- `test_undo_keeps_a_copy_whose_steps_changed`: remove the `done=True` check from
  `is_untouched_copy_of` for a moment. The "tick `Floor`" case fails (the ticked copy is deleted).
  Put it back.
- `git diff` must not show any of these breaks.

**Protecting tests** (pass before and after): 4's
`test_edit_form_has_every_field_a_person_can_change` (the reverse relation `subtasks` is
`auto_created`, so the edit form gets no field); 8's `test_every_post_form_keeps_the_filter`; every
count, filter, search, sort and repeating test.

## Steps, in order

1. Write the unit tests, the integration tests (not the changed delete-completed test yet), and the
   CUJ test. Run `make test`: they fail with `ImportError` / `NoReverseMatch`. Run `make test-cuj`:
   the new journey times out.
2. `models.py`: `with_subtask_progress()`, `SubtaskQuerySet`, `Subtask`. Run `makemigrations`, then
   `migrate`.
3. The delete-completed test: add the step parts to 19's version. Before step 2 they fail
   (`ImportError`); after, they pass. Break it on purpose (a loop that deletes one by one).
4. `forms.py`: `SubtaskForm`.
5. `urls.py`: four addresses. `views.py`: `subtask_page`, `back_to_subtasks`, the four views,
   `page_context` starts from `with_subtask_progress()`.
6. `subtask_list.html`; the progress link in `todo_list.html`; the Steps link in `todo_edit.html`.
7. `admin.py`: the inline. In `Todo`: `subtask_titles()`, `copy_subtasks_to()`, the new
   `is_untouched_copy_of`, and the `copy_subtasks_to` call in `set_done`. Run the repeating tests.
8. `make test`, `make test-cuj`: all pass. Do the other "break it on purpose" checks.
9. `make run` and try it: add a to-do, Edit → Steps, add three steps, tick one, Back to the list:
   "1 of 3 steps". Tick all: the to-do is **not** done. On Active, follow the progress link, add a
   step, Back: still Active. Delete completed: their steps are gone (check in the admin). Narrow
   window like a phone: the row and the steps page fit.
10. **Rebase on 9 and 19** (they merge first):
    - Sort (9): keep sort's `order_by` after `with_subtask_progress()`. Fix test 16's `href` order.
    - Repeating (19): add `done=` to every Done / Undo post in these tests; reuse `WANTED`; start the
      delete-completed test from 19's version; check 19's merged `set_done` and
      `is_untouched_copy_of` still look as in this plan, and change them as above.
    - The migration: delete this branch's migration and run `makemigrations` again.
    - The CUJ tests: keep every step of every journey.
    - `make test` and `make test-cuj` again.
11. `AGENTS.md`.
12. `uv run python manage.py makemigrations --check --dry-run`: "No changes detected".
13. `make check`. Commit.

## Risks

- **The delete-completed test grows again.** 11 wrote it, 19 changed it, 15 adds to it. The
  docstring says why each query is there, and the "break it on purpose" check shows it still catches
  a loop.
- **Copied steps and Undo.** If the person adds a step to the **old** to-do after Done, the copy's
  steps no longer match, so Undo keeps the copy (two open to-dos). Rare, and nothing is lost —
  the same as 19's "edited copy" rule.
- **Same-title accessible names.** Two steps with the same title ("Buy milk" twice) give two buttons
  both called "Done Buy milk". Two to-dos with the same title and the same progress give two links
  with the same name. A screen reader user cannot tell them apart. Rare; accepted, like the Edit
  link in 4.
- **The first step is found through Edit → Steps.** The owner says this is fine.
- **Leaving the edit page by the Steps link loses unsaved typing**, the same as Cancel. Accepted: it
  is a plain link, and the step forms are no longer on the edit page.
- **Later queries that join another table** (tags, 14; lists, 13) could count steps twice without
  `distinct=True`. We use it, and 14's test uses two tags to prove it.
- **Accounts and sharing** must keep "the step belongs to the to-do in the address" (`todo.subtasks` after the to-do lookup). The table above says exactly
  what each writes; test 11 must pass unchanged.

## Notes for later: steps in the details pane (21)

The details pane (21) shows one to-do on the right of the list, with `?selected=<id>`. This plan does
**not** change it. Later, steps could appear there in a small, safe way:

- the same "1 of 3 steps" link (it already ends with `{{ list_query }}`, which now keeps
  `selected`, so "Back to the list" returns with the pane open);
- a short, read-only list of the step titles, done ones crossed out, perhaps the first five;
- the step **buttons** stay on the steps page, so the pane has no new `POST` forms.

The query for the pane is one more small query for **one** to-do (`todo.subtasks.all()`), so it is
not an N+1. Because `list_query` includes `selected`, every link and redirect in this plan already
keeps the pane open; test 14 and 16 check only `show`, so they are not affected.

## What happened

The builder followed the plan on today's `main` (waves 1 and 2, and the details pane). Sort (9)
and repeating (19) were being built at the same time, so they are **not** in this branch yet.
These are the places where the build is a little different from the plan, and why.

1. **No real browser** (owner decision). The journey `test_split_a_todo_into_steps` uses Django's
   test client: it reads each form from the page and presses its button (`press()`), and follows
   links by their name (`link_href`). `press()` now finds a button by its **accessible name** (the
   `aria-label`, else the text), so "Done Buy flour" can be pressed. It also takes `lands_on`: the
   steps page, not the list. `PageButton` got `label` and `accessible_name`, with a unit test.
2. **Done / Undo is a button with `name="done" value="1"`** (or `"0"`), not a hidden input.
   `page_forms` sends a pressed button's name and value, like a browser.
3. **`WANTED` is made here** (`{"1": True, "0": False}` in `views.py`), because 19 is not merged.
   On the rebase, keep 19's one table and delete this one.
4. **The details pane gets a Steps row** (asked by the orchestrator, "Notes for later" said not
   yet): `<dt>Steps</dt><dd><a href="/5/subtasks/?selected=5">1 of 3 done</a></dd>`, after
   Created and before Notes, only when the to-do has steps. It uses the counts the list query
   already has (`with_subtask_progress`), so it costs **no** query at all, not even one; the
   pane's test `test_selecting_costs_no_extra_query` still passes. `pane_element(..., steps=None)`
   builds it in tests. Tests: `test_pane_shows_the_steps_row`,
   `test_pane_of_a_todo_without_steps_has_no_steps_row`.
5. **The progress link sits after the title `<span>`**, not inside it, so `title_element` and every
   title test stay the same.
6. **The delete-completed query test** was changed on today's `main` (without 19's `next_todo`).
   Checked for 2 ids and for 5 ids: exactly one `SELECT` reads `todos_todo`, one
   `DELETE FROM "TODOS_SUBTASK" WHERE`, one `DELETE FROM "TODOS_TODO" WHERE`, **no** `UPDATE`, no
   `SELECT` from `todos_subtask`, the same number of statements for 2 and 5; the steps of the
   deleted to-dos are gone and the open to-do's step stays. Each case runs in a transaction that is
   rolled back, so the 5-id case starts from the same rows.
7. **A unit test for `distinct=True`**, `test_counts_stay_right_when_the_query_joins_again`. Before
   tags (14) there is no other table to join, but a filter through the steps after the counts
   joins the steps a second time. Without `distinct=True` it says "2 of 6", not "1 of 3".
8. **The unit tests are in a new file**, `unit/test_subtask_models.py`, so the old model tests
   still ran while `Subtask` did not exist.
9. **Test 16 has no `sort=due` yet**: sort (9) is not on `main`, so the address is
   `/?show=active&q=cake`. Add `&sort=due` after the rebase on 9.
10. **The add form's box keeps the spaces** after the "   " error (`value="   "`): Django shows
    what was typed. The test checks the whole form exactly. **This expected value was set after
    the code ran**: the first version of `test_bad_step_is_not_saved` expected no `value` for
    "   ", and the first green run showed that Django echoes the typed spaces. The test was then
    corrected to match. Before the code it failed only with `NoReverseMatch`, so this one detail
    was never seen failing for its own reason.

### After the review

An adversarial reviewer ran 28 mutations (small deliberate bugs) on the branch; 20 were caught.
These changes close the gaps. Each new or changed test was first seen failing (logs:
`subtasks-review-before.txt`, `subtasks-bugs2.txt` in the scratchpad).

11. **Escaping**: `test_titles_are_escaped`, with a to-do titled `<b>"x</b>` and a step titled
    `"><img src=x onerror=alert(1)>`. It checks the exact escaped `<h1>`, the page `<title>`, the
    whole step row (`step_row`), the progress link (`progress_link`), and that `<img` is not on
    the steps page or the list. `|safe` in each of 5 places makes it fail. The `<title>` is checked
    as raw text: the HTML reader that `html=True` uses reads the inside of `<title>` as plain
    text, so `<b>` and `&lt;b&gt;` looked the same and `|safe` there first went unseen.
12. **CSRF on every change**: `test_add_step_needs_the_csrf_token` became
    `test_step_changes_need_the_csrf_token`: add, Done and Delete without the token → 403, and no
    step changes. `@csrf_exempt` on `subtask_done` or `subtask_delete` makes it fail.
13. **Missing ids**: `test_changes_to_a_missing_todo_or_step_are_404` posts add, Done and Delete to
    `/999/…`, to a missing step, and with a 26-digit id → 404, nothing created or changed. **It
    found a real bug**: `get_object_or_404(Subtask, pk=…, todo_id=<26 digits>)` crashed with
    `OverflowError` (a 500 page), because Django checks the range of a primary-key lookup but not
    of `todo_id`. The fix is one helper, `get_subtask_or_404(pk, subtask_pk)`: first
    `get_object_or_404(Todo, pk=pk)`, then `get_object_or_404(todo.subtasks, pk=subtask_pk)`. This
    is already the shape accounts (17) and sharing (20) planned, so they change only its first
    line. It costs one more small query per step change. `test_step_of_another_todo_is_404` is
    unchanged and still catches a lookup without the to-do.
14. **Rename**: `test_delete_completed_does_not_load_each_todo` is now
    `test_delete_completed_uses_a_fixed_number_of_queries`, because Django does read the to-dos
    (one `SELECT`, whole rows; no `.only()`). The older plans keep the old name, as history.
15. **`autofocus` on the "New step" box** (`SubtaskForm`'s widget): the steps page is for adding
    steps. `EMPTY_BOX` and the bad-step box in the tests have it; test 1 now checks the whole add
    form with `EMPTY_BOX`.
16. **The page `<title>` is `Steps: <the to-do's title>`**, so browser tabs and screen readers
    say which to-do. Test 1 checks `<title>Steps: Bake a cake</title>`.
17. The phone width is checked by the orchestrator with a real 375-pixel window before the merge.

### Checks

- **Before the code**: 4 unit/integration errors (`ImportError: Subtask` / `SubtaskForm` in three
  new test modules and in the delete-completed test) and the journey failed with
  `0 links named 'Steps', not 1`. Everything else passed.
- **A second red run** (after the review; `subtasks-before-2.txt`), so that each test shows its own
  reason, not only `ImportError`: the model, the form, the admin and migration `0005` present;
  `views.py`, `urls.py`, `todo_list.html` and `todo_edit.html` as on the branch's base, and no
  `subtask_list.html`. Result: Unit 75 passed (the model and form tests pass: their code is
  there). Integration: 22 errors, every one `NoReverseMatch` for `subtask_list`, `subtask_add`,
  `subtask_done` or `subtask_delete` (the steps page and the three posts); 2 failures:
  `test_list_shows_step_progress` (no progress link on the row) and `test_pane_shows_the_steps_row`
  (no Steps row in the pane). The journey failed with `0 links named 'Steps', not 1`. Passing in
  this run, because their part was already there or because nothing is there to break: the
  delete-completed query test and the admin inline test (model and admin present),
  `test_list_queries_do_not_grow_with_rows`, `test_pane_of_a_todo_without_steps_has_no_steps_row`
  and `test_changes_to_a_missing_todo_or_step_are_404` (no address at all gives 404 too). Those
  are protecting tests; each one was shown failing against its own deliberate bug.
- **After**: `make test` (Integration 175, Unit 75), `make test-cuj` (CUJ 4) and `make check` pass.
  After the review: Integration 177, Unit 75, CUJ 4 (`subtasks-after-review.txt`).
- **Deliberate bugs**, each put back (`git diff` shows none): a lookup without `todo_id=pk` →
  `test_step_of_another_todo_is_404` fails (302 != 404); no `distinct=True` → "(2, 6) != (1, 3)";
  `todo.subtasks.count` in the list → `test_list_queries_do_not_grow_with_rows` fails (10 != 5
  queries); delete completed one by one in a loop → the delete-completed test fails (2 and 5
  deletes, not 1).
- **Migration** `0005_subtask` (made by `makemigrations`, after `0004_todo_notes`) ran on a
  database that already had two to-dos: `OK`; both to-dos were still there with 0 steps; a step
  could be added; `makemigrations --check` says "No changes detected".
- **By eye** (headless Chrome, 1280 wide): the list row shows a small grey "1 of 3 steps" before
  Edit; the pane shows "Steps 1 of 3 done" under Created; the steps page has the heading, a
  crossed-out done step with Undo, open steps with Done, the "New step:" box and Back to the list.
  Headless Chrome cannot make a window narrower than about 500 pixels, so its "phone" picture is
  cut on the right, for the old list page too; the phone check is left for a real narrow window.

### Waiting for the rebase on 9 and 19

- `copy_subtasks_to()` (one `bulk_create`, every step not done) and its call in `set_done` right
  after `copy.save()`.
- **Owner decision (replaces the plan's "steps exactly the copied, untouched ones" comparison):**
  adding, finishing / undoing, or deleting a step on a to-do sets that to-do's `edited=True`
  (repeating, 19, adds the `edited` flag; Undo keeps an edited copy). So no `subtask_titles()`
  comparison in `is_untouched_copy_of`; the step views set `edited` instead.
- The four repeating tests in `integration/test_repeat.py`; the deliberate bug for "keeps a copy
  whose steps changed" becomes "a step view that does not set `edited`".
- The delete-completed test: start from 19's version (1 `SELECT`, 1 `UPDATE`, 1 `DELETE` on
  `todos_todo`) and keep this branch's step checks; `count("UPDATE")` becomes 1.
- `done=` on every to-do Done / Undo post in these tests (`test_steps_and_the_todo_are_separate`);
  one `WANTED` table.
- Test 16's address and `href` with `sort=due`; sort's `order_by` after `with_subtask_progress()`.
- The migration: delete `0005_subtask.py` and run `makemigrations` again.
