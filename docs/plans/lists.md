# Plan: lists ("Work", "Shopping")

Status: **done.** Approved (third version, with the owner's answers below). Built in three commits (A, B, C); see "What happened".

**The owner's answers:**

1. Deleting a list **deletes the whole list with its to-dos** (`on_delete=CASCADE`). The delete
   button says how many to-dos it will delete.
2. After moving a to-do, the person goes **back to the original list**. (As planned.)
3. **No production data yet** (CONVENTIONS): no back-filling. The migration **deletes** old to-dos
   that have no list. An old user with no list is sent to `/lists/new/`. New people still get
   "My to-dos" at sign-up.

This is feature 13, in wave 5 of [the rollout plan](feature-rollout.md). The merge order in wave 5
is: **13 lists** → 14 tags → 16 drag to reorder. 14 and 16 are built at the same time as this one,
and rebase on it after it merges.

**Where this starts.** `main` after waves 1–4. "How it fails today" in the tests means that `main`.
These are the names this plan uses from earlier features (from their plans; the builder checks them
on `main` first):

- **Accounts (17):**
  - `Todo.owner`: a required **foreign key** (FK: a column that points at a row of another table)
    to the user, `on_delete=CASCADE`.
  - `Todo.objects.for_user(user)`. **Every** to-do query in a view starts with
    `Todo.objects.for_user(request.user)`. Another person's to-do is **404**.
  - `LoginRequiredMiddleware`: every page needs log-in, except views marked
    `@login_not_required` (log-in, `signup`).
  - Settings: `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "todo_list"`,
    `LOGOUT_REDIRECT_URL = "login"`.
  - The view `signup` in `todos/views.py`: `login(request, form.save())`, then
    `redirect("todo_list")` (twice: also when already logged in).
  - No `legacy` user and no back-filling: old rows without a required value are deleted by a data
    function in `todos/data_migrations.py` (CONVENTIONS, "NO PRODUCTION DATA YET").
  - Test helpers in `todos/tests/helpers.py`: `make_user(username)`, `LoggedInTestCase`
    (`cls.user`, `self.make_todo(owner=None, **fields)`).
  - `integration/test_ownership.py`: the 404 **matrix** `test_their_todo_is_404_everywhere`, and
    the **guard** `test_every_url_is_in_the_matrix` (every URL name is in the matrix or in
    `LIST_URLS`).
  - `integration/test_accounts.py`: `test_visitor_cannot_change_anything` posts to every todos URL
    without log-in.
  - `integration/test_owner_migration.py`: finds migrations by their `-n` name ending.
  - The account bar (`Signed in as … / Log out`) at the top of `todo_list.html`.
- **Edit (4):** `TodoEditForm(TodoForm)`, `todo_edit`, `list_url(request)`, and
  `todos/templates/base.html`, which every page extends.
- **Subtasks (15):** a `Subtask` model (`todo` FK to `Todo`), managed on their own page
  `/<id>/subtasks/`. The views find the to-do with
  `get_object_or_404(Todo.objects.for_user(request.user), pk=pk)` and then use `todo.subtasks`.
  There is no `Subtask.objects.for_user`.
- **Repeating (19):** `Todo.next_copy()` makes the next to-do. It lists the copied fields by name. A
  unit test, `test_next_copy_copies_every_field_a_person_can_change`, reads the model's fields.
- **Earlier waves:** `TodoQuerySet` (`remaining()`, `completed()`), `page_context(request, form)`,
  `list_params`, `list_query`, `filter_links`, `back_to_list(request)`, `filter_todos`,
  `search_todos`, `sort_todos`, `sort_options`, and the list footer with the count and "Delete N
  completed to-dos".

## What we want

A person can keep **separate lists**, for example "Work" and "Shopping". They see **one list at a
time**. They can make a new list, rename a list, and delete a list (with its to-dos). They can **move** a to-do
to another of their lists, on the edit page. The count, "delete completed", the filter, search and
sort all work **inside the list they are looking at**.

A new person gets a list called **"My to-dos"** when they sign up. There is no real data yet, so
old to-dos are not kept (see "Old to-dos").

No JavaScript.

## Decisions

### The model: `TodoList`

- A new table, `TodoList`, with three columns: `owner` (FK to the user, `on_delete=CASCADE`),
  `name` (up to 50 characters), `created_at`.
- **The name is unique per owner, and big and small letters count as the same.** One person cannot
  have "Work" and "work", but two people can each have "Work". The database keeps this rule with a
  `UniqueConstraint` on `Lower("name")` and `owner`. (A **constraint** is a rule the database
  itself keeps.) The constraint has a `violation_error_message`, so where Django checks it by itself
  (for example in the admin, where `owner` is a field), the message is friendly too.
- Lists are in the order they were made (`ordering = ["created_at", "pk"]`). So the first list is
  "My to-dos", unless the person deleted it.
- The name `TodoList`, not `List`: `list` is a Python word.

### Every to-do is in exactly one list: `Todo.todo_list`

- `Todo` gets a new FK, **`todo_list`**, to `TodoList`, with `related_name="todos"` and
  `verbose_name="list"` (so its label is "List" in every form and in the admin). It is
  **required**: a to-do never has no list. Then every query is simple, and there is no "no list"
  case to test.
- `on_delete=models.CASCADE` (owner decision). **CASCADE** means: when a list is deleted, the
  database deletes its to-dos too (and their subtasks, which CASCADE from the to-do). Deleting a
  **user** deletes their lists, and so their to-dos.
- In the code, a variable for a list is called `todo_list`, like the field. The view that shows a
  list is also called `todo_list`; inside views we use `current_list` for the list being shown, so
  the two names never meet.

### Ownership: the owner always follows the list

The rule (CONVENTIONS, OWNERSHIP): **`Todo.owner` is always `todo.todo_list.owner`.**

- `Todo.save()` sets it, every time:

  ```python
  def save(self, *args, **kwargs):
      self.owner_id = self.todo_list.owner_id
      super().save(*args, **kwargs)
  ```

  So no view has to remember it, and a bug cannot make them different through `save()`.
- `queryset.update(...)` and `bulk_create` do not call `save()`. We do not use them to change
  `todo_list` (only the data migration does, and it keeps the rule).
- `Todo.owner` stays in the table. Later, sharing (20) and reminders (18) use it: "the list owner".

### Who may see a to-do: through its list

- `TodoList.objects.for_user(user)`: the lists this person may **see and use**. Today: the lists they
  own.
- `TodoList.objects.owned_by(user)`: the lists this person **owns**. Used for the actions only an
  owner may do: rename, delete, the name check, and which list `/` opens.
- Today both give the same rows. Sharing (20) **deletes** `for_user` and puts `visible_to` /
  `editable_by` in its place, so every old caller fails loudly and is checked. `owned_by` stays.
- `Todo.objects.for_user(user)` now goes through the lists:

  ```python
  def for_user(self, user):
      return self.filter(todo_list__in=TodoList.objects.for_user(user))
  ```

  `todo_list__in=<a QuerySet>` makes a **subquery**: one database question inside another ("the
  to-dos whose list is in this group of lists"). It is still one query.
- Subtasks (15) need no change: their views reach a subtask only through
  `Todo.objects.for_user(request.user)` and then `todo.subtasks`, so they follow the list by
  themselves.

### Addresses: one list at a time

| Address | Method | What it does | Name |
|---|---|---|---|
| `/` | GET | Sends the browser to the person's **first own** list. If they own none: to `/lists/new/`. | `home` |
| `/lists/new/` | GET, POST | GET shows the "New list" form. POST makes the list. | `list_create` |
| `/lists/<id>/` | GET | The list page, for one list. (Was `/`.) | `todo_list` |
| `/lists/<id>/add/` | POST | Add a to-do to this list. (Was `/add/`.) | `todo_add` |
| `/lists/<id>/delete-completed/` | POST | Delete the completed to-dos of this list. (Was `/delete-completed/`.) | `todo_delete_completed` |
| `/lists/<id>/edit/` | GET, POST | GET shows the rename form and the "Delete list" button. POST renames. | `list_edit` |
| `/lists/<id>/delete/` | POST | Delete this list **and its to-dos**. | `list_delete` |
| `/<pk>/toggle/`, `/<pk>/delete/`, `/<pk>/edit/`, the subtask addresses | as before | No address change. They now go back to **the to-do's list**. | as before |

- **`/` only redirects** and never makes anything: a `GET` only reads (AGENTS.md). So it does not
  "make a list if there is none"; it sends the person to `/lists/new/`. This case is real: a user
  from before this feature, a user made with `createsuperuser`, or a person who deleted all their
  lists.
- `/` drops any `?show=...`: an old bookmark `/?show=active` opens the first list on "All". Simple
  and harmless.
- The old addresses `/add/` and `/delete-completed/` are gone (404).
- `LOGIN_REDIRECT_URL = "home"`, and `signup` ends with `redirect("home")` (both places). Then
  after log-in and sign-up, the person lands on their first list.
- A list id that is not the person's, or does not exist: **404**. Two small helpers do it, so no view
  can forget:

  ```python
  def get_list(request, list_id):
      """A list this person may use, or 404."""
      return get_object_or_404(TodoList.objects.for_user(request.user), pk=list_id)


  def get_owned_list(request, list_id):
      """A list this person owns, or 404. For rename and delete."""
      return get_object_or_404(TodoList.objects.owned_by(request.user), pk=list_id)
  ```

- **Why the list is in the address, not a hidden field:** the address says which list is open, it
  can be bookmarked, and the add form needs no list choice.

### The list page

From top to bottom:

1. The **account bar** ("Signed in as ana", Log out) — it now lives in `base.html` (see Templates),
   so every page has it.
2. **The lists**: `<nav class="lists" aria-label="Lists">`, one link per list (`TodoList.objects
   .for_user`), in order. The current one has `aria-current="page"` (bold, by the same CSS rule as
   the filter links). Then a link **"New list"**.
3. **The heading** is the list's name: `<h1>Work</h1>`. After it, a link **"Rename or delete"** to
   `/lists/<id>/edit/`, with `aria-label="Rename or delete Work"`. (An **accessible name** is what a
   screen reader says for a link. "Rename or delete" alone would not say which list.)
4. The add form, search, filter, sort, the to-dos and the footer, as before, **for this list only**.

The page `<title>` is "Work – To-do list".

There is **no separate "all my lists" page**: the `<nav>` on every list page is the index.

### Make and rename a list: `TodoListForm`

- A `ModelForm` with one field, `name`, label "Name".
- Django's `CharField` already removes spaces at both ends, and refuses an empty name and a name over
  50 characters.
- **The same name twice:** the form gets the owner, `TodoListForm(data, owner=request.user)`, as a
  **keyword-only argument** (written after `*args`, so it must be given by name: forgetting it is an
  error at once, not a silent bug). `clean_name` looks in `TodoList.objects.owned_by(owner)` for the
  same name, big or small letters (`name__iexact`), not counting the list being renamed. The
  message: `You already have a list called "Work".` Renaming "work" to "Work" is allowed.
- Why not let Django check the constraint by itself here: Django skips a constraint when one of its
  fields (`owner`) is not in the form. So we check in `clean_name`. The database constraint is the
  safety net.
- **Two requests at the same moment** with the same new name can both pass `clean_name`; then the
  database refuses the second one with `IntegrityError`, and the person sees an error page (500).
  This needs two clicks in the same millisecond by the same person. **We accept it.**
- After making a list: go to the new list. After renaming: back to that list.

### Delete a list: the list **and its to-dos** (owner decision)

- Deleting a list deletes every to-do in it. This is the owner's choice.
- **The confirm step is the page we already have.** The list page has no delete button, only the
  link "Rename or delete". That page (`/lists/<id>/edit/`) shows the delete button, and the button
  **says the number**: "Delete list and its 3 to-dos" (or "Delete list" when it is empty). So a
  person always sees what will be lost before they press it. No new page is needed.
- The number comes from one database count, `current_list.todos.count()`, in the key
  `todo_count`. `pluralize` gives "to-do" for 1 and "to-dos" otherwise.
- The view does `current_list.delete()`. Django deletes the to-dos and their subtasks with it.
- If someone adds a to-do between opening the page and pressing the button, it is deleted too,
  although the number did not count it. This needs two tabs; we accept it.
- After a delete: go to `/`, which opens the first list left, or `/lists/new/`.
- **The last list can be deleted.** The "no list" path must work anyway.
- `GET /lists/<id>/delete/` gives 405 ("method not allowed"), by `require_POST`.

### The "New list" page when the person has no list

- It has the account bar (from `base.html`), so the person can still **log out**.
- It has **no Cancel link** when the person has no list: Cancel would go to `/`, which comes back
  here. Cancel is shown only when `lists` is not empty, and goes to `/`.

### Move a to-do: on the edit page

- `TodoEditForm` (4) gets one more field, `todo_list`, a choice box. Its label is "List" (from the
  model's `verbose_name`).
- `TodoForm` (the add form) does **not** get it: the add form posts to `/lists/<id>/add/`, so it
  knows the list. So `TodoEditForm.Meta.fields = TodoForm.Meta.fields + ["todo_list"]`.
- **Only the person's own lists:** `TodoEditForm(..., user=request.user)` (keyword-only) sets
  `self.fields["todo_list"].queryset = TodoList.objects.for_user(user)`. A `ModelChoiceField`
  (Django's choice box for rows of a table) does two jobs with this one line:
  - it **shows** only these lists, and
  - it **refuses** any other id that is posted: `Select a valid choice. That choice is not one of
    the available choices.` So posting another person's list id saves nothing. A test posts exactly
    that.
- `empty_label = None`: no "---------" choice, because a to-do must be in a list.
- After saving, the person goes **back to the list they came from** (the to-do's list when the edit
  page opened), with the same filter. If they moved it, it is gone from that list: that shows the
  move worked. Cancel goes to the same list.
- `Todo.save()` sets the owner from the new list (the OWNERSHIP rule).

### Count, delete completed, filter, search, sort: per list

- `page_context(request, form, current_list)` gets the list. It starts from
  `Todo.objects.for_user(request.user).filter(todo_list=current_list)`, and **every** key comes from that: `todos`
  (after filter, search, sort), `has_todos`, `remaining_count`, `completed_ids`.
- Two new keys, one per line: `current_list`, and `lists` (`TodoList.objects.for_user(request.user)`).
- The helpers that build the address `/lists/<id>/` get the list's **id**:
  `back_to_list(request, list_id)`, `list_url(request, list_id)`, `filter_links(params, list_id)`,
  `sort_options(params, list_id)`. An id, not the list, so `todo_toggle` can call
  `back_to_list(request, todo.todo_list_id)` with no extra database query. (`todo.todo_list_id` is
  the number Django already has in the to-do's row.) `list_params` and `list_query` do not change.
- **Delete completed** deletes only to-dos that are completed, **in this list**, and in the posted
  ids: `Todo.objects.for_user(request.user).filter(todo_list=current_list).completed().filter(pk__in=ids)`. An id
  from another list is ignored, even the person's own.
- **Search looks only in the open list.** "Search every list" is a later feature, if wanted.

### Repeating (19) and subtasks (15)

- `next_copy()` copies `todo_list` too, so the next copy of a repeating to-do is in the **same
  list**. (The owner then follows from the list.) The existing test
  `test_next_copy_copies_every_field_a_person_can_change` fails until this is done, because it
  reads the model's fields: that is its job.
- Subtasks: no change (see "Who may see a to-do").

### New people get "My to-dos": in the sign-up view

- In `signup`, inside `transaction.atomic()`: `user = form.save()`, then
  `TodoList.objects.create_default(user)`, then `login(request, user)`. **`transaction.atomic()`**
  means "all of this, or nothing": we never get a user without a list because of an error in
  between.
- **Why not a signal** (code Django runs by itself after a user is saved): a signal is hidden from a
  beginner reading the view, and it also runs in the admin and in tests. A user made another way has
  no list, and `/` sends them to `/lists/new/`. That is fine.
- `DEFAULT_LIST_NAME = "My to-dos"` is a constant in `models.py`, used by `create_default`.

### Old to-dos: deleted by a data migration (no production data yet)

- Nobody uses the live site yet (CONVENTIONS, owner decision). So we do **not** back-fill: old users
  get **no** list, and old to-dos (which have no list) are **deleted**.
- An old user who logs in lands on `/`, which sends them to `/lists/new/`. That path exists anyway.
- The logic is a normal function in `todos/data_migrations.py`; the migration only calls it
  (CONVENTIONS). Going back does nothing (`noop`): deleted rows cannot come back.
- On a laptop, `make reset` also gives a clean database.

### Ready for sharing (20), but not built

- `TodoList.owner` now; sharing adds members.
- Rename, delete, the name check and `/` already use `owned_by`. Sharing (20) deletes `for_user`
  and `get_list` (CONVENTIONS), so every place that reads lists is found again.
- The sharing plan expects a "lists index" page. **This feature has none**: the lists `<nav>` on the
  list page is the index. Sharing should put "Shared with me" there (flagged for 20).

## What we will not do (yet)

- **No sharing** (feature 20).
- **No "all lists" page**, and no search across lists.
- **No count per list** in the list links (for example "Work (3)").
- **No reordering lists**: they stay in the order they were made.
- **No undo** after deleting a list.
- **No back-filling** of old to-dos into a list (no production data yet).
- **No moving many to-dos at once.** One at a time, on the edit page.
- **No list choice on the add form.** Open the list, then add.
- **No signal** for the default list.

## Changes in behaviour

1. `/` now redirects to the person's first list, or to `/lists/new/`. Log-in and sign-up land there.
2. The list page is `/lists/<id>/`. It shows one list, with links to the others, and its name as the
   heading.
3. A to-do is added to the list that is open. Toggle, delete and edit go back to that list.
4. New pages: "New list" and "Rename or delete". Deleting a list deletes its to-dos; the button
   says how many.
5. The edit page has a "List" choice, with only the person's own lists.
6. The count, delete completed, filter, search and sort only look at the open list.
7. New people get a list "My to-dos" on sign-up. Old to-dos (with no list) are deleted by the
   migration; old users start with no list and are sent to "New list".
8. Any list address of another person, or of a list that does not exist: 404.
9. The account bar is on every page (it moved to `base.html`).
10. The next copy of a repeating to-do is in the same list.

## The changes, one file at a time

### 1. `todos/models.py`

```python
from django.db.models.functions import Lower

DEFAULT_LIST_NAME = "My to-dos"


class TodoListQuerySet(models.QuerySet):
    def for_user(self, user):
        """The lists this person may see and use. Today: the lists they own."""
        return self.filter(owner=user)

    def owned_by(self, user):
        """The lists this person owns. For rename, delete and the name check."""
        return self.filter(owner=user)

    def create_default(self, user):
        return self.create(owner=user, name=DEFAULT_LIST_NAME)


class TodoList(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="todo_lists"
    )
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TodoListQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "owner",
                name="todolist_unique_name_per_owner",
                violation_error_message="You already have a list with this name.",
            ),
        ]

    def __str__(self):
        return self.name
```

- `TodoList` goes **above** `Todo`, because `Todo` points at it.
- In `Todo`, after the other fields (CONVENTIONS field order: the new field comes last):

  ```python
  todo_list = models.ForeignKey(
      TodoList, on_delete=models.CASCADE, related_name="todos", verbose_name="list"
  )
  ```

- `Todo.save()` sets the owner (see "Ownership").
- `TodoQuerySet.for_user` changes (see "Who may see a to-do").
- `Todo.next_copy()` (19) copies `todo_list`.

### 2. `todos/data_migrations.py` — new, the data function

```python
def delete_todos_without_a_list(apps, schema_editor):
    """No production data yet: old to-dos have no list, so they are deleted."""
    Todo = apps.get_model("todos", "Todo")
    Todo.objects.filter(todo_list__isnull=True).delete()
```

- `apps.get_model(...)`: the table **as it was at that migration**, not as it is in `models.py`
  today. That is the Django rule for data migrations.
- Their subtasks go too (CASCADE from the to-do).
- If accounts (17) already made `todos/data_migrations.py`, add this function to it.

### 3. The three migrations, made by Django, with names

Django cannot add a **required** column to a table that has rows, unless it gets one default value
for all of them. There is no good default list. So it is three short steps, like accounts (17):
add the column as "may be empty", delete the rows that are empty, make the column required.

```bash
# Step 1 — models.py has todo_list = ForeignKey(..., null=True) for now
uv run python manage.py makemigrations todos -n todolist
# Step 2
uv run python manage.py makemigrations todos --empty -n delete_todos_without_list
```

In the empty file, add `from todos.data_migrations import delete_todos_without_a_list` and one
line in `operations`:

```python
migrations.RunPython(delete_todos_without_a_list, migrations.RunPython.noop),
```

(`noop` means "going back does nothing here": deleted rows cannot come back, and step 1 going
back removes the column anyway. So the migrations can still be run backwards.)

```bash
# Step 3 — remove null=True from models.py
uv run python manage.py makemigrations todos -n todo_list_required --noinput
```

`--noinput`: Django does not ask for a default for old rows (step 2 deleted them). Check that the
new file is a single `AlterField` with no `default`.

**For the merge queue** (write this in the PR description): the usual "delete our migrations and
run `makemigrations`" gives **one** wrong file here. Instead: delete this branch's three files, then
run the three steps above, in order. The `-n` names stay the same, so the migration test still
finds them.

### 4. `todos/forms.py`

```python
class TodoListForm(forms.ModelForm):
    class Meta:
        model = TodoList
        fields = [
            "name",
        ]

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_name(self):
        name = self.cleaned_data["name"]
        same = TodoList.objects.owned_by(self.owner).filter(name__iexact=name)
        if same.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f'You already have a list called "{name}".')
        return name
```

`TodoEditForm` (4):

```python
class TodoEditForm(TodoForm):
    class Meta(TodoForm.Meta):
        fields = TodoForm.Meta.fields + ["todo_list"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        ...  # the title box changes from feature 4 stay
        self.fields["todo_list"].queryset = TodoList.objects.for_user(user)
        self.fields["todo_list"].empty_label = None
```

### 5. `todos/urls.py`

```python
path("", views.home, name="home"),
path("lists/new/", views.list_create, name="list_create"),
path("lists/<int:list_id>/", views.todo_list, name="todo_list"),
path("lists/<int:list_id>/add/", views.todo_add, name="todo_add"),
path("lists/<int:list_id>/delete-completed/", views.todo_delete_completed, name="todo_delete_completed"),
path("lists/<int:list_id>/edit/", views.list_edit, name="list_edit"),
path("lists/<int:list_id>/delete/", views.list_delete, name="list_delete"),
```

Toggle, delete, edit and the subtask addresses do not change.

### 6. `todos/views.py`

- `get_list`, `get_owned_list` (above), near the top of the file.
- `home`:

  ```python
  def home(request):
      first = TodoList.objects.owned_by(request.user).first()
      if first is None:
          return redirect("list_create")
      return redirect("todo_list", list_id=first.pk)
  ```

- `todo_list(request, list_id)`: `current_list = get_list(...)`; `page_context(request, TodoForm(),
  current_list)`.
- `todo_add(request, list_id)`: `current_list = get_list(...)`. On a good form:
  `form.instance.todo_list = current_list`, `form.save()` (the owner comes from the list), then
  `back_to_list(request, current_list.pk)`. On a bad form: `page_context(request, form,
  current_list)`. The line `form.instance.owner = request.user` from 17 goes away: `save()` does it.
- `todo_toggle`, `todo_delete`: unchanged lookups (`get_object_or_404(Todo.objects.for_user(request.user), ...)`),
  and `back_to_list(request, todo.todo_list_id)`. For delete, keep the id in a variable before
  `todo.delete()`.
- `todo_edit`: `came_from = todo.todo_list_id` before the form; `TodoEditForm(..., user=request.user)`;
  after a good save, `back_to_list(request, came_from)`; Cancel is `list_url(request, came_from)`.
- The subtask views: no change. Their page is `/<id>/subtasks/`, not the list page.
- `todo_delete_completed(request, list_id)`: `current_list = get_list(...)`; delete as in
  Decisions; `back_to_list(request, current_list.pk)`.
- `list_create`, `list_edit`: the standard Django form pattern ("if POST and the form is good,
  save and redirect; else show the form"), with `require_http_methods(["GET", "POST"])`.
  `list_create` sets `form.instance.owner = request.user` before `form.save()`. `list_edit` uses
  `get_owned_list`.
  `list_edit` also gives the page `todo_count` (`current_list.todos.count()`), for the delete
  button.
- `list_delete(request, list_id)`, `require_POST`:

  ```python
  current_list = get_owned_list(request, list_id)
  current_list.delete()  # its to-dos go too (CASCADE)
  return redirect("home")
  ```
- `page_context`, `back_to_list`, `list_url`, `filter_links`, `sort_options`: as in Decisions.
  Every `reverse("todo_list")` becomes `reverse("todo_list", args=[list_id])`.
- `signup`: `transaction.atomic()` with `create_default` (see Decisions); `redirect("home")` in both
  places.

### 7. `config/settings.py`

`LOGIN_REDIRECT_URL = "home"`.

### 8. Templates

- `base.html`: the account bar moves here from `todo_list.html`, inside
  `{% if user.is_authenticated %}`. So every page that extends `base.html` has it (list, edit, the
  list pages). The log-in and sign-up pages extend `registration/account_base.html`, so they do not
  get it.
- `todo_list.html`: the lists `<nav>`, the "New list" link, `<h1>{{ current_list.name }}</h1>` with
  the "Rename or delete" link, the `<title>`. Every `{% url %}` for a list address gets
  `current_list.pk`.
- `list_form.html` (new, extends `base.html`): one page for "New list" and "Rename or delete".
  Heading "New list" or "Rename or delete Work". The name form (button "Save"). Cancel only if
  `lists` (to `/` on "New list", to the list on "Rename"). On the rename page only: a second form,
  `<form class="delete-list" method="post" action="{% url 'list_delete' current_list.pk %}">` with
  the button, on one line so tests can match it:
  `<button type="submit">Delete list{% if todo_count %} and its {{ todo_count }} to-do{{ todo_count|pluralize }}{% endif %}</button>`.
- `todo_edit.html`: no change. The new field is drawn by its loop.

CSS (in `base.html`): `nav.lists` shares the rule of `nav.filters`, with `flex-wrap: wrap` so many
lists fit on a phone.

### 9. `todos/admin.py`

Register `TodoList` (`list_display = ["name", "owner", "created_at"]`). Add `"todo_list"` to the
`Todo` admin `list_display`.

### 10. `AGENTS.md`

- `todos/models.py` row: "`TodoList`: owner, name (unique per owner), created_at. Every `Todo` is in
  one list (`todo_list`, required; deleting a list deletes its to-dos). `Todo.save()` sets the owner from the list.
  `TodoList.objects.for_user(user)` for lists a person uses, `owned_by(user)` for owner-only
  actions. `Todo.objects.for_user` goes through the lists."
- `todos/urls.py` row: the new addresses.
- `todos/views.py` row: "`get_list` / `get_owned_list` give one list or 404. A list with to-dos
  cannot be deleted."
- New rows: `todos/data_migrations.py`, `todos/templates/todos/list_form.html`.
- Rules: "Rename and delete of a list are owner-only: use `owned_by` / `get_owned_list`."

## Tests (`todos/tests/`)

We write these **first**, and run them **before** changing the code. Elements are checked exactly
with `assertContains(..., html=True)`; redirects with `response["Location"]`, exactly.

### The test helpers (`todos/tests/helpers.py`, from 17) change

- `make_user(username)` also calls `TodoList.objects.create_default(user)`, the same as `signup`.
- `LoggedInTestCase.setUpTestData` keeps `cls.todo_list` (the user's "My to-dos").
- `self.make_todo(todo_list=None, **fields)` makes a to-do in `todo_list or self.todo_list`. (No
  `owner` argument any more: the owner follows the list.)
- `self.list_url(todo_list=None, query="")` gives `/lists/<id>/` + `query`, for the old tests that
  open `/` or expect a redirect to `/`.

Old tests change **setup and addresses only, never an assertion about behaviour**: `make_todo`
calls that passed `owner=` pass a list of that user instead, and `"/"` becomes `self.list_url()`.
Do it in its **own commit**, so a reviewer can check exactly that.

In the new tests: `ana` (the `LoggedInTestCase` user) has "My to-dos" (`self.todo_list`) and
"Work"; `ben` (from `make_user("ben")`) has "My to-dos" and "Secret".

How most new tests fail today: `ImportError` (no `TodoList`) or `NoReverseMatch` (no address
`list_create`, ..., or `todo_list` with an id).

### Bottom: unit tests (`todos/tests/unit/test_lists.py`, new)

| Test | What it checks | How it fails today |
|---|---|---|
| `test_lists_for_user_are_only_their_own` | `TodoList.objects.for_user(ana)` and `owned_by(ana)` are each exactly ana's two lists, in the order made | `ImportError` |
| `test_save_sets_the_owner_from_the_list` | `Todo(title="x", todo_list=work, owner=ben).save()` → `owner` is ana; then move it to ben's Secret and save → `owner` is ben | `ImportError` |
| `test_todos_for_user_go_through_the_list` | **a guard for sharing:** make a to-do in ben's list, then force `owner=ana` with `Todo.objects.filter(pk=...).update(...)` (which skips `save()`); it is in `Todo.objects.for_user(ben)` and not in `for_user(ana)`. This proves the **list** decides, which sharing needs | `ImportError` |
| `test_next_repeat_stays_in_the_same_list` | a weekly to-do in Work: `next_copy().todo_list` is Work | `ImportError` |
| `test_create_default_makes_my_todos` | `create_default(user)` makes one list "My to-dos", owned by `user` | `ImportError` |
| `test_make_user_has_my_todos` | `make_user("cai")` has exactly one list, "My to-dos" | `ImportError` |
| `test_name_unique_per_owner_ignoring_case` | a second "work" for ana raises `IntegrityError` | `ImportError` |
| `test_two_people_may_use_the_same_name` | ben can make "Work" | `ImportError` |
| `test_constraint_message` | `TodoList(owner=ana, name="WORK").validate_constraints()` raises `ValidationError` with `You already have a list with this name.` | `ImportError` |
| `test_deleting_a_list_deletes_its_todos` | Work has a to-do with a subtask; `work.delete()` → the list, the to-do and the subtask are gone; ana's My to-dos and its to-do stay | `ImportError` |
| `test_deleting_a_user_deletes_their_lists_and_todos` | delete ben → his lists and to-dos are gone; ana's stay | `ImportError` |
| `test_list_form_refuses_a_name_already_used` | `TodoListForm({"name": " WORK "}, owner=ana)` is not valid; error `You already have a list called "WORK".` | `ImportError` |
| `test_list_form_may_rename_a_list_to_itself` | renaming Work to "work" is valid | `ImportError` |
| `test_list_form_needs_a_name_up_to_50` | `"   "` and 51 letters are not valid | `ImportError` |
| `test_add_form_has_no_list_field` | `"todo_list" not in TodoForm().fields` | passes today — a protecting test; see it fail by adding `"todo_list"` to `TodoForm.Meta.fields` for a moment |
| `test_edit_form_offers_only_own_lists` | `TodoEditForm(user=ana).fields["todo_list"].queryset` is exactly ana's lists; `empty_label` is `None` | `TypeError` (no `user` argument) |
| `test_edit_form_refuses_another_users_list` | `TodoEditForm({"title": "x", "todo_list": secret.pk}, instance=todo, user=ana)` is not valid, with the error on `todo_list` | `TypeError` |

Feature 4's `test_edit_form_has_every_field_a_person_can_change` now expects `todo_list` too; it
reads the model, so it needs no change. 19's `test_next_copy_copies_every_field_a_person_can_change`
fails until `next_copy` copies `todo_list` (that shows the gap first).

### Middle: integration tests (`todos/tests/integration/test_lists.py`, new)

| Test | What it does | What it checks |
|---|---|---|
| `test_home_goes_to_the_first_list` | ana opens `/` | redirect to `/lists/<my-todos>/` exactly |
| `test_home_with_no_list_goes_to_new_list` | ana deletes her empty lists (in the database), opens `/` | redirect to `/lists/new/` exactly |
| `test_no_list_new_list_page` | the same ana opens `/lists/new/` | the account bar's Log out form is there (exact element); there is no `<a>` Cancel (checked on the exact `<form>` element of the page, not page-wide) |
| `test_login_and_signup_land_on_the_first_list` | log in with the form; sign up a new person (subTests) | the redirect chain ends at `/lists/<their my-todos>/` |
| `test_signup_makes_my_todos` | sign up a new person through the page | exactly one list, "My to-dos", owned by them |
| `test_list_page_shows_only_that_list` | a to-do in each of ana's lists; open Work | the `<ul>` has exactly the Work to-do (exact element); `<h1>Work</h1>` |
| `test_list_links` | open Work | exactly `<nav class="lists" aria-label="Lists">` with both links, `aria-current="page"` on Work, and "New list" |
| `test_add_goes_into_the_open_list` | post to `/lists/<work>/add/?show=active` | the to-do is in Work, owner ana; redirect `/lists/<work>/?show=active` |
| `test_create_list` | post `name=Shopping` to `/lists/new/` | one new list, owner ana; redirect to it |
| `test_create_list_with_a_used_name` | post `name=work` | status 200, the error message; no new list |
| `test_rename_list` | post `name=Office` to `/lists/<work>/edit/` | the name is Office; redirect `/lists/<work>/` |
| `test_delete_button_says_how_many` | GET `/lists/<work>/edit/` with 0, 1 and 3 to-dos in Work (subTests) | exactly `<button type="submit">Delete list</button>`, `...Delete list and its 1 to-do</button>`, `...Delete list and its 3 to-dos</button>` |
| `test_delete_list_deletes_its_todos` | Work has 2 to-dos; post to `/lists/<work>/delete/` | the list and both to-dos are gone; ana's My to-dos to-do stays; redirect to `/` |
| `test_delete_last_list_goes_to_new_list` | delete both of ana's lists, then `GET /` | redirect `/lists/new/` |
| `test_delete_list_refuses_get` | GET `/lists/<work>/delete/` | 405; the list still exists |
| `test_count_is_per_list` | 2 open to-dos in My to-dos, 1 in Work; open Work | exactly `<p class="count">1 item left</p>` |
| `test_delete_completed_only_in_this_list` | a completed to-do in each list; post **both** ids to `/lists/<work>/delete-completed/` | only Work's is deleted; the button on Work said "Delete 1 completed to-do" |
| `test_search_is_per_list` | "Buy milk" in each list; `/lists/<work>/?q=milk` | the `<ul>` has exactly one item |
| `test_toggle_and_delete_go_back_to_the_todos_list` | toggle and delete (subTests) a Work to-do, with `?show=active` | redirect `/lists/<work>/?show=active` |
| `test_edit_page_list_choice` | GET the edit page of a to-do | exactly `<select name="todo_list" id="id_todo_list">` with ana's two lists, the current one `selected`, no empty option; the label is `List:` |
| `test_move_todo_to_another_list` | post the edit form with `todo_list=<work>` for a My to-dos to-do | the to-do is in Work; redirect to `/lists/<my-todos>/` (where it came from) |
| `test_move_to_another_users_list_is_refused` | post `todo_list=<secret>` | status 200; exactly the `<ul class="errorlist">` with `Select a valid choice...`; the to-do is still in My to-dos, owner still ana |
| `test_missing_list_is_404` | each list address with id 999 (subTests) | 404 |

### Middle: accounts' matrix and guard (`todos/tests/integration/test_ownership.py`, changed)

- `LIST_URLS` (the guard's list of addresses that take **no** to-do id) becomes the **list
  matrix**: for each row, ana tries **ben's** list "Secret", in a `subTest`, and gets **404**, and
  ben's list and to-dos are **exactly the same** afterwards (a snapshot before and after). For each
  row, the same request on ana's own list does **not** give 404.

  | URL name | Method | Data |
  |---|---|---|
  | `todo_list` | GET | — |
  | `todo_add` | POST | a title |
  | `todo_delete_completed` | POST | ben's completed id |
  | `list_edit` | GET | — |
  | `list_edit` | POST | `name=Hacked` |
  | `list_delete` | POST | — (Secret has a to-do; both must still exist afterwards) |

- `home` and `list_create` take no id: they go in a small `NO_OBJECT_URLS` set in the guard, so
  `test_every_url_is_in_the_matrix` still knows every name.
- The to-do rows of the matrix (toggle, delete, edit, subtasks) stay. They now pass **through the
  list**.
- Signed-out: accounts' `test_visitor_cannot_change_anything` already posts to **every** URL name,
  so the new addresses are covered there with **no new test**. Give it the `list_id` argument for
  the new list addresses.

How it fails today: `NoReverseMatch` for the new names.

### The data migration (`todos/tests/integration/test_lists_migration.py`, new)

A `TransactionTestCase` (a test case that really changes the database tables, instead of undoing
everything in one transaction; migrations need that). With Django's `MigrationExecutor` (the part
of Django that runs migrations, which a test can tell "go back to here" and "go forward to there"),
go back to `..._todolist`, make a user with two old to-dos (no list) and one to-do in a list, with
the old models, then go forward to `..._delete_todos_without_list`. Check: the two old to-dos are
gone; the one in a list stays; the user still exists and has **no** new list (no back-filling).
Then go back one step (the `noop`), to show going back works. At the end, go forward to the newest
migration.

The test finds the migrations **by their `-n` name ending**, like `test_owner_migration.py` does,
so the merge queue can renumber them. How it fails today: the migrations do not exist.

### Top: CUJ tests (`todos/tests/cuj/test_journeys.py`)

A **new journey**, so a new test, `test_keep_two_lists_apart`:

1. Sign up (accounts' step). The heading is "My to-dos".
2. Click "New list", type "Shopping", Save. The heading is "Shopping".
3. Add "Buy milk". It is a list item.
4. Click the link "My to-dos" in the lists. `Nothing to do yet` is visible.
5. Add "Write report", press its Edit link, choose List "Shopping", Save.
6. Click "Shopping": the list has exactly two items, "Buy milk" and "Write report".
7. Click "Rename or delete": the button says "Delete list and its 2 to-dos". Press it: the page
   shows "My to-dos", and "Shopping" is no longer in the lists.

How it fails today: there is no "New list" link, so Playwright times out after 5 seconds.

**The old CUJ tests** (`test_plan_and_finish_a_todo`, `test_sign_up_and_see_only_my_own_list`)
need **no change in their steps**, but they only pass **because of** this feature's changes:
`make_user` now makes "My to-dos", and log-in and sign-up now go to `home`, which opens it. Before
those two changes, they would land on `/`, with no list page. Run them; if one of them checks the
old `<h1>` text, update that one assertion and say so in the PR.

## Steps, in order

1. Change the test helpers; change the old tests to use them (own commit). They fail with
   `ImportError` / `NoReverseMatch` — expected.
2. Write the new unit, integration, migration and CUJ tests, and the matrix changes. Run
   `make test` and `make test-cuj`; see them fail as listed. Show the output.
3. `models.py` with `null=True` for now → migration `todolist`. `data_migrations.py` → migration
   `delete_todos_without_list`. Remove `null=True` → migration `todo_list_required` (section 3).
4. `forms.py`, `urls.py`, `views.py` (with `signup`), `settings.py`, the templates, `admin.py`,
   `next_copy`.
5. `make test`, `make test-cuj`: everything passes. Break `test_add_form_has_no_list_field` on
   purpose (add `"todo_list"` to `TodoForm`), see it fail, put it back. `git diff` must not show it.
6. **Try the migration on an old database:** copy a laptop `db.sqlite3` that has users and to-dos
   (from before this branch), run `uv run python manage.py migrate` on the copy: the old to-dos are
   gone, the users stay, and logging in goes to "New list". Then `migrate todos <the migration
   before todolist>` to check that going back works.
7. `make run`: make lists, move a to-do, open "Rename or delete" on a full list (the button says
   the number), delete it, delete the last one (then `/` shows "New list" with Log out and no Cancel). Make the window narrow, like a
   phone: the list links wrap.
8. `uv run python manage.py makemigrations --check --dry-run`: "No changes detected".
9. Update `AGENTS.md`. `make check`. Commit. In the PR description, write the three-step migration
   recipe for the merge queue.

## Risks

- **Big diff in old tests.** Every test that makes a to-do or opens `/` changes. Mitigation: the
  helpers, one separate commit, setup and addresses only.
- **The migration needs three steps.** The usual merge-queue recipe gives a wrong single migration.
  The PR carries the recipe; the merge queue runs it, then the migration test, then step 6.
- **Tags (14) rebase on this.** Tag filtering must work **inside** the open list; their
  `reverse("todo_list")` calls need the list id; tags belong to the **list owner** (CONVENTIONS).
- **Drag to reorder (16) rebases on this.** Its plan reads the list with
  `get_object_or_404(TodoList, pk=list_pk, owner=request.user)` — a **raw owner filter**. It must
  use `get_list(request, list_pk)` instead, or sharing (20) cannot find and change it. The order is
  per list, and moving a to-do on the edit page must put it at the end of the new list (16's job:
  `"todo_list" in form.changed_data`).
- **Deleting a list loses its to-dos for good** (owner decision). The button states the number,
  and it is on a separate page, not on the list page. There is no undo.
- **The migration deletes old to-dos.** Fine only while there is no production data (CONVENTIONS).
  If the owner announces a launch before this merges, stop and plan a back-fill instead.
- **Sharing (20) expects a lists index page.** There is none; the lists `<nav>` is the index (see
  Decisions).
- **Two requests with the same new list name at the same moment** → one 500 error page. Accepted.
- **Case-insensitive names** only cover A–Z in SQLite (`Lower` and `iexact` are ASCII-only there).
  "Ärger" and "ärger" count as different. Acceptable.
- **Names from earlier plans.** If 15, 17 or 19 merged with other names, the builder adapts the
  names and keeps the rules: one entry point for lists, to-dos (and so their subtasks) visible through their
  list, the owner always the list owner.

## Owner answers (decided)

1. Deleting a list deletes its to-dos (CASCADE). The button on the "Rename or delete" page says how
   many.
2. After moving a to-do, the person goes back to the original list.
3. No production data yet: the migration deletes old to-dos; no back-filling.

## What happened

Built on `main` after accounts (everything up to `0009_todo_owner_required`), in three commits:
**A** (the plumbing; the old tests change setup and addresses only; green), **B** (the behaviour
tests; red for the reasons below), **C** (the feature; green). These are the places where the build
is different from the plan, and why.

1. **Step A is bigger than "helpers only".** With a required `todo_list`, the old suite can only be
   green if the model, the three migrations, `Todo.save()`, the new addresses (`/` → first list,
   `/lists/<id>/`, add, delete completed), `create_default` in `signup`, the copy's `todo_list` in
   `next_values()` and the edit form's list box (only the person's lists) are already there. So in
   B some plan tests passed at once (they are **protecting** tests: the owner rule in `save()`,
   the edit form's own lists, a move into ben's list, the add form without a list box, the
   migration). Each of them was shown failing with a deliberate bug (below).
2. **The edit form's list box is not required.** A browser always sends it. A hand-made post
   without it (many old tests post only a title) keeps the to-do in its list, like a missing
   priority is Medium (`clean_todo_list`). So the `<select>` has no `required` attribute, exactly
   as the plan's element. Unit test: `test_edit_form_without_a_list_keeps_the_list`.
3. **Test helpers** are in `todos/tests/integration/helpers.py` (accounts put them there, not in
   `todos/tests/helpers.py`). New: `first_list(user)`, `list_path(list_id, query="")`; in
   `LoggedInTestCase`: `cls.todo_list`, `make_todo(todo_list=None, **fields)`,
   `list_url(todo_list=None, query="")`, `add_url(...)`, `delete_completed_url(...)`,
   `self.list_footer(...)` and `self.delete_completed_form(...)`. `title_element` builds the link
   from `todo.todo_list_id`. `log_in()` expects `/` then the first list. `page_parts(...)
   .current_links` leaves out the lists `<nav>` (its marked link is in `.current_lists`), so the old
   filter tests still prove "exactly one filter link is marked". Unit tests that call
   `full_clean()` pass `owner` and `todo_list` (the owner is set by `save()`); the admin helper in
   `test_repeat.py` sends `todo_list`, like the admin page.
4. **No real browser** (owner decision). The journey `test_keep_two_lists_apart` uses the test
   client: it follows the links ("New list", "My to-dos", "Edit Write report", "Rename or delete
   Shopping") and presses the page's own buttons with CSRF checks on. `press()` takes
   `lands_on=HOME` (through `/` to the first list) or a function (an address known only after the
   press). The old journeys changed only that: log-in and sign-up now land through `/`.
5. **Old assertions changed on purpose (in B, red first):** the list page's `<h1>` and `<title>`
   name the list (`test_list_page_keeps_its_title_and_add_form`, `test_page_title_names_the_search`).
   With a search: `Search: milk – My to-dos – To-do list`.
6. **The 404 matrix** gets `LIST_MATRIX` (the list page, add, delete completed, rename GET and
   POST, delete; each on a fresh list of ben's with an open to-do, a step and a completed to-do;
   whole-table snapshots of lists, to-dos and steps), and the same rows on ana's own list are not
   404. `home` and `list_create` are in `NO_OBJECT_URLS`. The walk over the whole URL resolver
   knows every name. **The canary:** ben's list's NAME carries the word too, and the canary also
   opens `home`, "New list", "Rename or delete" and their error pages. **The source guard** covers
   `TodoList`: `TodoList.objects` must go on with `.for_user(`, `.owned_by(` or `.create_default(`;
   `get_object_or_404(TodoList, ...)` with a raw owner filter is caught.
7. **Admin:** `TodoList` is registered (name, owner, created). In the `Todo` admin the owner is
   read-only (it follows the list); the list is a field and a column.
8. **CSS** for `nav.lists` is in the list page's own `{% block style %}`, not `base.html`: only that
   page has the nav. The middleware sends a visitor's `POST` to `?next=/` via `reverse("home")`.
9. The steps page's "Back to the list" and the edit page's Cancel go to the to-do's own list.

### Red and green

- **A** (`lists-A-check.txt`): `make check` passed. Integration 292, Unit 117, CUJ 6.
- **B** (`lists-B-red-test.txt`, `lists-B-red-cuj.txt`): Integration 298 passed, 31 failed, 11
  errors; Unit 131 passed, 1 failed, 5 errors; CUJ 6 passed, 1 failed. The reasons: the new
  addresses answer 404 (create, rename, delete, the visitor tests), `NoReverseMatch` for
  `list_edit` / `list_delete` (the matrix rows, the canary), `ImportError` for `TodoListForm`, the
  list page shows every to-do of the person (only-that-list, count, delete completed, search), no
  lists nav and the old heading, `/` with no list is 404, a move goes back to the new list, the
  guard for sharing (`for_user` still asked the owner, not the list), and the journey has no
  "My to-dos" heading.
- **C** (`lists-C-green-test.txt`, `lists-C-green-cuj.txt`, `lists-C-check.txt`): Integration
  329, Unit 137, CUJ 7 passed; `make check` passed (473 tests, "No changes detected").

### Deliberate bugs, one at a time, each put back (`lists-deliberate-bugs.txt`)

| Bug | Caught by |
|---|---|
| `list_edit` opens any list (another person's id) | the list matrix (GET and POST rows), the guard |
| `list_delete` deletes any list | the list matrix, `test_missing_list_is_404`, the guard |
| `get_list` (list page, add, delete completed) opens any list | the list matrix (3 rows), the guard |
| `list_create` takes a posted owner | `test_create_list_ignores_a_posted_owner` |
| the edit form offers every list (a to-do moves into ben's list) | 2 unit tests, `test_edit_page_list_choice`, `test_move_to_another_users_list_is_refused`, `test_my_todo_cannot_move_into_their_list`, the canary |
| the name check is exact, not ignoring case | `test_list_form_refuses_a_name_already_used`; the two pages hit the database constraint (500) |
| deleting a list leaves its to-dos (`DO_NOTHING`) | the unit and integration delete tests, the matrix's "my list" row, the journey |
| `Todo.save()` keeps a wrong owner | `test_save_sets_the_owner_from_the_list` |
| the add form gets the list box | `test_add_form_has_no_list_field` and 46 more |
| the data migration deletes nothing | the migration tests |

### The migration, checked (`lists-migration-old-data.txt`, `lists-migration-empty.txt`)

- A database at `0009` with two users, six to-dos and six steps: `migrate` applied the three steps;
  after it, 2 users, 0 to-dos, 0 steps, 0 lists. Ana logs in: `/` → `/lists/new/` (200). Then
  `migrate todos 0009_todo_owner_required` unapplied the three, and `migrate` applied them again.
- An empty database: `migrate` from nothing, back to `0009` and forward again; `makemigrations
  --check --dry-run`: "No changes detected".

**Making the migrations again (for the merge queue).** The usual "delete our migrations and run
`makemigrations`" gives ONE wrong file. Instead, delete this branch's three files, then:

```bash
# 1. In models.py, give Todo.todo_list null=True for a moment.
uv run python manage.py makemigrations todos -n todolist
# 2. The data step: an empty migration, then add ONE line to its operations:
#    migrations.RunPython(delete_todos_without_a_list, migrations.RunPython.noop),
#    with `from todos.data_migrations import delete_todos_without_a_list` at the top.
uv run python manage.py makemigrations todos --empty -n delete_todos_without_list
# 3. Take null=True away again.
uv run python manage.py makemigrations todos -n todo_list_required --noinput
```

Step 3 must be a single `AlterField` with no `default`. The `-n` names stay, so
`test_lists_migration.py` finds them by their name ending.

### Checked by eye (headless Chrome, 1280 × 800)

`runserver` on a free port with a fresh database; a test user signed up through the real sign-up
form, a list "Work" made through "New list" and to-dos added through the add forms; Chrome got the
pages through a small local proxy that adds the session cookie; then the server was stopped and the
database deleted.

- **The list page with two lists** (`lists-page-1280.png`): "My to-dos  **Work**  New list" above the
  heading (Work bold, not underlined, like the chosen filter), the heading "Work", the small
  "Rename or delete" link under it, then the add form, search, filter, sort and the three Work
  to-dos; the pane hint on the right.
- **New list** (`lists-new-1280.png`): the account bar, "New list", the Name box (focused), Save and
  Cancel.
- **Rename or delete** (`lists-rename-delete-1280.png`): "Rename or delete Work", the box with
  "Work", Save and Cancel, a thin line, then the button "Delete list and its 3 to-dos".

### For tags (14) and reorder (16), building on this branch

`Todo.todo_list` (FK, `related_name="todos"`), `TodoList` (`owner`, `name`, `created_at`),
`TodoList.objects.for_user(user)` / `.owned_by(user)` / `.create_default(user)`,
`DEFAULT_LIST_NAME`, `get_list(request, list_id)` and `get_owned_list(request, list_id)` in
`views.py`, `back_to_list(request, list_id)`, `list_url(request, list_id)`,
`page_context(request, form, current_list)`, `filter_links(params, list_id)`,
`sort_links(params, list_id)`, `select_base(params, list_id)`. URL names: `home`, `list_create`,
`todo_list` / `todo_add` / `todo_delete_completed` / `list_edit` / `list_delete` (each with
`list_id`). A new address with a list id goes in `LIST_MATRIX`; one with no id in
`NO_OBJECT_URLS`.
