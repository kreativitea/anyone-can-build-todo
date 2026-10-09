# Plan: building features 4 to 20, in parallel

Status: **approved, in progress.** This plan says *in what order* to build the features, and
which features can be built *at the same time*. Each feature still gets its own plan in
`docs/plans/<feature>.md`.

## The pipeline for one feature

1. **Plan.** A planner agent writes `docs/plans/<feature>.md`, in the same style as
   [due-date.md](due-date.md).
2. **Adversarial review.** A second agent tries to find what is wrong with the plan. The planner
   fixes every finding.
3. **Plan card.** You get a short card: what the feature does, the decisions it makes, the files it
   changes, and the risks. You approve it, or ask for changes.
4. **Tests first.** In its own worktree and branch, an agent writes the tests and shows them failing.
5. **Code.** The same agent writes the code until every test passes and `make check` passes.
6. **Adversarial review.** A third agent reviews the tests and the code. The builder fixes every
   finding.
7. **Pull request.** The PR goes to `main`, and joins the **merge queue** (below). The builder
   agent never merges. Only the orchestrator merges, one PR at a time.

A **worktree** is a second folder for the same git repository. Each worktree is on its own branch,
so several agents can change files at the same time without getting in each other's way.

## Where features collide

Two branches **collide** when both change the same lines. Then the second one to merge has to fix
the clash by hand. These are the places that cause collisions:

| Hot spot | Features that change it | How bad |
|---|---|---|
| **Migrations** (`todos/migrations/`) | 5, 6, 7, 13, 14, 15, 16, 17, 19 | **The worst.** Two branches both make `0002_...`. Django then refuses to run until someone fixes it. |
| `todos/models.py` | the same as migrations | mild: different lines |
| `todos/forms.py` (made by 5) | 4, 6, 7, 13, 14, 19 | mild: one more field each |
| `todo_list` in `views.py` | 8, 9, 10, 12, 13, 14, 17 | medium: they all change how the list is read |
| the template | almost every feature | mild: mostly different parts of the page |
| the CUJ test | features that change the main journey | mild |

### Rules that keep collisions small

- **Migration rule.** Builders make their migration from `main` as it is when they start, and do
  not worry about other branches. The merge queue makes the migration again just before it merges
  (below), so two branches never reach `main` with the same migration number.
- **List-query rule.** Filter, search, sort and count all read the list. Each one adds a small
  function in `views.py` that changes the query. `todo_list` only calls them one after another, so
  each branch adds one line in `todo_list`, not a block of code.
- **One form.** Every field feature adds its field to the one `TodoForm`. Then "edit" (feature 4)
  shows every field without more work.
- **Merge order inside a wave** is fixed in advance (below). The merge queue follows it.

## The merge queue

The orchestrator (the main Claude thread, the one you talk to) is the **merge queue**: the only one
that merges into `main`. It merges **one PR at a time**, so `main` always has exactly one line of
migrations.

A PR joins the queue when its code review is finished and its fixes are pushed. For each PR, in the
wave's order:

1. **Bring it up to date.** Rebase the branch on the newest `main`. A **rebase** moves the
   branch's commits so they start from the end of `main`, as if the work had started today. Fix
   any clash in normal code by hand.
2. **Make the migration again** (only if the branch has one):
   - Delete the branch's **own** migration files: the ones that are not on `main` yet.
   - Run `uv run python manage.py makemigrations`. Django gives the file the next number and points
     it at the newest migration on `main`.
   - This does not break "never edit a migration by hand": Django writes the new file, and the old
     one never reached `main`.
3. **Check it.**
   - `uv run python manage.py makemigrations --check --dry-run` must say "No changes detected".
   - `make check` and `make test-cuj` must pass.
   - The migration must run on a copy of a database that has old to-dos in it, not only on an
     empty test database.
4. **Push and wait.** Push the branch (`git push --force-with-lease`, which refuses to overwrite
   anything it has not seen). Wait for CI on GitHub to pass.
5. **Merge.** Squash-merge: the whole PR becomes **one commit** on `main`.
6. **Next.** Start again at step 1 with the next PR. Its rebase now includes the PR just merged.

If a step fails, the PR leaves the queue and goes back to its builder with the error, and the next
PR goes first. If two fixes in a row fail, the orchestrator stops and asks you.

**Data migrations.** Some features may need a migration that Django cannot write by itself, for
example "give every old to-do an owner" (17), or "number the old to-dos in order" (16). Those
features keep that code in a function in a normal Python file, and their plan says how to make the
migration again: `makemigrations --empty`, then one line that calls the function. Every plan
reviewer checks for this.

**A guard.** `makemigrations --check --dry-run` is added to `make check` and to CI in wave 0. It
fails if a migration is missing, or if two migrations have the same parent. So a migration clash
cannot reach `main` even by mistake.

## The waves

A **wave** is a group of features that are built at the same time. A wave starts after the wave
before it is merged.

**Planning runs one wave ahead.** While the agents build wave N, the planners write and review the
plans for wave N+1. Then you always have plan cards to review, and no agent has to wait. A plan for
a late wave is not written at the start, because it would be out of date by the time we built it.

| Wave | Features (merge order) | Built at the same time | Why this wave |
|---|---|---|---|
| **0** | test pyramid, plus the migration guard | 1 | Every other branch puts its tests in the new folders. The test work is already done in your working copy; it needs the guard, a commit and a PR. |
| **1** | **5** due date → **12** count → **11** clear completed → **8** filter | 4 | 5 makes `forms.py`, which later features use. Its plan is already approved. 8, 11 and 12 make no migration. |
| **2** | **6** priority → **7** notes → **4** edit → **10** search | 4 | 6 and 7 add fields to the form from wave 1. 4 comes after them, so "edit" covers every field. 10 is a list query, like 8. |
| **3** | **9** sort → **19** repeating → **15** subtasks | 3 | 9 sorts by due date and priority, so it needs waves 1 and 2. 19 needs due dates. 15 is a new table. |
| **4** | **17** accounts | 1 | It changes every view and every query, so nothing else can run next to it. It must come before 13, 14 and 20, because those need an owner. |
| **5** | **13** lists → **14** tags → **16** drag to reorder | 3 | 13 and 14 are new tables. 16 waits for 13, so that the order is per list. |
| **6** | **20** sharing → **18** reminders | 2 | 20 needs accounts and lists. 18 needs accounts (who gets the email) and due dates. |

That is **7 waves instead of 17 steps one after another.** The longest wave has 4 features.

### Agents per wave

Each feature uses about 4 agents: a planner, a plan reviewer, a builder and a code reviewer. The
whole set is about **70 agent runs**. Each agent works in its own worktree, so the work in this
folder is never touched.

## What you do

- **Approve plan cards.** Up to 4 at a time.
- **Nothing else.** The orchestrator merges. You get a short note after each merge, and a ping if
  the queue stops.

## Open questions

1. **Accounts (17).** Wave 4 changes "everyone sees the same list", the most basic idea of this app.
   Do we build it?
2. **Reminders (18).** These need an email service and something that runs on a timer (a cron job).
   Those are new parts of the live server. Do we build it, or stop at feature 19?
