# To-do list: short commands for this project. Type `make help` to see them.

.PHONY: help setup run test test-cuj lint format check reset worktree

help:
	@echo "make setup            install Python and the packages, create the database, turn on the commit checks"
	@echo "make run              start the server, then open http://127.0.0.1:8000"
	@echo "make test             run the unit and integration tests (fast)"
	@echo "make test-cuj         run the CUJ test in a real browser (slow)"
	@echo "make lint             look for mistakes and style problems (ruff check)"
	@echo "make format           rewrite the code in the standard style (ruff format)"
	@echo "make check            everything the commit checks run, on every file, plus the tests"
	@echo "make reset            delete db.sqlite3 and create it again, empty"
	@echo "make worktree BRANCH=name"
	@echo "                      give a branch its own folder, .claude/worktrees/name"

setup:
	uv sync
	uv run python manage.py migrate
	uv run playwright install chromium
	uv run pre-commit install

run:
	uv run python manage.py runserver

test:
	uv run python manage.py test --parallel auto todos.tests.unit todos.tests.integration

test-cuj:
	uv run python manage.py test todos.tests.cuj

lint:
	uv run ruff check

format:
	uv run ruff format

check:
	uv run pre-commit run --all-files
	uv run python manage.py test --parallel auto

reset:
	rm -f db.sqlite3
	uv run python manage.py migrate

# Every branch gets its own worktree: its own folder and its own files, so
# several people or agents can work at the same time.
worktree:
	@test -n "$(BRANCH)" || { echo "Say which branch: make worktree BRANCH=name"; exit 1; }
	@if git show-ref --quiet --verify refs/heads/$(BRANCH); then \
		git worktree add .claude/worktrees/$(BRANCH) $(BRANCH); \
	else \
		git worktree add -b $(BRANCH) .claude/worktrees/$(BRANCH) main; \
	fi
	@echo "Now work in .claude/worktrees/$(BRANCH)"
