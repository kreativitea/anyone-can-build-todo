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
