# To-do list

The most basic to-do list in Django: add a to-do, mark it done, delete it.

## Run it on your laptop

**1. Install uv, once.** uv installs Python and this project's packages for you.

Mac:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close the terminal and open a new one, then check with `uv --version`.

**2. Get the code.**

```bash
git clone https://github.com/kreativitea/anyone-can-build-todo.git
cd anyone-can-build-todo
```

**3. Install the packages.** The first time, uv also downloads the right version of Python.

```bash
uv sync
```

**4. Create the database.** This makes a file called `db.sqlite3`.

```bash
uv run python manage.py migrate
```

**5. Turn on the commit checks.** From now on, every `git commit` checks your code first.

```bash
uv run pre-commit install
```

**6. Start the server.**

```bash
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Press `Ctrl+C` in the terminal to stop the server.

**7. Run the tests.**

```bash
uv run python manage.py test
```

You should see `OK`, then one line for each level of tests, like `Unit: 3 passed`. There are three
levels: **unit** tests check one piece alone, **integration** tests send requests to the site, and
**CUJ** (critical user journey) tests follow a whole journey a person takes, from start to finish.
All of them use Django's test client, a pretend browser inside the test, so no real browser is
needed.

On a Mac, `make` does the same in fewer words: `make setup` is steps 3 to 5, `make run` is step 6.
`make test` runs the fast tests, `make test-cuj` runs the journey tests, and `make check` runs
everything. `make help` lists the rest.

## Checks

| Command | What it does |
|---|---|
| `uv run ruff check` | Finds mistakes and bad habits in the Python code |
| `uv run ruff format` | Rewrites the Python code in the standard style |
| `uv run pre-commit run --all-files` | Runs every commit check on every file |

The commit checks run Ruff, Django's own check, and a few checks on every file. If a check fails
because it fixed a file for you, look at the change, `git add` the file, and commit again. GitHub
runs the same checks and the tests on every push.

## How it is put together

| File | What it does |
|---|---|
| `config/settings.py` | Settings for the whole project |
| `config/urls.py` | Sends each address to the right app |
| `todos/models.py` | The `Todo` table in the database |
| `todos/urls.py` | The addresses of the to-do pages |
| `todos/views.py` | What happens when each address is visited |
| `todos/templates/todos/todo_list.html` | The page you see |
| `todos/tests/` | The tests, in three folders: `unit`, `integration` and `cuj` |
| `config/test_runner.py` | Runs the tests, then prints a summary for each level |
| `AGENTS.md` | Instructions for the AI assistant (Codex reads it; `CLAUDE.md` points Claude to it) |

## Put it on the internet

A live server needs three environment variables. Never put their real values in the code.

| Variable | Value |
|---|---|
| `DJANGO_SECRET_KEY` | A long random string. Make one with `uv run python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | The site's address without `https://`, for example `my-todo.onrender.com` |

With `DJANGO_DEBUG` set to `False`, the site only works over HTTPS.

Build command:

```bash
pip install uv && uv sync --locked --no-dev && uv run --no-dev python manage.py collectstatic --no-input && uv run --no-dev python manage.py migrate
```

Start command:

```bash
uv run --no-dev gunicorn config.wsgi
```
