from collections.abc import Callable
from typing import NamedTuple
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

class Filter(NamedTuple):
    """One filter: everything about it is in this one row."""

    value: str  # the value in the address, ?show=<value>
    label: str  # the word on the link
    empty_message: str  # what the list says when nothing matches
    apply: Callable  # makes the list of to-dos smaller


# The one table of filters. The first row is the default: it needs no ?show=.
FILTERS = [
    Filter("all", "All", "Nothing to do yet. Add something above.", lambda t: t),
    Filter("active", "Active", "Nothing left to do.", lambda t: t.filter(done=False)),
    Filter(
        "completed",
        "Completed",
        "Nothing completed yet.",
        lambda t: t.filter(done=True),
    ),
]
DEFAULT_FILTER = FILTERS[0]
FILTER_BY_VALUE = {f.value: f for f in FILTERS}


def list_params(data):
    """The list parameters in the address that we know, without the defaults.

    Anything we do not know is dropped, so it can never reach a redirect.
    """
    params = {}
    show = data.get("show")
    if show in FILTER_BY_VALUE and show != DEFAULT_FILTER.value:
        params["show"] = show
    return params


def chosen_filter(params):
    """The Filter row that the list parameters ask for."""
    return FILTER_BY_VALUE[params.get("show", DEFAULT_FILTER.value)]


def list_query(params):
    """The text to put after an address: "?show=active", or "" for none."""
    return "?" + urlencode(params) if params else ""


def filter_todos(todos, params):
    """Only the to-dos the filter asks for."""
    return chosen_filter(params).apply(todos)


def filter_links(params):
    """The All, Active and Completed links, each one keeping the other parameters."""
    chosen = chosen_filter(params)
    return [
        {
            "label": f.label,
            "url": reverse("todo_list")
            + list_query(list_params({**params, "show": f.value})),
            "current": f == chosen,
        }
        for f in FILTERS
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
        "empty_message": chosen_filter(params).empty_message,
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
