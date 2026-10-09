"""The hand-made order of a list, "My order" (reorder, 16): numbering and moving.

Every query here starts from ONE list's to-dos (`todo.todo_list.todos`), and
the to-do itself was found through its owner by the view. So a move can never
read or change a to-do of another list, or of another person.
"""

from django.db import transaction
from django.db.models import Count

UP = "up"
DOWN = "down"
DIRECTIONS = (UP, DOWN)


def needs_renumber(todos):
    """True when a to-do has no number, or two to-dos have the same one.

    The database counts; normally both are False. Only bulk_create, loaddata
    and old rows leave an empty number.
    """
    if todos.filter(position__isnull=True).exists():
        return True
    repeated = (
        todos.order_by()
        .values("position")
        .annotate(rows=Count("pk"))
        .filter(rows__gt=1)
    )
    return repeated.exists()


def renumber(todos):
    """Give `todos` (one list) 1, 2, 3, ... in My order. Writes only the rows that change."""
    changed = []
    for number, todo in enumerate(todos.in_my_order(), start=1):
        if todo.position != number:
            todo.position = number
            changed.append(todo)
    todos.bulk_update(changed, ["position"], batch_size=500)


def move(todo, shown, direction):
    """Move `todo` one place up or down among the rows on the page.

    `shown` is the to-dos the page shows (the filter, the search). The
    neighbour is the next SHOWN row with the same done state: completed
    to-dos always go last (owner decision), so an open to-do never swaps with
    a completed one. The two to-dos swap their numbers. At the first or last
    row nothing changes. If `todo` is not shown (an old page), the neighbour
    comes from the whole list.
    Returns True when two to-dos swapped, False when nothing changed.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be {UP!r} or {DOWN!r}")
    siblings = todo.todo_list.todos.all()  # this list only, never another one
    # One transaction on the list's own database: every read and both writes.
    with transaction.atomic(using=siblings.db):
        if needs_renumber(siblings):
            renumber(siblings)
        # Read fresh, inside the transaction: another tab may have moved it.
        fresh = siblings.filter(pk=todo.pk).first()
        if fresh is None:
            return False  # deleted a moment ago
        shown_ids = set(shown.values_list("pk", flat=True))
        rows = siblings.filter(done=fresh.done).in_my_order()
        ids = list(rows.values_list("pk", flat=True))
        if fresh.pk in shown_ids:
            ids = [pk for pk in ids if pk in shown_ids]
        index = ids.index(fresh.pk)
        other_index = index - 1 if direction == UP else index + 1
        if not 0 <= other_index < len(ids):
            return False  # the first row cannot go up, the last cannot go down
        other = siblings.get(pk=ids[other_index])
        siblings.filter(pk=fresh.pk).update(position=other.position)
        siblings.filter(pk=other.pk).update(position=fresh.position)
        return True


def move_limits(todos):
    """The ids whose ↑ and whose ↓ the page draws `disabled`: (no_up, no_down).

    `todos` is the page's rows in My order, completed last. The first row of
    the open ones and of the completed ones cannot go up; the last of each
    cannot go down.
    """
    no_up, no_down = set(), set()
    previous = None
    for todo in todos:
        if previous is None or previous.done != todo.done:
            no_up.add(todo.pk)
            if previous is not None:
                no_down.add(previous.pk)
        previous = todo
    if previous is not None:
        no_down.add(previous.pk)
    return no_up, no_down
