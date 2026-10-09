# AGENTS.md — for the AI agent working in this repository

The person asking you may be new to programming, and may read English as a second language.
Explain in short, plain sentences, and define a technical word the first time you use it. When you
change code, say which file changed and why.

## What this is

The most basic to-do list, in Django. A person can add a to-do, mark it done (or undo that), and
delete it. There are no accounts: everyone who opens the site sees the same list. The data is kept
in a SQLite database, the file `db.sqlite3`, which is not in git.

## What each file does

| File | Its one job |
|---|---|
| `config/settings.py` | Settings for the whole project. The secret key, debug and allowed hosts come from environment variables on a live server, with defaults for a laptop. |
| `config/urls.py` | Sends `/admin/` to Django's admin, and everything else to `todos/urls.py`. |
| `todos/models.py` | The `Todo` table: `title`, `done`, `due_date`, `priority`, `notes`, `created_at`. `priority` is a number (High 3, Medium 2, Low 1), so it sorts in the right order. Use `Todo.Priority.HIGH`, not `3`. Notes are optional (`""` when empty, never `NULL`) and at most `NOTES_LIMIT` (500) characters; the model's validator checks it too. `Todo.objects.remaining()` gives the to-dos that are not done; `Todo.objects.completed()` gives the completed to-dos. |
| `todos/forms.py` | `TodoForm`: the add form, built from the model. It has `title`, `due_date`, `priority` and `notes`, and checks them. A missing or empty priority is Medium. `NotesField` counts a line break as one character, like the browser does. `notes_box_open()` says if the folded notes box starts open. `TodoEditForm`: the same form for the edit page, with every field of `TodoForm`, and a visible label on every box. A new field goes in `TodoForm` only. |
| `todos/admin.py` | The admin for `Todo`. It uses `NotesField` for the notes, so a line break counts as one character there too. |
| `todos/urls.py` | The addresses: the list, add, toggle, edit, delete, delete completed. |
| `todos/views.py` | One function per address. Add, toggle, delete and delete completed accept `POST` only, then send the browser back to the list. `todo_edit`: `GET` shows the form, `POST` saves it and goes back to the list, with the same list parameters (filter and pane). A bad form shows the page again with the errors. Delete completed deletes only the completed to-dos whose ids the page sent; the page sends at most the oldest 500 (`MAX_DELETE_AT_ONCE`). If the add form has errors, the page is shown again with the errors and what the person typed. Every key the list page needs goes in `page_context(request, form)`, so both views get it; today that is `todos`, `form`, `has_todos`, `remaining_count`, `completed_ids`, `empty_message`, `list_query`, `filter_links`, `sort_links`, `selected`, `select_base`, `close_url`, `q`, `no_match_start`, `search_box_maxlength`, `search_keeps` and `clear_search_url`. The list can show All, Active or Completed (`?show=active`, `?show=completed`). Everything about a filter is one row in the `FILTERS` table. `list_params` reads the list parameters and drops anything unknown. Every `POST` form posts to an address with the list query, and `back_to_list` sends the browser back to the same view. The count and the delete-completed button are about the whole table, not only what the filter or the search shows. The list can be searched (`?q=milk`). `list_params` cleans `q`: no invisible characters (but it keeps the two zero-width joiners, U+200C and U+200D), one space between words, at most `SEARCH_MAX_LENGTH` characters (the title's max_length, 200). The search box's `maxlength` is twice that, because the browser counts UTF-16 units. `search_todos` looks in the title or the notes for the word as typed or in its NFKC form, so wide letters find normal ones. With a search it also adds `title_match` (an annotation, in the same query), so a row whose title does not match shows `matches in notes`. `search_todos` runs before `selected_todo`, so a search that hides the selected to-do closes the pane. `?selected=<id>` shows the details pane. `list_params` checks it with `clean_id` (ASCII digits only, at most 18; always the last key). The pane's to-do is taken **only** from the to-dos already on the page (`selected_todo`), never looked up by id. Everything that changes the list comes before `selected_todo`. The list can be sorted (`?sort=due`, `priority`, `title`; the default is `created`, Date added, oldest first). `SORTS` is the one table of choices. Every order ends with `created_at`, then `pk`. `list_params` keeps the order `show`, `q`, `sort`, and `selected` last. `sort_todos` runs after `search_todos` and before `selected_todo`. The chosen sort link has `aria-current="true"` (the filter uses `"page"`). |
| `todos/templates/base.html` | The page frame: the `<head>` and the shared CSS. Every page extends it. A page's own CSS goes in its `{% block style %}`. |
| `todos/templates/todos/todo_edit.html` | The edit page. It draws every field of the form with a loop, so a new field needs no change here. |
| `todos/templates/todos/todo_list.html` | The list page: the add form (drawn by Django from `TodoForm`; the notes box is folded in a `<details>`), the search form (a `GET` form that keeps the other list parameters in hidden inputs), the filter links (the row "Show:") and the sort links (the row "Sort by:"; each row's visible label is also its name for a screen reader, with `aria-labelledby`), the list (it shows `High priority` or `Low priority` after the title; Medium shows nothing; each row has an Edit link before Done), and under it how many to-dos are left and the "Delete N completed to-dos" button. Each title is a link that opens the details pane (on the right on wide screens, under the list on phones). The pane shows the notes, with their line breaks; the list rows never show them. The pane ends with Edit and Close. Its CSS is in the page's `{% block style %}`. |
| `todos/tests/unit/` | Unit tests: one piece alone, like the model, with no request. |
| `todos/tests/integration/` | Integration tests: requests through Django's test client, from the URL to the database. |
| `todos/tests/integration/helpers.py` | Helpers the integration tests share: `page_parts` (the titles shown, the `POST` form actions, the chosen filter link), `page_forms` (every form with its address, fields and button, so a test can send it like a browser), `page_without_csrf`, and `list_footer` (the whole footer, exactly). For the details pane: `panes`, `selected_titles`, `row(title)`, `title_element(..., match_hint=False)` and `pane_element(..., notes=None, edit_url=None)`; `page_parts(...).pane_notes` (the pane's notes as text) and `.pane_tags` (every element inside the pane). `page_parts(...).html_lang` (the page's `lang`). `link_href(response, name)`: the address of the one link whose whole name (its `aria-label`, else its text) is exactly `name`, like a click. |
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
- **Use what Django already has** — forms, the admin, `get_object_or_404`, the test client — before
  writing your own.
- **Change data only with `POST`.** A `GET` request only reads.
- **A new `POST` form on the list page ends its `action` with `{{ list_query }}`**, and its view
  ends with `back_to_list(request)`. Then the person stays on the same filter.
- **A change control in the details pane goes in `<p class="details-actions">`.** Close only reads.
- **Check titles with `page_parts(...).titles` or `title_element(...)`**, never a hand-written
  `<span class="title">`: the title is a link with a long address.
- **A new page extends `base.html`.**
- **Put a test in the lowest level that can catch the bug.** Its folder sets the level: `unit`,
  `integration` or `cuj`. Add a CUJ test only for a new journey a person takes.
- **No real-browser tests.** Things only a browser shows (CSS, layout, focus) are checked by eye
  with a screenshot.
- **Show text that people typed only through Django's escaping.** Never use `|safe` or
  `{% autoescape off %}` on it. The list is shared, so one person's text is shown to everyone.
- **No label, summary, `<dt>` or `aria-label` may contain a button's word**: Add, Done, Undo,
  Delete, Due date. Tests find buttons by part of their name.
- **Add or change a test with every change in behavior**, and show the person the test failing
  before the fix and passing after.
