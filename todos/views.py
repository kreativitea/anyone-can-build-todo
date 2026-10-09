from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import TodoForm
from .models import Todo


def page_context(form):
    """What the list page needs. Both views use this, so a new key goes here once."""
    return {
        "todos": Todo.objects.all(),
        "form": form,
    }


def todo_list(request):
    return render(request, "todos/todo_list.html", page_context(TodoForm()))


@require_POST
def todo_add(request):
    form = TodoForm(request.POST)
    if form.is_valid():
        form.save()
        return redirect("todo_list")
    return render(request, "todos/todo_list.html", page_context(form))


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
