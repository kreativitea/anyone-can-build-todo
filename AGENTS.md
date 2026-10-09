# AGENTS.md — for the AI agent working in this repository

The person asking you may be new to programming, and may read English as a second language.
Explain in short, plain sentences, and define a technical word the first time you use it. When you
change code, say which file changed and why.

## What this is

The most basic to-do list, in Django. A person can add a to-do, mark it done (or undo that), and
delete it. Each person signs up and logs in, and sees only their own to-dos. A visitor who is not
logged in sees only the log-in and sign-up pages. The data is kept in a SQLite database, the file
`db.sqlite3`, which is not in git.

## What each file does

| File | Its one job |
|---|---|
| `config/settings.py` | Settings for the whole project. The secret key, debug and allowed hosts come from environment variables on a live server, with defaults for a laptop. With `DJANGO_DEBUG=False` and no `DJANGO_SECRET_KEY` (or an empty one, or one starting with `django-insecure-`), the site refuses to start (`ImproperlyConfigured`). `LOGIN_URL`, `LOGIN_REDIRECT_URL` (the list) and `LOGOUT_REDIRECT_URL` (the log-in page). |
| `config/middleware.py` | `LoginRequired`: Django's `LoginRequiredMiddleware`, so **every** page needs log-in by itself. A visitor's `GET` or `HEAD` goes to `/accounts/login/?next=<that address>`; any other method (a `POST`) goes to `?next=/`, the list, because after log-in the browser would `GET` a `POST`-only address and get 405. |
| `config/urls.py` | Sends `/admin/` to Django's admin; `/accounts/login/` and `/accounts/logout/` to Django's `LoginView` and `LogoutView` (log out is `POST` only, and open to visitors so an old tab can still log out); `/accounts/signup/` to `todos.views.signup`; everything else to `todos/urls.py`. No password-reset pages: they need email. |
| `todos/models.py` | The `Todo` table: `owner` (the user who added it; `CASCADE`: deleting a user deletes their to-dos; never in a form), `title`, `done`, `due_date`, `priority`, `notes`, `repeat`, `next_todo`, `created_at`. `priority` is a number (High 3, Medium 2, Low 1), so it sorts in the right order. Use `Todo.Priority.HIGH`, not `3`. `Todo.objects.for_user(user)` gives only that person's to-dos: **every** to-do query in a view starts with it. Notes are optional (`""` when empty, never `NULL`) and at most `NOTES_LIMIT` (500) characters; the model's validator checks it too. `Todo.objects.remaining()` gives the to-dos that are not done; `Todo.objects.completed()` gives the completed to-dos. `repeat` is a word: `none`, `daily`, `weekly` or `monthly` (`Todo.Repeat`); a repeating to-do needs a due date (`Todo.clean()` checks it). `next_todo` links to the copy that Done made (`editable=False`, emptied when the copy is deleted). `repeat_day` is the day of the month a monthly to-do comes back on (set by `TodoForm.save` when the to-do is new or its date or repeat changed; copies keep it). `edited` is set when a person saves on the edit page or in the admin. `set_done(True/False)` is Done and Undo. `mark_edited()` sets `edited` with one `UPDATE` (the step views call it). Done on a repeating to-do makes the next one, with the same owner (none after the year 9999); Undo deletes it only if it is open, has no next copy and is not `edited`. The admin's "done" box makes no copy. `Subtask`: a step inside a to-do (`todo`, `title`, `done`, `created_at`), oldest first, deleted with its to-do (`CASCADE`); `todo.subtasks` gives a to-do's steps. `with_subtask_progress()` counts the steps (`subtask_count`, `subtask_done_count`, with `distinct=True`) in the list query. Done on a repeating to-do gives the next copy the same steps, all not done (`copy_subtasks_to`, one `bulk_create`, in the same transaction). |
| `todos/forms.py` | `TodoForm`: the add form, built from the model. It has `title`, `due_date`, `priority`, `notes` and `repeat`, and checks them. A missing or empty priority is Medium; a missing or empty repeat is `none`. `NotesField` counts a line break as one character, like the browser does. `notes_box_open()` says if the folded notes box starts open. `TodoEditForm`: the same form for the edit page, with every field of `TodoForm`, and a visible label on every box. A new field goes in `TodoForm` only. `SubtaskForm`: the "New step" box (only `title`). |
| `todos/data_migrations.py` | The logic of data migrations: a migration imports one function from here. `delete_todos_without_owner` (accounts): the to-dos made before accounts had no owner, and are deleted (no production data yet, owner decision). |
| `todos/repeat.py` | The date math for repeating to-dos: `next_due_date(due, repeat, day)`. Counted from the due date. Monthly comes back on the remembered day, or the last day of a shorter month. After 31 Dec 9999 it raises `OverflowError`. |
| `todos/admin.py` | The admin for `Todo`. Staff see every person's to-dos, on purpose: `owner` is a column and a filter. It uses `NotesField` for the notes, so a line break counts as one character there too. A to-do's steps are shown on its page (`SubtaskInline`); `Subtask` is not registered alone. |
| `todos/urls.py` | The addresses: the list, add, toggle, edit, delete, delete completed; and a to-do's steps page `/<id>/subtasks/` with its three `POST` addresses: add, done, delete. |
| `todos/views.py` | One function per address. **Every to-do query starts with `Todo.objects.for_user(request.user)`**, keeping the methods after it (`with_subtask_progress()`, `completed()`, ...); another person's to-do is not in it, so it is a 404 everywhere. `todo_add` sets `form.instance.owner = request.user`. `signup`: Django's `UserCreationForm` (the four password validators check the password), then `login()`; open to visitors (`@login_not_required`); a logged-in person goes to the list. Add, toggle, delete and delete completed accept `POST` only, then send the browser back to the list. Done/Undo (`todo_toggle`) post the state the person wants, `done=1` or `done=0`; anything else is 400. A to-do already in that state is not changed, so a double click or an old tab does nothing. `todo_edit`: `GET` shows the form, `POST` saves it and goes back to the list, with the same list parameters (filter and pane). A bad form shows the page again with the errors. Delete completed deletes only the completed to-dos whose ids the page sent; the page sends at most the oldest 500 (`MAX_DELETE_AT_ONCE`). If the add form has errors, the page is shown again with the errors and what the person typed. Every key the list page needs goes in `page_context(request, form)`, so both views get it; today that is `todos`, `form`, `has_todos`, `remaining_count`, `completed_ids`, `empty_message`, `list_query`, `filter_links`, `sort_links`, `selected`, `select_base`, `close_url`, `q`, `no_match_start`, `search_box_maxlength`, `search_keeps` and `clear_search_url`. The list can show All, Active or Completed (`?show=active`, `?show=completed`). Everything about a filter is one row in the `FILTERS` table. `list_params` reads the list parameters and drops anything unknown. Every `POST` form posts to an address with the list query, and `back_to_list` sends the browser back to the same view. The count and the delete-completed button are about all of the person's to-dos, not only what the filter or the search shows. The list can be searched (`?q=milk`). `list_params` cleans `q`: no invisible characters (but it keeps the two zero-width joiners, U+200C and U+200D), one space between words, at most `SEARCH_MAX_LENGTH` characters (the title's max_length, 200). The search box's `maxlength` is twice that, because the browser counts UTF-16 units. `search_todos` looks in the title or the notes for the word as typed or in its NFKC form, so wide letters find normal ones. With a search it also adds `title_match` (an annotation, in the same query), so a row whose title does not match shows `matches in notes`. `search_todos` runs before `selected_todo`, so a search that hides the selected to-do closes the pane. `?selected=<id>` shows the details pane. `list_params` checks it with `clean_id` (ASCII digits only, at most 18; always the last key). The pane's to-do is taken **only** from the to-dos already on the page (`selected_todo`), never looked up by id. Everything that changes the list comes before `selected_todo`. The list can be sorted (`?sort=due`, `priority`, `title`; the default is `created`, Date added, oldest first, open before completed). `SORTS` is the one table of choices. In every sort, completed to-dos go last: every order starts with `done` (open first), then that sort's keys. Every order ends with `created_at`, then `pk`. `list_params` keeps the order `show`, `q`, `sort`, and `selected` last. `sort_todos` runs after `search_todos` and before `selected_todo`. The chosen sort link has `aria-current="true"` (the filter uses `"page"`). The list starts from `Todo.objects.with_subtask_progress()`, so each row (and the pane) has its step counts with no extra query. Steps: `subtask_list` shows a to-do's steps page; `subtask_add`, `subtask_done` and `subtask_delete` are `POST` only and go back to the steps page with `back_to_subtasks` (same list parameters). A step is always looked up with `get_subtask_or_404(request, pk, subtask_pk)`, which returns `(todo, subtask)`: first the to-do through its owner, then the step among `todo.subtasks`, so a link can never change a step of another to-do or another person (and a too-big id is a 404). The steps page lists `todo.subtasks.all()`. `subtask_done` takes the wanted state (`done=1` or `done=0`, from `WANTED`); anything else is 400. Adding, Done/Undo on, or deleting a step sets the to-do's `edited`, so Undo keeps a repeating copy whose steps changed. Steps never change their to-do's `done`, and the to-do's Done never changes its steps. |
| `todos/templates/base.html` | The page frame: the `<head>` and the shared CSS. Every page extends it. A page's own CSS goes in its `{% block style %}`. For a logged-in person, the account bar at the top: `Logged in as <name>` and a **Log out** button (a `POST` form). |
| `todos/templates/registration/` | `login.html` (the name Django's `LoginView` looks for) and `signup.html`. Both extend `base.html`, draw the form with `{{ form }}` (labels and errors from Django), and link to each other. |
| `todos/templates/todos/todo_edit.html` | The edit page. It draws every field of the form with a loop, so a new field needs no change here. Under the form, a **Steps** link goes to the to-do's steps page. |
| `todos/templates/todos/subtask_list.html` | The steps page of one to-do: its steps, oldest first, each with Done / Undo (a button that posts `done=1` or `done=0`) and Delete; the "New step" box (with `autofocus`); Back to the list. |
| `todos/templates/todos/todo_list.html` | The list page: the add form (drawn by Django from `TodoForm`; the notes box is folded in a `<details>`), the search form (a `GET` form that keeps the other list parameters in hidden inputs), the filter links (the row "Show:") and the sort links (the row "Sort by:"; each row's visible label is also its name for a screen reader, with `aria-labelledby`), the list (it shows `High priority` or `Low priority` after the title; Medium shows nothing; an open repeating to-do shows `Every week` (or day, month) under the due date; each row has an Edit link before Done, and Done/Undo carry a hidden `done` input), and under it how many to-dos are left and the "Delete N completed to-dos" button. Each title is a link that opens the details pane (on the right on wide screens, under the list on phones). The pane shows a Repeats row when the to-do repeats (also when it is completed), and the notes, with their line breaks; the list rows never show them. A to-do with steps shows a "1 of 3 steps" link to its steps page (on its own line inside the title block, so on a phone the title keeps the full width), and the pane a "Steps: 1 of 3 done" row. The pane ends with Edit and Close. Its CSS is in the page's `{% block style %}`. |
| `todos/tests/unit/` | Unit tests: one piece alone, like the model, with no request. |
| `todos/tests/integration/` | Integration tests: requests through Django's test client, from the URL to the database. |
| `todos/tests/integration/helpers.py` | Helpers the integration tests share: `page_parts` (the titles shown, the `POST` form actions, the chosen filter link), `page_forms` (every form with its address, fields and button, so a test can send it like a browser; a button's `accessible_name` is its `aria-label`, else its text), `page_without_csrf`, and `list_footer` (the whole footer, exactly). For the details pane: `panes`, `selected_titles`, `row(title)`, `title_element(..., match_hint=False, repeat="", progress="")` and `pane_element(..., notes=None, edit_url=None, repeats=None, steps=None)`; `page_parts(...).pane_notes` (the pane's notes as text) and `.pane_tags` (every element inside the pane). `page_parts(...).html_lang` (the page's `lang`). `link_href(response, name)`: the address of the one link whose whole name (its `aria-label`, else its text) is exactly `name`, like a click. Accounts: `make_user(username)` (password `TEST_PASSWORD`, a test value); `LoggedInTestCase` (ana is logged in with `force_login`; `self.make_todo(**fields)` makes her to-dos; `self.csrf_client()` is a second, logged-in client with CSRF checks); `log_in(client, username)` logs in through the real log-in page; `account_bar(username)`; `count_elements`; `page_post_forms` (the page's `POST` forms, without the account bar's Log out). `page_parts(...).post_actions` leaves out the Log out form too. |
| `todos/tests/integration/test_ownership.py` | The 404 matrix: one row per address with an id and method; each row on fresh objects of another person, with whole-table snapshots. `test_every_url_is_in_the_matrix` walks **every route of the whole project** (all of `config/urls.py`); except the allowlist (the admin, the account pages, `static/`), **a new address with an id goes in `MATRIX`, any other in `LIST_URLS`**. The canary test (`CanaryTests`) gives ben a to-do, notes and a step with a unique word, opens every `LIST_URLS` address and every list setting as ana, and fails if the word shows. |
| `todos/tests/cuj/` | CUJ tests (critical user journeys): a whole journey through Django's test client. Each step reads the form from the page, posts it with CSRF checks on, and follows the redirect. |
| `config/test_runner.py` | Runs the tests like Django does, then prints a summary for each level. |
| `todos/migrations/` | Made by Django from `models.py`. Never edit these by hand. |
| `pyproject.toml`, `uv.lock` | The packages this project uses, and their exact versions. |
| `.pre-commit-config.yaml` | The checks that run on every `git commit`. |
| `Makefile` | Short commands. `make help` lists them. |

## Commands

This project uses **uv** to install Python and the packages. Run every Python command through
`uv run`, so it uses this project's packages:

- `make setup` — install everything, create the database, turn on the commit checks
- `make run` — start the server at <http://127.0.0.1:8000>
- `make test` — run the unit and integration tests, in parallel (fast)
- `make test-cuj` — run the CUJ tests: whole journeys through the test client
- `make lint` / `make format` — Ruff: find mistakes, and rewrite code in the standard style
- `make check` — every commit check on every file, a check that no migration is missing or
  clashing, then every test

Add a package with `uv add <name>`, never with `pip install`. After changing `models.py`, run
`uv run python manage.py makemigrations` and then `uv run python manage.py migrate`.

## Rules

- **Run `make check` before every commit.** The commit checks also run by themselves. If one fails
  after fixing a file, look at the change, `git add` the file, and commit again.
- **Never put a secret in the code.** Passwords, keys and tokens go in environment variables.
  A live server must set `DJANGO_SECRET_KEY`; run `uv run python manage.py check --deploy` before
  a deploy.
- **Every to-do query in a view starts with `Todo.objects.for_user(request.user)`.** Never
  `Todo.objects.all()` and never `get_object_or_404(Todo, ...)`; find a step through its to-do
  (`todo.subtasks`). Another person's to-do is a 404, never a 403. A unit test reads every `.py` file in
  `todos/` and `config/` (not tests or migrations) and fails on a query without the owner, a
  generic view or form on `Todo`/`Subtask` (`model = Todo`), `get_list_or_404(Todo, ...)` or
  `.model.objects`. Model code that works on a to-do already found is listed in its `ALLOWED`, with
  the reason; filter it by `owner_id` too.
- **The owner is never in a form.** The view sets it.
- **A new view needs log-in by itself** (the middleware). Only a page for visitors gets
  `@login_not_required`.
- **Every migration can be reversed.** A `RunPython` always has a reverse (`RunPython.noop` if
  there is nothing to undo). Its logic lives in `todos/data_migrations.py`.
- **Never change a function that a migration imports.** Write a new one.
- **Use what Django already has** — forms, the admin, `get_object_or_404`, the test client — before
  writing your own.
- **Change data only with `POST`.** A `GET` request only reads.
- **A new `POST` form on the list page ends its `action` with `{{ list_query }}`**, and its view
  ends with `back_to_list(request)`. Then the person stays on the same filter.
- **A change control in the details pane goes in `<p class="details-actions">`.** Close only reads.
- **Check titles with `page_parts(...).titles` or `title_element(...)`**, never a hand-written
  `<span class="title">`: the title is a link with a long address.
- **A new page extends `base.html`.**
- **In code and addresses say *subtask*; on the page say *step*.**
- **A test that needs a logged-in person uses `LoggedInTestCase` and `self.make_todo(...)`.** A
  unit test that saves a to-do passes `owner=make_user()`.
- **Put a test in the lowest level that can catch the bug.** Its folder sets the level: `unit`,
  `integration` or `cuj`. Add a CUJ test only for a new journey a person takes.
- **No real-browser tests.** Things only a browser shows (CSS, layout, focus) are checked by eye
  with a screenshot.
- **Show text that people typed only through Django's escaping.** Never use `|safe` or
  `{% autoescape off %}` on it. Usernames and the admin show one person's text to others.
- **No label, summary, `<dt>` or `aria-label` may contain a button's word**: Add, Done, Undo,
  Delete, Due date. Tests find buttons by part of their name.
- **Every `Todo` ModelForm must include `repeat`.** `Todo.clean()` ties its error to that field;
  without it, Django raises `ValueError`.
- **Done and Undo send `done=1` or `done=0`.** A test that posts to `todo_toggle` must send it, or it
  gets 400.
- **Add or change a test with every change in behavior**, and show the person the test failing
  before the fix and passing after.
