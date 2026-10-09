# Plan: edit a to-do

Status: **approved, in progress.** Built and tested on `main` with wave 1. The part "After 6 and 7
are on `main`" (and its four tests) is left until this branch is rebased on 6 and 7.

This is feature 4, in wave 2 of [the rollout plan](feature-rollout.md). The merge order in wave 2
is: 6 priority → 7 notes → **4 edit** → 10 search.

An adversarial review (a reviewer whose job is to find what is wrong) checked the first version,
on Django 5.2. Every finding is fixed below. The Django behaviours this plan relies on were checked
by running them.

**Where this starts.** The work starts on `main` **after wave 1 is merged**: 5 due date, 12 count,
11 delete completed, 8 filter. So "how it fails today" in the tests means: `main` with those four
features in it. On that `main`:

- `todos/forms.py` has `TodoForm`, with the fields `title` and `due_date`.
- `todos/models.py` has `TodoQuerySet` as the manager.
- `todos/views.py` has `page_context(request, form)`, and the filter helpers `list_params`,
  `list_query` and `back_to_list(request)`.
- Every `POST` form on the list page ends its `action` with `{{ list_query }}`.
- `todos/tests/integration/helpers.py` has the shared test helpers (`page_parts`).

Features 6 (priority) and 7 (notes) are built at the same time as this one, and merge **before**
it. They add fields to `TodoForm`. The section "After 6 and 7 are on `main`" says what this feature
must then do. Feature 10 (search) merges **after** it.

## What we want

Each to-do on the list gets an **Edit** link. It opens a small page with a form. The form shows
what is saved now: the title, the due date, and every other field the add form has. The person
changes what they want and presses **Save**. Then they are back on the list, and the list shows the
new values. **Cancel** goes back to the list and changes nothing.

The page needs no JavaScript.

## Decisions

### A separate edit page, not editing inside the list

- The edit page has its own address: `/<id>/edit/`, for example `/5/edit/`. Its name in the code is
  `todo_edit`.
- **Inline editing** (changing the title right in the list) needs JavaScript, or one open form per
  row. A separate page needs neither. It is the simplest way, and the standard Django way.
- `GET /5/edit/` only **reads**: it shows the form. `POST /5/edit/` **changes**: it saves. This
  follows the rule "change data only with `POST`".
