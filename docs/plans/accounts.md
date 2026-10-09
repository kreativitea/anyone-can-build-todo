# Plan: user accounts (feature 17)

Status: **done.** Approved with the owner's answers (below, "Owner answers"). Wave 4, built alone. The
first version was checked by an adversarial review (partly in a real browser). Every finding is
fixed. Built in three commits (A, B, C); see "What happened".

> **This changes the most basic idea of the app.** Today there are no accounts, and everyone who
> opens the site sees the **same list**. After this feature, each person **signs up**, **logs in**,
> and sees **only their own to-dos**. A visitor who is not logged in sees only the log-in and
> sign-up pages. The owner approved this change.

**Assumed base:** `main` after waves 1–3: due date (5), count (12), delete completed (11), filter
(8), priority (6), notes (7), edit (4), search (10), sort (9), repeating (19), subtasks (15). The
builder uses the real names from `main`; names below that come from other plans are marked "(from
N)". This plan relies on:

- Django 5.2 (from `uv.lock`). It has `LoginRequiredMiddleware` (new in 5.1).
- `todos/templates/base.html` (from 4): the `<head>` and shared CSS. Every page extends it, and it
  shows Django `messages`.
- `TodoQuerySet` with `remaining()`, `completed()`, and `with_subtask_progress()` (from 15).
- `page_context(request, form)`, `list_params`, `list_query`, `back_to_list`, `list_url`; the views
  `todo_list`, `todo_add`, `todo_toggle` (posts the wanted state, from 19), `todo_delete`,
  `todo_delete_completed`, `todo_edit`, and the subtask views and page `/<id>/subtasks/` (from 15).
- `todos/tests/integration/helpers.py`: the one shared file for test helpers.
- `config/settings.py` already has `django.contrib.auth`, `AuthenticationMiddleware`, the four
  password validators, and, when `DEBUG` is off, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  HTTPS redirect and HSTS.

## What we want

1. A new person can **sign up** with a username and a password, and is then logged in.
2. A person can **log in** and **log out**.
3. Every to-do has an **owner**: the person who added it.
4. A person sees, counts, changes and deletes **only their own** to-dos. Another person's to-do
   looks like it **does not exist** (404).
5. The to-dos that exist today are **not lost**.

## Decisions

### Use what Django already has: `django.contrib.auth`

- **Log in:** Django's `LoginView`. **Log out:** Django's `LogoutView`. In Django 5, log out accepts
  **`POST` only**, so it is a button in a small form, not a link. This matches our rule "change data
  only with `POST`".
- **Sign up:** a small function view of our own, `signup`, with Django's `UserCreationForm`. Django
  has the form but no sign-up view. The form checks the password with the four **password
  validators** already in `settings.py` (too short, too common, only numbers, too like the
  username). After a good sign-up, the view calls `login(request, user)`.
- **Addresses** (in `config/urls.py`): `/accounts/login/`, `/accounts/logout/`, `/accounts/signup/`.
  We do **not** use `include("django.contrib.auth.urls")`: it also adds the password-reset pages,
  which need email.
- **Settings:** `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "todo_list"`,
  `LOGOUT_REDIRECT_URL = "login"`. (Lists, 13, changes `LOGIN_REDIRECT_URL` to `"home"`.)
- `LoginView(redirect_authenticated_user=True)`: a logged-in person who opens the log-in page goes
  to the list. `signup` does the same.
- **The `next` address.** After log-in, Django sends the person to the page they asked for
  (`?next=/`). Django checks that `next` is on our own site. A test protects this.

### Every page needs log-in: a small `LoginRequiredMiddleware`

A **middleware** is code that runs for every request, before the view. With Django's
`LoginRequiredMiddleware`, **every** view needs log-in by itself, so a new view cannot forget it.
(With `@login_required` on each view, a new view could forget.)

- Views for visitors are marked `@login_not_required`. Django already marks `LoginView` and the
  admin's own log-in page. We mark `signup`, and **`LogoutView`**: a person whose session has ended
  and who presses "Log out" in an old tab is simply logged out and sent to the log-in page, instead
  of being asked to log in so they can log out.
