from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import TodoForm
from .models import Todo

# Django refuses a form with more than 1,000 fields, and then nothing is
# deleted. So the delete-completed button offers at most this many, oldest
# first; the next click deletes the rest.
MAX_DELETE_AT_ONCE = 500

# The filter links: (the value in the address, the word on the page).
FILTERS = [("all", "All"), ("active", "Active"), ("completed", "Completed")]


def list_params(data):
    """The list parameters in the address that we know, without the defaults.

    Anything we do not know is dropped, so it can never reach a redirect.
    """
    params = {}
    if data.get("show") in ("active", "completed"):
        params["show"] = data["show"]
    return params


def list_query(params):
    """The text to put after an address: "?show=active", or "" for none."""
    return "?" + urlencode(params) if params else ""


def filter_todos(todos, params):
    """Only the to-dos the filter asks for."""
    show = params.get("show")
    if show == "active":
        return todos.filter(done=False)
    if show == "completed":
        return todos.filter(done=True)
    return todos


def filter_links(params):
    """The All, Active and Completed links, each one keeping the other parameters."""
    chosen = params.get("show", "all")
    return [
        {
            "label": label,
            "url": reverse("todo_list")
            + list_query(list_params({**params, "show": value})),
            "current": value == chosen,
        }
        for value, label in FILTERS
    ]


def back_to_list(request):
    """Send the browser back to the list, with the same list parameters.

    The address always starts from our own list page.
    """
    return redirect(reverse("todo_list") + list_query(list_params(request.GET)))


def page_context(request, form):
    """What the list page needs. Both views use this, so a new key goes here once."""
    params = list_params(request.GET)
    todos = Todo.objects.all()
    todos = filter_todos(todos, params)
    return {
        "todos": todos,
        "form": form,
        "has_todos": Todo.objects.exists(),
        "remaining_count": Todo.objects.remaining().count(),
        "completed_ids": list(
            Todo.objects.completed()
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)[:MAX_DELETE_AT_ONCE]
        ),
        "show": params.get("show", "all"),
        "list_query": list_query(params),
        "filter_links": filter_links(params),
    }


def todo_list(request):
    return render(request, "todos/todo_list.html", page_context(request, TodoForm()))


@require_POST
def todo_add(request):
    form = TodoForm(request.POST)
    if form.is_valid():
        form.save()
        return back_to_list(request)
    return render(request, "todos/todo_list.html", page_context(request, form))


@require_POST
def todo_toggle(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    todo.done = not todo.done
    todo.save()
    return back_to_list(request)


@require_POST
def todo_delete(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    todo.delete()
    return back_to_list(request)


# A real id is a plain number. 18 digits always fit in SQLite's 64-bit integer;
# longer values may overflow.
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
