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


def delete_todos_without_a_list(apps, schema_editor):
    """Feature 13: to-dos made before lists have no list. Delete them.

    There is no production data yet (owner decision), so nothing real is lost,
    and there is no back-filling: old users get no list (they are sent to "New
    list"). Their subtasks are deleted with them (CASCADE).
    """
    Todo = apps.get_model("todos", "Todo")
    Todo.objects.filter(todo_list__isnull=True).delete()


def number_existing_todos(apps, schema_editor):
    """Feature 16: give the to-dos that exist a place in "My order".

    For each list: oldest first (date added, then id), 1, 2, 3, ... So on day
    one, "My order" is the same as "Date added". There is no production data
    yet (owner decision), but whatever exists is numbered. bulk_update does
    not call save().
    """
    Todo = apps.get_model("todos", "Todo")
    changed = []
    next_number = {}
    for todo in Todo.objects.order_by("todo_list_id", "created_at", "pk"):
        number = next_number.get(todo.todo_list_id, 1)
        next_number[todo.todo_list_id] = number + 1
        if todo.position != number:
            todo.position = number
            changed.append(todo)
    Todo.objects.bulk_update(changed, ["position"], batch_size=500)
