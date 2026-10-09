from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from .forms import TodoEditForm, TodoForm
from .models import Todo

# Django refuses a form with more than 1,000 fields, and then nothing is
# deleted. So the delete-completed button offers at most this many, oldest
# first; the next click deletes the rest.
MAX_DELETE_AT_ONCE = 500

# A real id is a plain number. 18 digits always fit in SQLite's 64-bit integer;
# longer values may overflow.
MAX_ID_DIGITS = 18


def clean_id(value):
    """The id as plain digits without leading zeros, like "5"; or None if it is not an id.

    isascii() comes first: isdigit() also says yes to "５" and "²", and int("²") crashes.
    """
    if value and value.isascii() and value.isdigit() and len(value) <= MAX_ID_DIGITS:
        return str(int(value))
    return None


class Filter(NamedTuple):
    """One filter: everything about it is in this one row."""

    value: str  # the value in the address, ?show=<value>
    label: str  # the word on the link
    empty_message: str  # what the list says when nothing matches
    apply: Callable  # makes the list of to-dos smaller


# The one table of filters. The first row is the default: it needs no ?show=.
FILTERS = [
    Filter("all", "All", "Nothing to do yet. Add something above.", lambda t: t),
    Filter("active", "Active", "Nothing left to do.", lambda t: t.remaining()),
    Filter("completed", "Completed", "Nothing completed yet.", lambda t: t.completed()),
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
    # `selected` is always the last key: later checks (search, sort) go above.
    selected = clean_id(data.get("selected"))
    if selected is not None:
        params["selected"] = selected
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


def without_selected(params):
    """The list parameters without the selection."""
    return {k: v for k, v in params.items() if k != "selected"}


def select_base(params):
    """The start of every title link: "/?show=active&selected=". The template adds the id."""
    others = without_selected(params)
    return (
        reverse("todo_list")
        + (list_query(others) + "&" if others else "?")
        + "selected="
    )


def selected_todo(todos, params):
    """The selected to-do, taken ONLY from the to-dos on the page; else None.

    Never look it up by id: a to-do that is not on the page (deleted, filtered
    out, or later: not yours) must give the same page as no selection.
    Everything that changes `todos` must come BEFORE this call.
    """
    wanted = params.get("selected")
    if wanted is None:
        return None
    return next((todo for todo in todos if str(todo.pk) == wanted), None)


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
    # Everything that changes `todos` (search, sort, ...) goes above this line.
    selected = selected_todo(todos, params)
    if selected is None:
        params.pop("selected", None)  # then the page is exactly the page without it
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
        "selected": selected,
        "select_base": select_base(params),
        "close_url": reverse("todo_list") + list_query(without_selected(params)),
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


@require_http_methods(["GET", "HEAD", "POST"])
def todo_edit(request, pk):
    """GET shows the edit form with the saved values. POST saves a good form.

    A bad form shows the page again, with the errors and what the person typed.
    The template gets `pk`, not the to-do, so it never shows a title that was
    not saved.
    """
    todo = get_object_or_404(Todo, pk=pk)
    params = list_params(request.GET)
    if request.method == "POST":
        form = TodoEditForm(request.POST, instance=todo)
        if form.is_valid():
            form.save()
            return back_to_list(request)
    else:
        form = TodoEditForm(instance=todo)
    return render(
        request,
        "todos/todo_edit.html",
        {
            "pk": pk,
            "form": form,
            "list_query": list_query(params),
            "list_url": reverse("todo_list") + list_query(params),
        },
    )


@require_POST
def todo_delete(request, pk):
    todo = get_object_or_404(Todo, pk=pk)
    todo.delete()
    return back_to_list(request)


@require_POST
def todo_delete_completed(request):
    """Delete the completed to-dos whose ids the page sent, and only those."""
    ids = [pk for value in request.POST.getlist("ids") if (pk := clean_id(value))]
    Todo.objects.completed().filter(pk__in=ids).delete()
    return back_to_list(request)
