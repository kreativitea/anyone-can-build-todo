from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import TodoForm
from .models import Todo


def page_context(request, form):
    """What the list page needs. Both views use this, so a new key goes here once.

    `request` is not used yet. The filter feature needs it next.
    """
    return {
        "todos": Todo.objects.all(),
        "form": form,
        "has_todos": Todo.objects.exists(),
        "remaining_count": Todo.objects.remaining().count(),
        "completed_ids": list(Todo.objects.completed().values_list("pk", flat=True)),
    }


def todo_list(request):
    return render(request, "todos/todo_list.html", page_context(request, TodoForm()))


@require_POST
def todo_add(request):
    form = TodoForm(request.POST)
    if form.is_valid():
        form.save()
        return redirect("todo_list")
    return render(request, "todos/todo_list.html", page_context(request, form))


@require_POST
def todo_toggle(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    todo.done = not todo.done
    todo.save()
    return redirect("todo_list")


@require_POST
def todo_delete(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    todo.delete()
    return redirect("todo_list")


# A real id is a plain number. A longer one cannot be a row, and is too big for SQLite.
MAX_ID_DIGITS = 18


@require_POST
def todo_delete_completed(request):
    """Delete the completed to-dos whose ids the page sent, and only those."""
    ids = [
        value
        for value in request.POST.getlist("ids")
        if value.isascii() and value.isdigit() and len(value) <= MAX_ID_DIGITS
    ]
    Todo.objects.completed().filter(pk__in=ids).delete()
    return redirect("todo_list")