- `HEAD` is allowed too. (`HEAD` is a `GET` that returns only the headers, not the page. Link
  checkers use it.) Other methods, for example `PUT` or `DELETE`, get status **405** ("method not
  allowed"). Django's `require_http_methods(["GET", "HEAD", "POST"])` does this for us.
- A to-do that does not exist gives **404** ("not found"), with `get_object_or_404`, like toggle and
  delete.

### A function view, not `UpdateView`

Django has a ready-made class, `UpdateView`, for edit pages. We use a **function view** instead,
because every other view in this app is a function, and a beginner can read it from top to bottom.
It is the standard Django pattern for a form: "if `POST` and the form is good, save and redirect;
else show the form".

### One form: the edit form is the add form, with a small change

- A **ModelForm** is a form that Django builds from the model. `TodoForm` is one.
- The rollout plan says: **every field feature adds its field to `TodoForm`**. So the edit page uses
  `TodoForm`, and every field appears on it with no more work.
- One thing is wrong for editing. On the add page, some boxes have no visible label. They are named
  by a hidden `aria-label` (`"New to-do"` on the title box, and `"Notes"` on the notes box after
  feature 7), and the title box has the hint text (`placeholder`) "What needs doing?". On the edit
  page the to-do is not new, and every box should have a **visible label**.
- So we make a **subclass** (a new class that starts as a copy of another class and changes a
  little): `TodoEditForm(TodoForm)`. For every field, it removes `aria-label` and `placeholder`.
  Then each box is named by its visible label, for example "Title:", which Django writes from the
  model.
- Its fields are **the same as `TodoForm`**. A unit test checks that the edit form has every field a
  person can change. So if feature 6 or 7, or a later feature, adds a field, the edit page has it
  too — or the test fails and tells us.
- The edit page draws its fields with a **loop**, so a new field also needs **no template change**.

### "Done" is not on the edit page

- The Done / Undo button already changes "done". Two ways to do the same thing would only confuse.
- `TodoForm` has no `done` field, so the edit form has none either. Even if someone sends `done=on`
  by hand, Django ignores it: a form reads only its own fields.
- `created_at` (when the to-do was made) is not in the form.

### What `form.save()` writes, and a small race

- `form.save()` saves the **whole row**: every column, `done` too. For `done` it writes the value
  that the view read from the database **at the start of this `POST` request** — not the value from
  when the edit page was opened.
- So a lost toggle can only happen in a tiny window: Ana presses Save, and in the same few
  milliseconds Ben presses Done on the same to-do. Then Ana's save can write the old `done` back.
  (A **race** is a bug where the result depends on which of two things happens first.)
- We could stop it with `save(update_fields=[...])`, which writes only the listed columns. **We do
  not**, because:
  - the window is a few milliseconds, inside one request;
  - `update_fields` cannot hold a many-to-many field. Feature 14 (tags) will add one to the form,
    and then the edit page would break.
  This is in Risks.

### A bad edit shows the errors and keeps the input

Like the add form (feature 5):

- An empty title, a title over 200 characters, or a bad date: **nothing is saved**. The edit page is
  shown again, with the error, and with **what the person typed**, so nothing is lost.
- The page heading is always **"Edit to-do"**, not the to-do's title. Why: when a form checks its
  input, Django copies **the good values** into the to-do object in memory, even when another field
  is bad. (The database does not change.) For example, a new title with a bad date: `todo.title` in
  memory is the new title, which was **not** saved. Showing it as the heading would be wrong. A
  fixed heading avoids this trap. The template never shows `todo.title`; the view passes only `pk`.

### Fields that are missing from a hand-made post

A browser always sends every box of the form. A hand-made post (for example from a test or a
script) may leave a field out. Django then does this (checked on Django 5.2):

- **due date** left out: the date is **removed** (`None`). Its model field has no default.
- **notes** left out (after 7): the notes are **kept**. Django skips a field that is missing from
  the post when its model field has a default (`default=""`).
- **priority** left out (after 6): it becomes **Medium**. This is the priority plan's rule
  ("a missing priority is Medium"), and a priority test pins it.

The browser never hits these cases. A test after the rebase pins them, so a change is seen.

### The Edit link on each row

- It is a normal link (`<a>`), because opening the edit page only reads.
- It shows the word **Edit**. Its accessible name is **"Edit Buy milk"**. An **accessible name** is
  what a screen reader (a program that reads the page aloud) says for a link or button. With only
  "Edit" on every row, a screen reader user would hear "Edit, Edit, Edit" and not know which one is
  which. We set it with `aria-label="Edit {{ todo.title }}"`. The visible word "Edit" is at the
  start of the name, so people who use voice control can still say "click Edit".
- Django **escapes** the title in the attribute (it turns `"` into `&quot;` and `<` into `&lt;`). So
  a title with quotes cannot break the page. A test checks it.
- It goes **right before the Done form**: after the title, the due date, and (after 6 and 7) the
  priority label and the notes.

### The edit page keeps the filter

From feature 8 (filter): when a person is on the Active view and edits a to-do, they come back to
the Active view.

- The Edit link's address ends with `{{ list_query }}`, for example `/5/edit/?show=active`.
- The view reads the list parameters **once**, with `list_params(request.GET)`.
- The edit form posts to `/5/edit/?show=active` (the rule "every `POST` form action ends with
  `{{ list_query }}`").
- After a good save, the view ends with `back_to_list(request)`, like add, toggle and delete.
- The **Cancel** link goes to the same list address, `/?show=active`.
- **Never an open redirect.** (An **open redirect** is a bug where a site sends the browser to any
  address someone put in a link.) Only values that `list_params` has checked reach an address. The
  filter feature already tests `back_to_list` for this.
- When search (10) adds `q` to `list_params`, the edit page keeps the search too, with no change
  here.

### A shared base template

- The edit page is the app's second page. Both pages need the same `<head>` and the same basic CSS.
- So this feature makes **`todos/templates/base.html`**: the `<head>`, and the CSS that every page
  uses. A **base template** is a page frame. Other templates **extend** it (`{% extends "base.html" %}`)
  and fill in **blocks**: named holes, like `{% block content %}`.
- `todo_list.html` and `todo_edit.html` both extend it. Later pages (accounts, lists, sharing)
  extend it too. (Decision of the orchestrator.)
- CSS that only one page uses stays in that page, in `{% block style %}`.

### The CUJ test grows one step

A **CUJ** (critical user journey) test is a whole journey in a real browser. AGENTS.md says: add a
new CUJ test only for a **new** journey. Fixing a typo in a to-do you just planned is part of the
same journey, "plan and finish a to-do". So we add **one step** to the one CUJ test, like feature 5
did. We do not add a new test.

The real browser also checks one thing the integration tests cannot: the **CSRF token** on the edit
form. (CSRF is an attack where another site makes your browser send a form. Django's test client
skips this check, but a real browser does not.)

## What we will not do (yet)

- **No inline editing** and no JavaScript.
- **No editing "done"** on the edit page. Use Done / Undo.
- **No warning when two people edit the same to-do.** The list is shared. If two people save, the
  last save wins. This is the same as toggle today.
- **No friendly page when the to-do was deleted** while someone had its edit page open. Their Save
  gets the plain 404 page.
- **No history** and no "undo my edit".

## Changes in behaviour

1. A new address, `/<id>/edit/`. `GET` shows the form with the saved values. `POST` saves a good
   form and goes back to the list, with the same filter. A bad form shows the errors and keeps the
   input, and saves nothing.
2. Each row on the list has an **Edit** link, with the accessible name "Edit" + the title.
3. A missing to-do gives 404. A method other than `GET`, `HEAD` or `POST` gives 405.
4. The date box writes a saved date as `2026-10-12` in every language (see `forms.py` below).

What stays the same: the list page looks and works the same (it now extends `base.html`, with the
same HTML inside). Add, Done / Undo, delete and delete completed do not change. The add form's
title box is still called "New to-do". No new field, **no migration**.

## The changes, one file at a time

### 1. `todos/forms.py` — the edit form

Add, under `TodoForm`:

```python
class TodoEditForm(TodoForm):
    """The add form, for a to-do that already exists. Every field of TodoForm is here too.

    On this page every box has a visible label, so the hidden names and hints go.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.pop("aria-label", None)
            field.widget.attrs.pop("placeholder", None)
```

- `self.fields` is this form's **own copy** of the fields. Django makes a new copy (a "deep copy")
  for every form, so a change here never touches another form.
- **Never change `self.base_fields`** (or `TodoForm.declared_fields`). `base_fields` are the fields
  of the **class**. For the fields that `TodoForm` writes out itself (`due_date`, and `priority`
  after 6), the edit form's class and `TodoForm` share **the same field object**. A change there
  would also change the add form. (For fields that Django makes from the model, like `title`, each
  class gets its own; so the bug would only show on some fields — easy to miss.) A unit test catches
  this mistake.
- `autofocus` stays: on the edit page, the cursor starts in the title box.

In `TodoForm`, make the date box always write its value as `2026-10-12`:

```python
widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
```

- A date box (`type="date"`) only understands a value like `2026-10-12`. The add form never showed a
  saved date, so this did not matter before. The edit page does show one.
- Without `format=`, Django writes the date in the format of the **current language**. Today the
  language is `en-us`, which happens to give `2026-10-12`. But in British English (`en-gb`) Django
  writes `12/10/2026`, and the browser would show an **empty** date box. A unit test shows this.

### 2. `todos/urls.py` — the address

```python
path("<int:pk>/edit/", views.todo_edit, name="todo_edit"),
```

`<int:pk>` means "a whole number here". Django gives it to the view as `pk`, the to-do's id.

### 3. `todos/views.py` — the view

```python
from django.views.decorators.http import require_http_methods

from .forms import TodoEditForm, TodoForm


@require_http_methods(["GET", "HEAD", "POST"])
def todo_edit(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    params = list_params(request.GET)
    if request.method == "POST":
        form = TodoEditForm(request.POST, instance=todo)
        if form.is_valid():
            form.save()
            return back_to_list(request)
    else:
        form = TodoEditForm(instance=todo)
    return render(
        request,
        "todos/todo_edit.html",
        {
            "pk": pk,
            "form": form,
            "list_query": list_query(params),
            "list_url": reverse("todo_list") + list_query(params),
        },
    )
```

- `instance=todo` tells the form "change this to-do, do not make a new one". On `GET`, it also fills
  the boxes with the saved values.
- `params` is read once, and used for both the form's address and the Cancel link.
- The template gets `pk`, not `todo`, so it cannot show a title that was not saved.
- `back_to_list` and `page_context` do not change. The edit page is not the list page.

### 4. `todos/templates/base.html` — a new file, the page frame

Move the `<head>` and the shared CSS out of `todo_list.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}To-do list{% endblock %}</title>
  <link rel="icon" href="data:,">
  <style>
    body { font-family: system-ui, sans-serif; max-width: 32rem; margin: 2rem auto; padding: 0 1rem; }
    .errorlist { margin: 0; padding: 0; list-style: none; color: #b00020; }
    .errorlist li { padding: 0; border: 0; }
    button { padding: 0.4rem 0.8rem; font-size: 0.9rem; cursor: pointer; }
    {% block style %}{% endblock %}
  </style>
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
```

- It lives in `todos/templates/`, not in `todos/templates/todos/`, because it is for every page.
  Django finds it as `"base.html"`.
- Only CSS that **every** page needs goes here. The rest stays in each page's `{% block style %}`.

### 5. `todos/templates/todos/todo_list.html` — extend the frame, and the Edit link

- The first line becomes `{% extends "base.html" %}`.
- `{% block title %}To-do list{% endblock %}`.
- The page's own CSS (the add form, the list, the filter links, the footer) goes into
  `{% block style %}`. Remove the lines that are now in `base.html`. Check the `.errorlist` rule:
  the add form's version has `flex: 1 1 100%`; keep that part in this page, as
  `form.add .errorlist { flex: 1 1 100%; }`.
- Everything inside `<body>` goes into `{% block content %}`, **with no change**.

The Edit link: in each row, **right before** the Done form:

```html
<a class="edit" href="{% url 'todo_edit' todo.pk %}{{ list_query }}" aria-label="Edit {{ todo.title }}">Edit</a>
```

No CSS change is needed: the row is already a flex row (a row of boxes side by side). Check it on a
narrow window (step 7 below).

### 6. `todos/templates/todos/todo_edit.html` — a new page

```html
{% extends "base.html" %}

{% block title %}Edit to-do{% endblock %}

{% block style %}
  form.edit .field { display: flex; flex-direction: column; gap: 0.25rem; margin-bottom: 1rem; }
  form.edit input, form.edit select, form.edit textarea { padding: 0.5rem; font: inherit; }
  form.edit .actions { display: flex; align-items: center; gap: 1rem; }
{% endblock %}

{% block content %}
  <h1>Edit to-do</h1>

  <form class="edit" method="post" action="{% url 'todo_edit' pk %}{{ list_query }}">
    {% csrf_token %}
    {{ form.non_field_errors }}
    {% for field in form %}
      <div class="field">{{ field.as_field_group }}</div>
    {% endfor %}
    <div class="actions">
      <button type="submit">Save</button>
      <a href="{{ list_url }}">Cancel</a>
    </div>
  </form>
{% endblock %}
```

- `{% for field in form %}` draws every field: today the title and the due date, after the rebase
  also priority and notes.
- `field.as_field_group` (new in Django 5.0) draws one field the standard way: its visible label
  (for example `<label for="id_title">Title:</label>`), its help text, its errors, and the box.
- The CSS puts each label above its box, so the page fits a phone. `select` and `textarea` are there
  for priority (a choice) and notes (long text). The notes box is open, with the visible label
  "Notes:" — this is what the notes plan asks for.

### 7. `todos/models.py` — no change

No new field, so **no migration**.

### 8. `AGENTS.md`

- `todos/forms.py` row: "`TodoForm`, the add form, built from the model. `TodoEditForm`, the same
  form for the edit page, with every field of `TodoForm`. A new field goes in `TodoForm` only."
- `todos/urls.py` row: add "edit" to the list of addresses.
- `todos/views.py` row: add "`todo_edit`: `GET` shows the form, `POST` saves it. A bad form shows
  the page again with the errors."
- New rows: `todos/templates/base.html` — the page frame: the `<head>` and the shared CSS. Every
  page extends it. `todos/templates/todos/todo_edit.html` — the edit page. It draws every field of
  the form with a loop.
- Rules: "A new page extends `base.html`."

## After 6 and 7 are on `main`

This feature merges after 6 (priority) and 7 (notes). Before it joins the merge queue, the builder
**rebases** on that `main`. A **rebase** moves this branch's commits so they start from the newest
`main`. Then:

1. **Run the unit test `test_edit_form_has_every_field_a_person_can_change`.** 6 and 7 put their
   fields in `TodoForm`, so it should pass with no change: the edit page shows priority and notes
   by itself.
2. **The row in `todo_list.html`.** 6 adds the priority label and 7 adds the notes `<p>`, after the
   due date. This branch adds the Edit link in about the same place, so git shows a clash. Keep
   their lines first, then the Edit link, then the Done form.
3. **The CSS.** 6 and 7 add CSS to `todo_list.html`'s `<style>`. This branch moved that CSS into
   `{% block style %}`. Move their new lines into the block too.
4. **The CUJ test.** 6 and 7 may also change it. Keep every step: theirs and the edit step.
5. Write the tests in "After the rebase" below, with the field names from the merged code.

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code. Each test before the
rebase uses only the title and the due date, so it works before and after 6 and 7 merge.

Words used below:

- A **`subTest`** runs one part of a test with its own name. If one part fails, the others still
  run, and the report says which part failed.
- **`SimpleTestCase`** is Django's test class for tests that do not use the database.
- Elements are checked exactly, with `assertContains(..., html=True)`, which compares whole HTML
  elements and ignores the order of attributes. Redirects are checked with `response["Location"]`,
  exactly.

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

Add one step to `test_plan_and_finish_a_todo`, just after the check for `due 12 Oct 2026`:

```python
item.get_by_role("link", name="Edit Buy milk").click()
page.get_by_label("Title", exact=True).fill("Buy oat milk")
page.get_by_role("button", name="Save").click()
item = page.get_by_role("listitem").filter(has_text="Buy oat milk")
expect(item).to_be_visible()
expect(item).to_contain_text("due 12 Oct 2026")
```

The steps after it (Done, Undo, Delete) use the new `item`.

How it fails today: there is no link called "Edit Buy milk", so Playwright waits 5 seconds and
fails with a timeout.

### Bottom: unit tests (`todos/tests/unit/test_edit_form.py`, new file)

A new file, so it does not clash with 6 and 7's form tests. The file imports `from todos import
forms` (the module), and each test uses `forms.TodoEditForm`. So today each test fails on its own,
with its own error, instead of the whole file failing at once.

| Test | What it checks | How it fails today |
|---|---|---|
| `test_edit_form_has_every_field_a_person_can_change` | the fields of `TodoEditForm()` are exactly the model fields that are `editable` and not made by Django (`auto_created`), minus `done`. Today: `{"title", "due_date"}` | `AttributeError`: there is no `TodoEditForm` |
| `test_edit_form_does_not_change_the_add_form` | make a `TodoEditForm()` first. Then make a `TodoForm()`, and check the `widget.attrs` of **every** field exactly: title `{"aria-label": "New to-do", "placeholder": "What needs doing?", "autofocus": True, "maxlength": "200"}`, due date `{"type": "date"}` | `AttributeError`: there is no `TodoEditForm` |
| `test_date_box_shows_iso_date_in_every_language` | inside `translation.override("en-gb")` (which switches Django to British English for a moment), `TodoForm(instance=Todo(title="Buy milk", due_date=date(2026, 10, 12)))["due_date"]` is exactly `<input type="date" name="due_date" value="2026-10-12" id="id_due_date">` | `AssertionError`: the value is `12/10/2026` |

The first test reads the fields from the model, so it never needs a change for 6 and 7. A later
feature that adds a field a person should **not** edit on this page (for example an owner, in
feature 17) must say so in this test, on purpose.

**How to see the second test fail after the code is written** (a deliberate bug that really leaks):
in `TodoEditForm.__init__`, add `self.base_fields["due_date"].widget.attrs["class"] = "edit"`. The
test fails, because the add form's date box now has `class="edit"` too. Put it back. `git diff`
must not show the line. (Checked: changing `base_fields["title"]` would **not** leak, because Django
makes a new title field for each class. That is why the test checks every field.)

### Middle: integration tests (`todos/tests/integration/test_edit.py`, new file)

A new file, so it does not clash with other branches. `Buy milk` is a to-do with the due date
12 Oct 2026, not done.

**Exact elements with errors.** In Django 5.2, a box with an error gets more attributes
(`aria-invalid="true"`, `aria-describedby="id_title_error"`), and the error list gets an `id`
(`<ul class="errorlist" id="id_title_error">`). Before writing these tests, print the bound field
once in `uv run python manage.py shell` and copy the exact element.

**How the tests fail today.** A test that builds the address with `reverse("todo_edit", ...)` fails
with `NoReverseMatch`: there is no address named `todo_edit`. A test that only opens the list page
writes the Edit link's address out by hand (`f"/{todo.pk}/edit/"`), so it fails with an
`AssertionError`: the link is not on the page.

To read a form's `action` from a page, use the shared helper `page_parts` in
`todos/tests/integration/helpers.py`. If it cannot read form actions yet, add that there, not in
this file.

**Tests for new behaviour.** These must **fail** before the change:

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_edit_page_shows_the_saved_values` | `GET /<id>/edit/` | status 200; `<title>Edit to-do</title>`; `<h1>Edit to-do</h1>`; exactly `<label for="id_title">Title:</label>` and `<input type="text" name="title" value="Buy milk" maxlength="200" required id="id_title" autofocus>`; exactly `<input type="date" name="due_date" value="2026-10-12" id="id_due_date">` | `NoReverseMatch` |
| `test_edit_saves_the_new_values` | post title `Buy oat milk`, date `2026-10-20` | the saved title and date are the new ones; redirect to `/` exactly | `NoReverseMatch` |
| `test_edit_can_remove_the_due_date` | post title `Buy milk`, date empty | the saved date is `None` | `NoReverseMatch` |
| `test_bad_edit_is_not_saved_and_keeps_the_input` | a `subTest` each: title `"   "` (error `This field is required.`); a title of 201 letters (error `Ensure this value has at most 200 characters (it has 201).`); title `Buy oat milk` with date `not-a-date` (error `Enter a valid date.`) | status 200; the error, as an exact `<ul class="errorlist">` element; the title box, exactly, with the typed value; the saved title and date are not changed | `NoReverseMatch` |
| `test_edit_does_not_change_done_or_created_at` | a `subTest` each: a completed to-do, posted without `done`; an open to-do, posted with `done=on` | `done` is not changed; `created_at` is not changed | `NoReverseMatch` |
| `test_get_edit_page_changes_nothing` | `GET /<id>/edit/?title=Hacked` | the saved title is still `Buy milk` | `NoReverseMatch` |
| `test_edit_missing_todo_is_404` | `GET` and `POST` to `reverse("todo_edit", args=[999])` (a `subTest` each) | status 404 | `NoReverseMatch` |
| `test_edit_allows_only_get_head_and_post` | a `subTest` each: `HEAD` → 200; `PUT` and `DELETE` → 405 | the status; nothing changed | `NoReverseMatch` |
| `test_list_has_an_edit_link_for_each_todo` | two to-dos: `Buy milk` and `Say "hi" <b>`; open `/` | exactly `<a class="edit" href="/<id>/edit/" aria-label="Edit Buy milk">Edit</a>`, and exactly `<a class="edit" href="/<id>/edit/" aria-label="Edit Say &quot;hi&quot; &lt;b&gt;">Edit</a>` (the title is escaped) | `AssertionError`: there is no Edit link |
| `test_edit_link_keeps_the_filter` | open `/?show=active` | exactly `<a class="edit" href="/<id>/edit/?show=active" aria-label="Edit Buy milk">Edit</a>` | `AssertionError`: there is no Edit link |
| `test_edit_page_keeps_the_filter` | a `subTest` each: `GET /<id>/edit/` and `GET /<id>/edit/?show=active` | the form's `action` is **exactly** `/<id>/edit/`, or `/<id>/edit/?show=active`; exactly `<a href="/">Cancel</a>`, or `<a href="/?show=active">Cancel</a>` | `NoReverseMatch` |
| `test_save_keeps_the_filter` | a `subTest` each: a good post to `/<id>/edit/?show=completed`; a post with an empty title to the same address | good: redirect to `/?show=completed` exactly. Bad: status 200, the form's `action` is exactly `/<id>/edit/?show=completed` | `NoReverseMatch` |

**A test that protects what already works.** It **passes** before the change, and must still pass
after:

| Test | What it checks |
|---|---|
| `test_list_page_keeps_its_title_and_add_form` | open `/`: exactly `<title>To-do list</title>`, `<h1>To-do list</h1>`, and the add form's title box (with `aria-label="New to-do"`) |

**How to see it fail after the code is written:** in `todo_list.html`, change the title block to
`{% block title %}{% endblock %}`. The test fails. Put it back. This checks the move to `base.html`.

Every test that exists before this change must also still pass. That includes the filter, count
and delete-completed tests (they check the list page that now extends `base.html`), and
`test_get_cannot_change_data`.

### After the rebase on 6 and 7

Added to `test_edit.py` after the rebase, with the field names and values from the merged code:

| Test | What it does | What it checks | How it fails then |
|---|---|---|---|
| `test_edit_page_shows_saved_priority_and_notes` | a High to-do with notes `2 litres`; `GET` its edit page | exactly the High `<option ... selected>`; exactly `<label for="id_notes">Notes:</label>` and the `<textarea>` with `2 litres` and **no** `aria-label` | passes at once if 6 and 7 used `TodoForm`. To see it fail, leave `notes` out of the edit form for a moment, then put it back |
| `test_edit_saves_notes_and_priority` | a `subTest` each: new notes; empty notes; a new priority | the new notes are saved; empty notes are saved as `""`; the new priority is saved | the same as above |
| `test_editing_only_the_title_keeps_the_rest` | post what a browser sends: every field with its saved value, and a new title | only the title changed: notes, priority and due date are the same | protecting: break it by leaving `notes` out of the form for a moment |
| `test_fields_left_out_of_a_post` | a hand-made post with only a title | due date becomes `None`; notes are kept; priority becomes Medium | protecting: it records Django's rules (see Decisions), so a change in Django or in a field is seen. Break it for a moment by removing `default=""` from `notes` in `models.py` (no migration needed for a moment in a test run): notes are then emptied, and the test fails |

## Steps, in order

1. Write the unit tests, the integration tests, and the CUJ step. Run `make test`:
   - the three unit tests fail: two with `AttributeError`, one with `AssertionError` (`12/10/2026`),
   - the 12 new-behaviour integration tests fail as listed,
   - the protecting test passes.
   Run `make test-cuj`: the CUJ test fails with a timeout, because it cannot find "Edit Buy milk".
2. Change `forms.py`: `TodoEditForm`, and `format="%Y-%m-%d"` on the date box.
3. Change `urls.py`. Change `views.py`: `todo_edit`.
4. Add `base.html`. Change `todo_list.html` to extend it, with no other change. Run `make test`: the
   old tests and the protecting test still pass.
5. Add the Edit link to `todo_list.html`. Add `todo_edit.html`.
6. Run `make test`, then `make test-cuj`: every test passes. Then the two deliberate bugs (in the
   unit tests and the protecting test): see each one fail, put the code back, check `git diff`.
7. Run `make run` and open the page:
   - Add a to-do with a date. Press Edit, change the title and the date, press Save.
   - Press Edit, empty the title, press Save: an error, and the box keeps what you typed.
   - On Active, press Edit, then Cancel: you are back on Active. Then Edit and Save: also Active.
   - Make the window narrow, like a phone: the row (title, date, Edit, Done, Delete) still fits,
     and the edit page fits.
   - In the browser's accessibility panel, the link is called "Edit Buy milk".
8. Update `AGENTS.md`.
9. When 6 and 7 are on `main`: rebase, then do "After 6 and 7 are on `main`" with its tests. Run
   `make test` and `make test-cuj` again.
10. Run `uv run python manage.py makemigrations --check --dry-run`: "No changes detected". This
    feature has no migration.
11. Run `make check`. Commit.

## Risks

- **The lost-toggle race.** If someone presses Done in the same few milliseconds as another person
  presses Save, the Done can be lost (see Decisions). We accept it, because `update_fields` would
  break when tags (14) join the form. If it matters later, save with `update_fields` for the plain
  columns only.
- **The CUJ test gets longer.** If the edit page breaks, the one journey stops at the edit step, and
  the Done / Undo / Delete steps do not run until it is fixed. The integration tests still say
  exactly what broke.
- **Moving to `base.html` touches most of `todo_list.html`.** 6, 7 (before) and 10 (after) also
  change it. Their clashes are in the CSS and the row; the rebase steps above say what to keep.
  Search (10) rebases on this feature, so its builder puts its CSS in `{% block style %}`.
- **A crowded row on a phone.** The row now has title, date, Edit, Done, Delete, and after 6 maybe a
  priority label. If it does not fit, let the row wrap (`flex-wrap: wrap`) — a CSS-only change.
- **Search (10) merges after this.** It adds `q` to `list_params`, so the Edit link, the edit form
  and Cancel keep the search with no change here. The search builder should add one test: the Edit
  link on `/?q=milk` ends with `?q=milk`.
- **Exact element tests are strict.** `test_edit_page_shows_the_saved_values` writes out the whole
  title box. If a later feature changes its attributes, that test must change too. That is on
  purpose: it shows the change.

## What happened

The builder followed the plan. These are the places where it did something a little different, and
why.

1. **The starting point** is `main` with wave 1 (5, 12, 11, 8), as the plan says. The code there
   is the same as the plan expects: `TodoForm` with `title` and `due_date`, `page_context`,
   `list_params`, `list_query`, `back_to_list`, and `page_parts` in
   `todos/tests/integration/helpers.py`. `page_parts` can already read every `POST` form's
   `action` (`post_actions`), so the helpers did not change.
2. **The CUJ date.** On `main`, the CUJ test adds "Buy milk" with the date `2026-10-05`, so the
   edit step checks `due 5 Oct 2026`, not `due 12 Oct 2026`.
3. **The label in the CUJ step** is `get_by_label("Title:", exact=True)`, with the colon. The
   visible label is "Title:", and an exact match needs the whole text.
4. **The add form's date box has no `type` in `widget.attrs`.** When Django makes a `DateInput`,
   it moves `type` out of `attrs` into `widget.input_type`. So in
   `test_edit_form_does_not_change_the_add_form`, the date box's `attrs` are exactly `{}`, and the
   test also checks `input_type == "date"`. Before the code this test failed with
   `AttributeError` (as planned), so the wrong `{"type": "date"}` was only seen once the code
   existed. It was fixed in the code commit.
5. **The bad-edit test** checks the title box exactly, with `aria-invalid="true"` and
   `aria-describedby="id_title_error"` when the title has the error. The bad-date case checks the
   date's error list (`id="id_due_date_error"`) and a title box with no error attributes.
6. **`page_context` and `back_to_list` did not change.** The edit view only uses them as they are.
7. **The part for 6 and 7 is not done yet.** The changes in "After 6 and 7 are on `main`" and the
   four tests in "After the rebase on 6 and 7" wait until this branch is rebased on that `main`.

Results before the code (`make test`, `make test-cuj`): the three unit tests failed (two with
`AttributeError: module 'todos.forms' has no attribute 'TodoEditForm'`, one with `AssertionError`:
`value="12/10/2026"`); the 10 integration tests that use `reverse("todo_edit")` failed with
`NoReverseMatch`; the 2 Edit-link tests failed with `AssertionError` (no Edit link); the protecting
test passed. The CUJ test failed with a timeout, waiting for the link "Edit Buy milk".

Deliberate bugs, after the code. Each one was put in, the tests were run, and it was taken out
again; `git diff` showed none of them.

- `self.base_fields["due_date"].widget.attrs["class"] = "edit"` in `TodoEditForm.__init__`:
  `test_edit_form_does_not_change_the_add_form` failed, `{'class': 'edit'} != {}`. The same line
  with `"title"` did **not** fail, as the plan says: Django makes a new title field for each class.
- No `format=` on the date box: `test_date_box_shows_iso_date_in_every_language` failed with
  `value="12/10/2026"`.
- `{% block title %}{% endblock %}` in `todo_list.html`:
  `test_list_page_keeps_its_title_and_add_form` failed: no `<title>To-do list</title>`.

Results after the code: `make test` (Integration 77, Unit 15), `make test-cuj` (CUJ 1) and
`make check` all pass. `makemigrations --check` says "No changes detected".

Looked at by eye at 375 pixels wide (a phone), with Playwright: on the list, each row shows the
title (with the due date under it), then Edit, Done and Delete; a long title wraps, and the page
does not scroll sideways. The edit page shows "Title:" above the title box and "Due date
(optional):" above the date box, each box the full width, then Save and Cancel. An empty title
shows "This field is required." in red above the box. From Active, Edit opens
`/1/edit/?show=active`, and Cancel goes back to `/?show=active`.