- **One problem, found in a real browser:** a visitor whose session ended presses `Done` (a
  `POST` to `/5/toggle/`). Django's middleware sends them to `/accounts/login/?next=/5/toggle/`.
  After log-in, the browser does a `GET` of `/5/toggle/`, which answers **405** ("method not
  allowed"). **We recommend** a 5-line subclass in `config/middleware.py`: for a request that is not
  a `GET`, `next` is the list page.

```python
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import resolve_url
from django.urls import reverse


class LoginRequired(LoginRequiredMiddleware):
    """Django's, but a POST (or other change) sends the person back to the list after log-in."""

    def handle_no_permission(self, request, view_func):
        if request.method == "GET":
            return super().handle_no_permission(request, view_func)
        return redirect_to_login(
            reverse("todo_list"),
            resolve_url(self.get_login_url(view_func)),
            self.get_redirect_field_name(view_func),
        )
```

  The `POST` itself is **not** done after log-in. The person sees their list and presses again.
- Static files are served by WhiteNoise before this middleware, so they are not affected.
- **The admin:** `/admin/login/` stays open. But `/admin/` and every other admin page now send a
  visitor to **our** log-in page (`/accounts/login/?next=/admin/`), not the admin's. A staff person
  logs in there and is sent on to the admin. This is fine; a test pins it.

### Ownership: one owner per to-do, one way to ask for to-dos

```python
owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="todos")
```

- A **ForeignKey** is a column that points at a row in another table: here, from a to-do to a user.
- `settings.AUTH_USER_MODEL`, not `User`, is Django's advice.
- `on_delete=CASCADE`: if a user is deleted, their to-dos are deleted too. Nobody else can see them.
- **The owner is never in a form.** `TodoForm` and `TodoEditForm` get no `owner` field. The view
  sets it, so a person cannot post `owner=5` to give a to-do to someone else.

A **QuerySet** is Django's "a question to the database that is not asked yet"; you can add more
filters to it. `TodoQuerySet` gets one new method:

```python
def for_user(self, user):
    return self.filter(owner=user)
```

**The rule: every to-do query in a view starts with `Todo.objects.for_user(request.user)`.** Never
`Todo.objects.all()`, never `get_object_or_404(Todo, ...)`. **Only change the start** of each line;
keep every method that is already on it (`with_subtask_progress()`, `completed()`, the sort's
`order_by`, …):

| Where | Before | After |
|---|---|---|
| `page_context` — the list | `Todo.objects.with_subtask_progress()` | `Todo.objects.for_user(request.user).with_subtask_progress()` |
| `page_context` — the count | `Todo.objects.remaining().count()` | `Todo.objects.for_user(request.user).remaining().count()` |
| `page_context` — completed ids | `Todo.objects.completed()…` | `Todo.objects.for_user(request.user).completed()…` |
| `todo_delete_completed` | `Todo.objects.completed().filter(pk__in=ids)…` | `Todo.objects.for_user(request.user).completed().filter(pk__in=ids)…` |
| `todo_toggle`, `todo_delete`, `todo_edit`, the subtask page | `get_object_or_404(Todo, pk=pk)` | `get_object_or_404(Todo.objects.for_user(request.user), pk=pk)` |
| `todo_add` | `form.save()` | `form.instance.owner = request.user`, then `form.save()` |
| filter, search, sort | change the list from `page_context` | no change: they get the scoped list |
| repeating (19): `next_values()` | copies title, notes, priority, repeat | also copies `owner` |

**Subtasks** have no owner of their own: a step's owner is its to-do's owner. Each subtask view
first finds the to-do **through the owner**, then finds the step **inside that to-do**:

```python
todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
subtask = get_object_or_404(todo.subtasks, pk=subtask_pk)
```

`todo.subtasks` is the related manager from `related_name="subtasks"` (15). No second entry point.

### 404, not 403, for another person's to-do

**403** means "it exists, but you may not touch it". **404** means "not found". With 403, a person
could try id 1, 2, 3… and learn how many to-dos other people have. With 404, another person's to-do
looks exactly like one that does not exist. The rule above gives 404 for free: the to-do is not in
the QuerySet.

### An automatic guard

A rule in a document can be forgotten. So a unit test reads the source code of `todos/views.py` and
`todos/forms.py` (with Python's `inspect.getsource`) and fails if it finds `Todo.objects.` not
followed by `for_user(`, any `Subtask.objects.`, or `get_object_or_404(Todo` / `get_object_or_404(
Subtask` not followed by `.objects.for_user(`. Model code (`models.py`, e.g. repeating's
`Todo.objects.filter(pk=self.pk)` on a to-do already checked) and management commands (18) are not
read. Sharing (20) deletes `for_user` and changes this guard to its own entry points.

### The to-dos that exist today: deleted (there is no production data yet)

The owner decided: this is a new app, and **nobody uses the live site yet** (until the owner
announces a launch). So there is **no back-filling**: we do not invent an owner for old to-dos. Old
to-dos without an owner are **deleted**. Their subtasks go with them (CASCADE).

The owner is **required**, and the database cannot make a required column while rows have no value
for it. Django also cannot know the table will be empty. So the simplest safe way is still three
migrations, in this order:

1. **Add the column, allowed to be empty** (`null=True`). Django makes it.
2. **Data migration:** delete every to-do without an owner. The logic is a normal function in
   `todos/data_migrations.py`. The migration is `makemigrations --empty` plus one `RunPython` line,
   with `RunPython.noop` as the reverse (deleted rows cannot come back; going back simply does
   nothing).
3. **Make the column required.** Django makes it.

**What a laptop with old to-dos sees:** after `git pull` and `uv run python manage.py migrate`,
the old to-dos are gone, and `/` shows the log-in page. Sign up, and the list is empty. If the
laptop's database is in a strange state for any other reason, `make reset` deletes `db.sqlite3` and
makes it again, empty (it also deletes users, so sign up again). A new database (CI, tests) has no
old rows, so step 2 does nothing there.

### Sessions and passwords on a live server

A **session** is how Django remembers that a browser is logged in: a random key in a cookie, and
the data in the database.

- Already in `settings.py` when `DEBUG` is off, no change needed: `SESSION_COOKIE_SECURE` (the cookie
  goes only over HTTPS), `CSRF_COOKIE_SECURE`, the HTTPS redirect, and **HSTS** (a header that tells
  the browser "use only HTTPS for this site from now on").
- Django's defaults, which we keep: `SESSION_COOKIE_HTTPONLY = True` (JavaScript cannot read the
  cookie), `SESSION_COOKIE_SAMESITE = "Lax"`, sessions last 2 weeks. `login()` always gives the
  browser a **new** session key, so a key someone planted before log-in is useless ("session
  fixation").
- **`SECRET_KEY` matters more now.** Django uses it to make a check value stored in each session
  (from the password hash, so changing a password logs out other browsers), and to sign other
  data. Anyone who knows the key could forge these. Today, a live server that forgets
  `DJANGO_SECRET_KEY` silently uses the key that is in git. New: **if `DEBUG` is off and
  `DJANGO_SECRET_KEY` is not set, the site refuses to start** (`ImproperlyConfigured`).
- The deploy steps get `uv run python manage.py check --deploy`, which lists unsafe settings.

### The pages

- **The account bar lives in `base.html`**, inside `{% if user.is_authenticated %}`:
  `Logged in as ana` and a **Log out** button (a `POST` form). So every page has it, and the log-in
  page (nobody logged in) does not. `user` is in every template already, from the `auth` **context
  processor** (a function that adds keys to every template's data).
- `registration/login.html` and `registration/signup.html` **extend `base.html`**. Each has an
  `<h1>`, the form drawn by Django (`{{ form }}`, so labels and errors come for free), a button, and
  a link to the other page ("New here? Sign up" / "Already have an account? Log in").
  `registration/login.html` is the name `LoginView` looks for by itself; the admin app ships no file
  with that name.
- No JavaScript.

### The admin

`TodoAdmin`: `owner` in `list_display`, `list_filter = ["owner"]`. Staff see every to-do, on purpose.

### How this fits the later plans

- **Lists (13)** uses `Todo.todo_list` with `on_delete=RESTRICT`. Deleting a **user** still deletes
  their lists (CASCADE on `TodoList.owner`) and their to-dos (CASCADE on `Todo.owner`): Django allows
  a RESTRICT row to go when the same delete also removes what it points at. 13 changes `for_user`
  to "in one of my lists" and makes `Todo.save()` set `owner` from the list.
- **Test helpers:** one set. Now: `make_user()` and `LoggedInTestCase.make_todo(**fields)`. Lists
  (13) changes them to `make_user()` that also makes the default list, and
  `make_todo(todo_list=None, **fields)`. Every test that uses them keeps working.
- **Reminders (18)** reads `Todo.objects.due_for_reminder(today).filter(owner=user)` in a
  management command, for every owner. That is correct (it is not a view), and the guard does not
  read commands. 18 adds an email box to sign-up with `SignUpForm(UserCreationForm)`.
- **Sharing (20)** deletes `for_user` and adds `visible_to` / `editable_by` and `todos/access.py`.
  Its grep `owner=` in `views.py` would match our `form.instance.owner = request.user`; 13 replaces
  that line (the owner comes from the list), so it is gone by then.

## What we will not do (yet)

- **No email check at sign-up, no "forgot my password" by email.** Both need a way to send email
  (an email service, like SendGrid or Amazon SES). The site has none. Reminders (18) brings one;
  then Django's own views can add both.
- No "change my password" or "delete my account" page. (The admin can do both.)
- No limit on wrong passwords. It needs a package like `django-axes`. See Risks.
- No sharing (20). No log-in with Google or GitHub. No custom user model.

## Changes in behaviour

1. A visitor who is not logged in sees **only** the log-in and sign-up pages. A `GET` of any other
   address goes to `/accounts/login/?next=<that address>`. A `POST` changes nothing and goes to
   `/accounts/login/?next=/`.
2. The list, the count, "Delete N completed", filter, search and sort show **only my** to-dos.
3. Toggle, delete, edit and every subtask action on **another person's** to-do give **404** and
   change nothing. Before, anyone could change any to-do.
4. "Delete completed" with another person's ids deletes **nothing** of theirs.
5. A new to-do belongs to the person who added it. A repeating to-do's next copy has the same owner.
6. To-dos that exist today (with no owner) are **deleted** by the migration. Nobody uses the site
   yet (owner decision).
7. `/admin/` sends a visitor to our log-in page; `/admin/login/` still opens.
8. A live server with `DEBUG` off and no `DJANGO_SECRET_KEY` refuses to start.

## The changes, one file at a time

### 1. `todos/models.py`

- `TodoQuerySet.for_user(user)`; `Todo.owner` (above; `null=True` only for migration 1).
- Repeating (19): `next_values()` adds `"owner": self.owner` (it then also counts in
  `is_untouched_copy_of`, which is right: the copy has the same owner).

### 2. `todos/data_migrations.py` — new file

```python
"""Logic for data migrations. A migration imports a function from here.

Never change a function that a migration imports: old migrations still run on every new database,
so changing it changes history. Write a new function instead.
"""


def delete_todos_without_owner(apps, schema_editor):
    """Feature 17: to-dos made before accounts have no owner. Delete them.

    There is no production data yet (owner decision), so nothing real is lost.
    Their subtasks are deleted with them (CASCADE).
    """
    Todo = apps.get_model("todos", "Todo")
    Todo.objects.filter(owner__isnull=True).delete()
```

- `apps.get_model(...)` gives the model **as it was at that migration**, not as in `models.py`
  today. Django needs this in a migration.
- `.delete()` here deletes the rows in the database, and the rows that depend on them.

### 3. The three migrations

**The recipe** (also pasted into the PR description, for the merge queue). Start with `models.py`
having `owner = models.ForeignKey(..., null=True)`:

```bash
# 1. Add the column, allowed to be empty.
uv run python manage.py makemigrations todos -n todo_owner
# 2. The data migration: an empty file, then one line (below).
uv run python manage.py makemigrations todos --empty -n delete_todos_without_owner
# 3. Now remove null=True from models.py, then:
uv run python manage.py makemigrations todos -n todo_owner_required --noinput
uv run python manage.py migrate
uv run python manage.py makemigrations --check --dry-run   # must say "No changes detected"
```

In the empty file from step 2, add `from todos.data_migrations import delete_todos_without_owner` and
this one line in `operations`:

```python
migrations.RunPython(delete_todos_without_owner, migrations.RunPython.noop),
```

`noop` means "going back does nothing". Going back past step 1 removes the column anyway. So every
migration can be **reversed** (rule for `AGENTS.md`, below).

`--noinput` in step 3 matters. Without it, Django stops and asks what to put in old rows. With it,
Django prints this, which is **expected** (step 2 has removed the old rows):

```
Field 'owner' on model 'todo' given a default of NOT PROVIDED and must be corrected.
```

Check the step-3 file is one `AlterField` with no `default`.

### 4. `config/middleware.py` — new, the `LoginRequired` class (above)

### 5. `config/settings.py`

```python
from django.core.exceptions import ImproperlyConfigured

if not DEBUG and "DJANGO_SECRET_KEY" not in os.environ:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY on a live server.")
```

(placed after `DEBUG` is read)

```python
MIDDLEWARE = [
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.LoginRequired",  # new: every page needs log-in
    ...
]

# Accounts: where to send a person to log in, and where to go after.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "todo_list"
LOGOUT_REDIRECT_URL = "login"
```

`LoginRequired` must come **after** `AuthenticationMiddleware`, which finds the user.

### 6. `config/urls.py`

```python
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required

from todos.views import signup

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", login_not_required(auth_views.LogoutView.as_view()), name="logout"),
    path("accounts/signup/", signup, name="signup"),
    path("", include("todos.urls")),
]
```

### 7. `todos/views.py`

- Every row of the table in "Ownership".
- The subtask views: the two `get_object_or_404` lines in "Subtasks".
- The sign-up view:

```python
@login_not_required
@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("todo_list")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect("todo_list")
    return render(request, "registration/signup.html", {"form": form})
```

### 8. Templates

- `todos/templates/base.html`: the account bar, at the top of `<body>`:

```html
{% if user.is_authenticated %}
  <div class="account">
    Logged in as <strong>{{ user.username }}</strong>
    <form method="post" action="{% url 'logout' %}">{% csrf_token %}<button type="submit">Log out</button></form>
  </div>
{% endif %}
```

- `todos/templates/registration/login.html` (new, extends `base.html`): `<h1>Log in</h1>`, the form
  with `{% csrf_token %}`, `{{ form }}`, `<input type="hidden" name="next" value="{{ next }}">`, a
  `Log in` button, the sign-up link.
- `todos/templates/registration/signup.html` (new, extends `base.html`): `<h1>Sign up</h1>`, the
  form, a `Sign up` button, the log-in link.

### 9. `todos/admin.py` — `owner` in `list_display`; `list_filter = ["owner"]`.

### 10. `todos/tests/integration/helpers.py` — add the account helpers

```python
# A test value only, for test users. Not a real password.
TEST_PASSWORD = "plum-tree-river-42"


def make_user(username="ana"):
    return get_user_model().objects.create_user(username, password=TEST_PASSWORD)


class LoggedInTestCase(TestCase):
    """A test where "ana" is logged in. self.make_todo() makes her to-dos."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("ana")

    def setUp(self):
        self.client.force_login(self.user)

    def make_todo(self, **fields):
        fields.setdefault("owner", self.user)
        return Todo.objects.create(**fields)
```

- `force_login` logs the test client in without the log-in page. It is fast.
- Changing an existing test class is two small edits: `TestCase` → `LoggedInTestCase`, and
  `Todo.objects.create(` → `self.make_todo(`. Unit tests that save a to-do pass
  `owner=make_user()`.

### 11. `AGENTS.md`

- "What this is": replace "There are no accounts: everyone who opens the site sees the same list"
  with "Each person signs up and logs in, and sees only their own to-dos."
- File table: `models.py` (`owner`, `for_user`), `views.py` (`signup`; every query starts with
  `for_user`), `config/urls.py` (log in, log out, sign up), new rows `config/middleware.py`,
  `todos/data_migrations.py`, `todos/templates/registration/`.
- New rules:
  - **Every to-do query in a view starts with `Todo.objects.for_user(request.user)`. Another
    person's to-do is a 404.** (A test checks this.)
  - **A new view needs log-in by itself. Only a page for visitors gets `@login_not_required`.**
  - **Every migration can be reversed.** A `RunPython` always has a reverse (`RunPython.noop` if
    there is nothing to undo).
  - **Never change a function that a migration imports.** Write a new one.
- Deploy: set `DJANGO_SECRET_KEY`; run `manage.py check --deploy`.

## Tests (`todos/tests/`)

Words used here: a **`subTest`** runs one part of a test in a loop and reports each failing part
on its own. A **`TransactionTestCase`** is a slower test class that really writes to the database
(needed to run migrations). A **`MigrationExecutor`** is Django's own tool that moves a database
forward or back to a named migration.

### Top: CUJ tests (`todos/tests/cuj/test_journeys.py`)

Labels: Django labels the fields `Username:`, `Password:` and `Password confirmation:`.
`get_by_label("Password")` finds **two** boxes on the sign-up page (checked in a real browser), so
always use `get_by_label("Password:", exact=True)` and
`get_by_label("Password confirmation:", exact=True)`.

- **Changed** `test_plan_and_finish_a_todo`: `setUp` makes `ana` with `make_user`. The journey opens
  `/`, sees the log-in page, fills `Username:` and `Password:`, presses `Log in`, and goes on as
  before. (A helper `log_in(page, username)`.)
- **New** `test_sign_up_and_see_only_my_own_list` (sign-up is a new journey):
  1. Open `/` → the log-in page. Click `Sign up`. Sign up as `ana`. See `Nothing to do yet`.
  2. Add `Buy milk`. Press `Log out`. The log-in page is shown.
  3. Sign up as `ben`. See `Nothing to do yet`, and the list has no `Buy milk` item. Log out.
  4. Log in as `ana`. `Buy milk` is a list item.

How they fail (step B below): there is no log-in page, so `get_by_label("Username:")` is not
found; `/` shows the list.

### Bottom: unit tests

| Test | What it checks | How it fails (step B) |
|---|---|---|
| `test_for_user_gives_only_their_todos` | ana has 2, ben has 1 → exactly ana's 2 | passes after A (protecting; check it against `for_user` returning `self.all()`) |
| `test_next_repeat_keeps_the_owner` | ben's repeating to-do: `next_copy().owner` is ben | `owner` is `None` (not copied) |
| `test_deleting_a_user_deletes_their_todos` | delete ben → ana's stay, ben's are gone | passes after A (protecting; check against `on_delete=SET_NULL`) |
| `test_views_never_ask_for_todos_without_the_owner` | the guard (above) on `views.py` and `forms.py` | finds `Todo.objects.with_subtask_progress()`, `get_object_or_404(Todo, …)` and more; also shown failing against one deliberate `Todo.objects.all()` added after the fix |

### Middle: integration tests

All use `LoggedInTestCase`, except the visitor tests.

**`integration/test_accounts.py`** (new):

| Test | What it checks | How it fails (step B) |
|---|---|---|
| `test_visitor_is_sent_to_log_in` | anonymous `GET /` → 302 to `/accounts/login/?next=/` | 200, the list |
| `test_visitor_post_changes_nothing_and_comes_back_to_the_list` | anonymous `POST` to **every** todos URL → 302 to `/accounts/login/?next=/`; the tables are unchanged | add returns 500 (no owner); toggle changes the row |
| `test_login_and_signup_pages_are_open` | anonymous `GET` → 200, exactly `<h1>Log in</h1>` / `<h1>Sign up</h1>` | `NoReverseMatch`: the addresses do not exist |
| `test_log_in_page_has_no_account_bar` | anonymous log-in page has no `<div class="account">` (exact element, count 0) | `NoReverseMatch` |
| `test_signup_makes_a_user_and_logs_in` | good data → 302 to `/`; the user exists; `GET /` is 200 | `NoReverseMatch` |
| `test_signup_rejects_a_common_password` | `password123` twice → 200, `This password is too common.`, no user | `NoReverseMatch` |
| `test_signup_rejects_different_passwords` | → 200, `The two password fields didn’t match.` (Django's **curly** apostrophe `’`) | `NoReverseMatch` |
| `test_signup_rejects_a_taken_username` | → 200, `A user with that username already exists.` | `NoReverseMatch` |
| `test_login_with_a_good_password` | → 302 to `/` | `NoReverseMatch` |
| `test_login_with_a_bad_password` | → 200, `Please enter a correct username and password. Note that both fields may be case-sensitive.`; not logged in | `NoReverseMatch` |
| `test_login_never_goes_to_another_site` | `next=https://evil.example/` → 302 to `/` | `NoReverseMatch`; protecting: also check against a view that follows `next` by hand |
| `test_logout_is_post_only` | `GET` → 405; `POST` → 302 to log-in; then `GET /` → 302 | `NoReverseMatch` |
| `test_logout_when_already_logged_out` | anonymous `POST` to log-out → 302 to `/accounts/login/` (not `?next=/accounts/logout/`) | `NoReverseMatch` |
| `test_account_bar_shows_who_is_logged_in` | exactly the `account` div with `ana` and the `Log out` form (`html=True`) | not there |
| `test_admin_sends_a_visitor_to_our_log_in` | anonymous `GET /admin/` → 302 to `/accounts/login/?next=/admin/`; `GET /admin/login/` → 200 | `/admin/` goes to `/admin/login/` |
| `test_no_secret_key_on_a_live_server_refuses_to_start` | reload settings in a subprocess with `DJANGO_DEBUG=False` and no key → exits with `ImproperlyConfigured` | it starts |

**`integration/test_ownership.py`** (new). Ana is logged in; ben has his own to-dos:

| Test | What it checks | How it fails (step B) |
|---|---|---|
| `test_list_shows_only_my_todos` | ana's `<li>` is there (exact element); the list has exactly 1 item | ben's is shown |
| `test_count_counts_only_mine` | the count is exactly ana's `1 item left` element | counts ben's |
| `test_search_filter_and_sort_show_only_mine` | ben has a matching to-do; `?q=milk`, `?show=active`, `?sort=title` give only ana's | ben's is shown |
| `test_add_makes_my_todo` | the new to-do's owner is ana | passes after A (protecting) |
| `test_add_and_edit_ignore_a_posted_owner` | post `owner=<ben's id>` → owner is still ana | passes after A (protecting; check against a form with `owner` in `fields`) |
| `test_delete_completed_never_deletes_theirs` | post ben's completed ids → ben's still exist | ben's are deleted |
| **`test_their_todo_is_404_everywhere`** | **the matrix** (below) | toggle/delete/edit change ben's rows |
| `test_my_todo_is_not_404` | the same rows on ana's own fresh objects → not 404 | passes (protecting: shows the 404 comes from the owner, not a wrong URL) |
| `test_every_url_is_in_the_matrix` | every name in `todos.urls.urlpatterns` is in the matrix or in `LIST_URLS` (`todo_list`, `todo_add`, `todo_delete_completed`) | a new address must be added to one of them |

**The matrix.** One row per (URL name, method). Each row runs in a `subTest`, and makes **fresh**
objects for itself: ben's to-do with one subtask (so one row cannot spoil the next). Before the
request, take a snapshot of the **whole** tables: `list(Todo.objects.values())` and
`list(Subtask.objects.values())`. Check **404**, then check both snapshots are exactly the same.

| URL name | Method | Object |
|---|---|---|
| `todo_toggle` | POST (`done=1`) | ben's to-do |
| `todo_delete` | POST | ben's to-do |
| `todo_edit` | GET | ben's to-do |
| `todo_edit` | POST (good data) | ben's to-do |
| the subtask page (from 15) | GET | ben's to-do |
| each subtask URL with a to-do id (e.g. `subtask_add`) | POST | ben's to-do |
| each subtask URL with a subtask id (e.g. `subtask_toggle`, `subtask_delete`) | POST | ben's to-do and ben's subtask |
| `subtask_toggle` with **ana's** to-do id and **ben's** subtask id | POST | 404 (the step is looked up inside ana's to-do) |
| any other address from 9 / 19 / 15 with an id | its method | ben's object |

**`integration/test_owner_migration.py`** (new), a `TransactionTestCase` with `MigrationExecutor`:
go back to `…_todo_owner`, make rows with the **old** models (`executor.loader.project_state(...)
.apps`), go forward to `…_todo_owner_required`, check. It finds the migrations by their name ending
(`_todo_owner`, `_todo_owner_required`), not by number, so the merge queue can renumber them.
**`tearDown` migrates back to the leaf nodes** (`executor.loader.graph.leaf_nodes()`), so the next
test finds the database complete.

| Test | What it checks |
|---|---|
| `test_old_todos_without_owner_are_deleted` | 2 old to-dos (one with a subtask) → after migrating, no to-dos and no subtasks are left |
| `test_the_migrations_can_be_reversed` | go back to before `…_todo_owner`, then forward again: no error |

These are written in step A, with the migrations, and shown failing first against a data migration
whose function body is `pass` (the old rows keep `NULL`, so step 3 fails with `IntegrityError`).
No unit test for the function: it is one line, and this test runs it for real.

**Changed existing tests (step A).** Every class in `integration/` becomes a `LoggedInTestCase`
and uses `self.make_todo(...)`; unit tests pass an owner; the existing CUJ logs in by putting a
session cookie in the browser (from `Client().force_login(ana)`), because there is no log-in page
yet. In step C the CUJ switches to the real log-in form.

## Steps, in order

**Step A — one commit, "the owner exists" (no behaviour change for a logged-in person).**

1. `models.py`: `owner` with `null=True`, and `for_user`. Migration 1 (recipe).
2. `todos/data_migrations.py` and migration 2. Remove `null=True`; migration 3. `migrate`.
3. Write `test_owner_migration.py`; show it failing against the `pass` body; then passing.
4. Add the helpers; change every existing test (mechanical). `todo_add` gets
   `form.instance.owner = request.user` (the only view change; without it, add would crash).
   Repeating's `next_values()` copies `owner` (without it, Done on a repeating to-do would crash).
5. Copy a `db.sqlite3` with to-dos from before this branch; `migrate` the copy; check it runs
   without error and the to-do table is empty. (The merge queue's "run the migration on a copy
   with old to-dos" check passes the same way.)
6. `make check`: everything green. Commit.

**Step B — one commit, the behaviour tests.** Write `test_accounts.py`, `test_ownership.py`, the
guard, the unit tests, and both CUJ journeys. Run `make test` and `make test-cuj`; save the output.
Each new test fails for the reason in its table (wrong answer, ben's rows shown or changed,
missing address). The protecting tests pass, and are each shown failing against their deliberate
bug.

**Step C — the feature.**

1. `config/middleware.py`, `settings.py` (middleware, `LOGIN_*`, the secret-key check),
   `config/urls.py`.
2. `views.py`: every row of the ownership table, the subtask lines, `signup`.
3. `base.html` account bar; `registration/login.html` and `signup.html`; `admin.py`.
4. The existing CUJ: replace the cookie log-in with the log-in form.
5. `make test`, `make test-cuj`: all pass. `make run`: sign up two people (one in a private window);
   each sees only their own list. Press `Done` in a tab after logging out in the other: you land on
   the log-in page, then on the list. Check both pages at phone width.
6. Add `uv run python manage.py check --deploy` to the deploy steps in `README.md`. Update
   `AGENTS.md`.
7. `make check`. Commit. Paste the migration recipe into the PR description.

## Risks

- **A view forgets the owner.** Covered three ways: the middleware (log-in), the guard test (the
  code), and the matrix with `test_every_url_is_in_the_matrix` (the behaviour).
- **The migration deletes old to-dos.** Safe only because there is no production data yet (owner
  decision). Anyone with to-dos on a laptop loses them; the plan and the PR say so. After a launch,
  a migration like this would need a different plan.
- **Guessing passwords.** No limit on wrong tries. Fine for a class project; `django-axes` later.
- **LAUNCH ITEM: rate limits and username enumeration (from the security review).** Sign-up is
  open to everyone and has no limit: a script can make many accounts, and try many passwords on
  the log-in page. The sign-up form also says "A user with that username already exists.", so
  anyone can find out which usernames exist (this is called **username enumeration**). Nobody
  uses the site yet, so no package is added now. **Before the launch:** add `django-axes` (it
  locks out an address or a username after a number of wrong passwords), and decide on a limit
  for sign-ups (for example with a rate-limit package or the hosting service's own limits).
- **LAUNCH ITEM: `DEBUG` is on unless `DJANGO_DEBUG=False`.** The default stays `True` (owner
  decision: it is a launch decision, not part of this feature). A live server that forgets
  `DJANGO_DEBUG=False` shows Django's debug pages, and then also skips the HTTPS-only cookie
  settings and the secret-key check. The deploy steps in `README.md` set it; check it at launch.
- **The live server must set `DJANGO_SECRET_KEY`** before this deploys, or it will not start. This is
  on purpose: better than running with the key from git. An empty or blank key, or one that
  starts with `django-insecure-` (like the laptop default), also refuses to start.
- **Every test file changes.** Mechanical, but large. That is why 17 is built alone.
- **The guard is a text search.** It can be fooled (e.g. `T = Todo; T.objects…`). The matrix is the
  real check; the guard catches the common mistake early.

## Owner answers

1. **Old to-dos:** no `legacy` user and no back-filling. There is no production data yet, so the
   migration deletes to-dos without an owner, and the owner field is required.
2. **Sign-up open to everyone:** yes.
3. The "`DJANGO_SECRET_KEY` must be set when `DEBUG` is off" check stays: it protects a future
   launch.

Note for the orchestrator: CONVENTIONS.md says "Signed in as"; this plan uses "Logged in as", as
the review asked. Please make the two the same. (By the build, CONVENTIONS.md says "Logged in as"
too.)

## What happened

Built on `main` after waves 1–3 (everything up to subtasks, `0006_subtask`), in three commits, as
planned: **A** (the owner exists; every test logs in; green), **B** (the behaviour tests; red for
the reasons in the tables), **C** (the feature; green). These are the places where the build is
different from the plan, and why.

1. **No real browser** (owner decision). Both journeys use Django's test client. `log_in(client,
   username)` in `helpers.py` opens `/`, checks it lands on `/accounts/login/?next=/`, reads the
   log-in form from the page and presses **Log in**. The existing journeys (`test_journeys.py`, and
   the details journey) start with it. The new journey `test_sign_up_and_see_only_my_own_list`
   follows the **Sign up** link and sends the real sign-up form (with CSRF checks on). Fields are
   filled by their names (`username`, `password1`, `password2`); the labels (`Username:`,
   `Password:`) are checked once in `test_log_in_form_has_its_labels`. In step A the journeys used
   `force_login` (no cookie trick needed with the test client); in step B they switched to the
   real form, so they failed in B with "/ did not show the log-in page".
2. **Every view on today's `main` is scoped**, not only the plan's table: the list, count,
   `has_todos`, completed ids, toggle, edit, delete, delete completed, `subtask_list`,
   `subtask_add`, and `get_subtask_or_404` (now `get_subtask_or_404(request, pk, subtask_pk)`,
   which returns `(todo, subtask)`). The steps page lists `todo.subtasks.all()` (it was
   `Subtask.objects.filter(todo_id=pk)`). The view's own `mark_edited(pk)` (an unscoped
   `Todo.objects.filter(pk=pk).update(...)`) became the model method `Todo.mark_edited()`, called
   on a to-do already found through its owner. The details pane needed no change: its to-do comes
   only from the scoped list (`test_their_selected_todo_shows_no_pane`).
3. **The next copy copies `owner_id`, not `owner`.** A to-do built in a unit test without an
   owner would crash on `self.owner` once the field is required. The field-copy test now sets and
   reads each field by its `attname` (`owner_id` for the owner, sample `7`), so it still demands
   that `next_values()` copies the owner.
4. **`owner` stays an editable model field** (the admin can change it), so two existing tests
   changed: the edit-form test leaves out `owner` with `done` ("the owner is never in a form"),
   and the admin form test gives `get_form` a superuser request (the admin's user box asks who is
   looking). `admin_save` in `test_repeat.py` sends the owner, and logs ana back in after.
5. **The account bar's Log out form is on every page.** `page_parts(...).post_actions` leaves it
   out, and the new `page_post_forms(response)` gives a page's `POST` forms without it. The
   journey that lists every button on the steps page now starts with `"Log out"`.
6. **The admin, pinned as Django 5.2 really does it** (the plan expected every admin page to go to
   our log-in page). Django marks the admin's front page and `/admin/login/` "login not
   required": `/admin/` goes to `/admin/login/?next=/admin/`. The other admin pages need log-in,
   so `/admin/todos/todo/` goes to `/accounts/login/?next=/admin/todos/todo/`. A logged-in person
   who is not staff is sent to the admin's log-in page. Tests: `test_admin_log_in_stays_open`,
   `test_admin_is_closed_to_a_person_who_is_not_staff`.
7. **More tests than the plan's tables:** a visitor's `GET` comes back to its page after log-in;
   `next` to our own page is followed; a logged-in person on the log-in or sign-up page goes to
   the list; the Log out form works with CSRF checks on; the footer is hidden when only another
   person has to-dos; `subtask_done` and `subtask_delete` with my to-do and their step are 404;
   the matrix also posts `done=0`; `test_every_url_is_in_the_matrix` also fails on a matrix name
   that no longer exists; the guard has its own test with good and bad lines. The secret-key test
   runs a new Python three times: no key with `DEBUG` off (refuses, `ImproperlyConfigured: Set
   DJANGO_SECRET_KEY on a live server.`), a test key (starts), and a laptop (starts).
8. **Test helpers** (in `helpers.py`): `TEST_PASSWORD`, `make_user`, `LoggedInTestCase` (with
   `make_todo` and `csrf_client()`, a second logged-in client with CSRF checks), `log_in`,
   `account_bar`, `count_elements`, `page_post_forms`, and `LOGIN_URL` / `SIGNUP_URL` /
   `LOGOUT_URL`. The two `make` helpers in `test_search.py` and `test_sort.py` became methods, so
   they make ana's to-dos.

### Red and green

- **Step A, the migration test** against a data migration whose body was `pass`: `IntegrityError:
  NOT NULL constraint failed: new__todos_todo.owner_id` (step 3 cannot make the column required
  while old rows have no owner). With the real body: 2 passed. Then the whole suite: CUJ 5,
  Integration 249, Unit 109 passed.
- **Step B:** Integration 256 passed, 53 failed, 1 error; Unit 113 passed, 1 failed; CUJ 6
  failed. The reasons: the addresses `/accounts/...` answer 404 (no log-in page); a visitor gets
  200 and the list; a visitor's add is an error (`Cannot assign AnonymousUser to Todo.owner`) and
  their toggle, edit, delete and step posts change rows; ben's to-dos are in the list, the count,
  the search, filter and sort, and the pane; delete completed deletes ben's; every row of the 404
  matrix answers 302 or 200 and changes ben's rows; a live server without a key starts; the guard
  lists 13 lines of `views.py`. The protecting tests passed (the mixed step row,
  `test_my_todo_is_not_404`, `test_every_url_is_in_the_matrix`, `for_user`, the next copy's
  owner, deleting a user, a posted owner) and were each shown failing against a deliberate bug
  (below).
- **Step C:** `make test`: Integration 287, Unit 114 passed. `make test-cuj`: CUJ 6 passed.
  `make check`: every hook passed, "No changes detected", all tests OK.

### Deliberate bugs, one at a time, each put back

| Bug | Caught by |
|---|---|
| list without `for_user` | list, footer, search/filter/sort, pane tests; the guard |
| count / completed / `has_todos` without `for_user` | count, footer tests; the guard |
| `get_object_or_404(Todo, ...)` in toggle, edit, delete, `subtask_list`, `subtask_add`, `get_subtask_or_404` (six runs) | the 404 matrix each time; the guard each time |
| delete completed without `for_user` | `test_delete_completed_never_deletes_theirs`; the guard |
| a stray `Todo.objects.all()` in `todo_list` | the guard |
| the `subtask_delete` row taken out of `MATRIX` | `test_every_url_is_in_the_matrix` |
| `for_user` returns `self.all()` | `test_for_user_gives_only_their_todos` |
| `next_values()` without the owner | `test_next_repeat_keeps_the_owner`, the field-copy test |
| `on_delete=SET_NULL` | `test_deleting_a_user_deletes_their_todos` (an `IntegrityError`) |
| `owner` in `TodoForm.Meta.fields` | `test_add_and_edit_ignore_a_posted_owner` |
| `LoginView` allows `evil.example` | `test_login_never_goes_to_another_site` |
| Django's plain `LoginRequiredMiddleware` | `test_visitor_post_changes_nothing_and_comes_back_to_the_list` (8 rows: `next` was the POST address) |
| `LogoutView` without `login_not_required` | `test_logout_when_already_logged_out` |

### The migration, checked

- A database at `0006_subtask` with two old to-dos and one step: `migrate` ran `0007_todo_owner`,
  `0008_delete_todos_without_owner` and `0009_todo_owner_required` with no error; then 0 to-dos
  and 0 steps.
- An empty database: `migrate` from nothing, no error. Then `migrate todos 0006` (all three
  reversed) and `migrate` again: no error.
- `test_owner_migration.py` does both on the test database in every run.

**The recipe, for the merge queue** (when another branch also adds a migration after `0006`).
Delete this branch's three files (`*_todo_owner.py`, `*_delete_todos_without_owner.py`,
`*_todo_owner_required.py`), add `null=True` to `Todo.owner` in `models.py`, then:

```bash
uv run python manage.py makemigrations todos -n todo_owner
uv run python manage.py makemigrations todos --empty -n delete_todos_without_owner
#   In that empty file, add:
#     from todos.data_migrations import delete_todos_without_owner
#   and in operations:
#     migrations.RunPython(delete_todos_without_owner, migrations.RunPython.noop),
#   Now remove null=True from Todo.owner again, then:
uv run python manage.py makemigrations todos -n todo_owner_required --noinput
#   Expected: "Field 'owner' on model 'todo' given a default of NOT PROVIDED and must be
#   corrected." The file must be one AlterField with no default.
uv run python manage.py migrate
uv run python manage.py makemigrations --check --dry-run   # "No changes detected"
uv run python manage.py test todos.tests.integration.test_owner_migration
```

### Checked by eye

Headless Chrome against `runserver` on a free port (a scratch database, stopped after):

- **Log-in page, 1280 wide:** `Log in`, `Username:` and `Password:` with their boxes, the
  **Log in** button, "New here? Sign up". No account bar.
- **Sign-up page, 1280 wide:** `Sign up`, the three boxes with Django's help text (the four
  password rules as a small grey list), the **Sign up** button, "Already have an account? Log in".
- **The list as ana, 1280 wide:** the account bar at the top right, "Logged in as **ana**" and
  **Log out**, above the two columns; only ana's three to-dos ("2 items left", "Delete 1
  completed to-do"); ben's to-do is not there.
- At the first try the bar was a flex row, and its gap made "as  ana" look like two spaces. It is
  now plain right-aligned text with an inline form.
- Narrow: Chrome's headless window is at least about 500 px wide, so a 375 px screenshot is cut
  off on the right (an artefact of the tool). At 500 px both pages fit: the bar sits at the top
  right, and the list keeps its full width.

### After the security review: a stronger safety net

A security reviewer attacked the branch as ben against ana on every address: nothing leaked and
nothing changed. The safety net was still made stronger before the merge. Each new test was
first shown failing (against the old code, or against a deliberate bug), then passing.

1. **Every route of the whole project.** `test_every_url_is_in_the_matrix` now walks Django's
   URL resolver (`get_resolver().url_patterns`, into every `include()`), not only
   `todos/urls.py`. Only an explicit allowlist is left out: the admin (namespace `admin`), the
   account pages (`login`, `logout`, `signup`) and `static/`. Every other route must be named and
   be in `MATRIX` or `LIST_URLS`. Shown failing against a new `todos/export.py` view (every
   title, unscoped) routed in `config/urls.py`.
2. **The canary.** Ben's to-do, its notes and its step carry a unique word. As ana, the test
   opens every `LIST_URLS` address, the list with each `show`, `sort`, `q` and `selected` value,
   the add form's error page, delete completed with ben's id, and her own edit and steps pages.
   The word must never appear. (A search for the whole word is not used, because the page shows
   the search back; a part of it is used.) Shown failing against the same export view listed in
   `LIST_URLS` (the walk then passes, the canary fails).
3. **The guard reads every `.py` file** in `todos/` and `config/`, except tests and migrations,
   with three more patterns: `model = Todo` / `Subtask` (a generic view or form), `get_list_or_404(
   Todo|Subtask` and `.model.objects`. The lines that may match are listed in `ALLOWED`, by file
   and exact text, each with its reason: the model methods that work on a to-do already found,
   the ModelForms' `Meta.model`, the data migration, and the admin inline. Shown failing against
   `class TodoDetail(DetailView): model = Todo` in `views.py`.
4. **Settings.** With `DEBUG` off, an empty or blank `DJANGO_SECRET_KEY`, or one that starts with
   `django-insecure-`, also refuses to start (red first: all four keys started). A new test loads
   the live settings in a new Python and checks `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` and
   `SESSION_COOKIE_HTTPONLY` are all `True` (shown failing without `SESSION_COOKIE_SECURE`). The
   `DEBUG` default is not changed: see Risks.
5. **Rate limits and username enumeration:** no package now; a launch item in Risks
   (`django-axes`).
6. **Steps page.** `test_my_steps_page_shows_only_my_steps`: ana's steps page lists exactly her
   step, and not ben's word. Shown failing against `todo.subtasks.model.objects.all()` (the canary
   and the guard catch it too).
7. **HEAD is like GET** in the middleware: a visitor's `HEAD /5/edit/` goes to
   `/accounts/login/?next=/5/edit/` (red first: `next` was `/`).
8. **Defence in depth in the model.** `Todo.mark_edited()` and Undo's `DELETE` of the copy also
   filter by `owner_id`. Two unit tests (red first): a stale object with another owner changes
   nothing, and Undo never deletes a copy that belongs to someone else.

After: `make test` Integration 292, Unit 117 passed; `make test-cuj` CUJ 6 passed; `make check`
passed.
