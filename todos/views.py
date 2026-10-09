import unicodedata
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import urlencode

from django.db import DatabaseError, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.http import Http404
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
    no_match_start: str  # with a search: the message before the word
    apply: Callable  # makes the list of to-dos smaller


# The one table of filters. The first row is the default: it needs no ?show=.
FILTERS = [
    Filter(
        "all",
        "All",
        "Nothing to do yet. Add something above.",
        "No to-dos match",
        lambda t: t,
    ),
    Filter(
        "active",
        "Active",
        "Nothing left to do.",
        "No active to-dos match",
        lambda t: t.remaining(),
    ),
    Filter(
        "completed",
        "Completed",
        "Nothing completed yet.",
        "No completed to-dos match",
        lambda t: t.completed(),
    ),
]
DEFAULT_FILTER = FILTERS[0]
FILTER_BY_VALUE = {f.value: f for f in FILTERS}

# The sort links: (the value in the address, the word on the page, the order).
# The first one is the default: it needs no ?sort=. Every order starts with
# "done" (False before True), so completed to-dos go last (owner decision).
# Every order ends with created_at, then pk, so ties never jump. nulls_last
# puts "no due date" last.
DUE_SOONEST_FIRST = F("due_date").asc(nulls_last=True)
SORTS = [
    ("created", "Date added", ("done", "created_at", "pk")),
    ("due", "Due date", ("done", DUE_SOONEST_FIRST, "-priority", "created_at", "pk")),
    (
        "priority",
        "Priority",
        ("done", "-priority", DUE_SOONEST_FIRST, "created_at", "pk"),
    ),
    ("title", "Title", ("done", Lower("title"), "created_at", "pk")),
]
DEFAULT_SORT = SORTS[0][0]
SORT_ORDERS = {value: order for value, _label, order in SORTS}

# The longest search, in characters (code points): the title's max_length,
# 200, so any title can be pasted whole. The server cuts the search to this.
SEARCH_MAX_LENGTH = Todo._meta.get_field("title").max_length
# The browser counts a box's maxlength in UTF-16 units, and one character (an
# emoji) can take two. So the box allows twice as many; the server still cuts.
SEARCH_BOX_MAXLENGTH = 2 * SEARCH_MAX_LENGTH

# The zero-width non-joiner and joiner are format characters too, but Persian,
# Hindi and emoji need them inside a word, so they are kept.
KEPT_FORMAT_CHARACTERS = {"‌", "‍"}


def is_invisible(ch):
    """True for a control or format character that a search must not keep."""
    if ch.isspace() or ch in KEPT_FORMAT_CHARACTERS:
        return False
    return unicodedata.category(ch) in ("Cc", "Cf")


def clean_search(text):
    """The search word: no invisible characters, one space between words.

    At most SEARCH_MAX_LENGTH characters (the title's max_length, 200).
    Invisible characters are control characters (like the "null" character)
    and format characters (like a zero-width space), but not the two joiners.
    White space is kept for the next step, which turns every kind of it (also
    the wide Japanese space) into one normal space. The cut comes last, so
    removed characters do not count.
    """
    text = "".join(ch for ch in text if not is_invisible(ch))
    text = " ".join(text.split())
    return text[:SEARCH_MAX_LENGTH].rstrip()


def list_params(data):
    """The list parameters in the address that we know, without the defaults.

    Anything we do not know is dropped, so it can never reach a redirect.
    """
    params = {}
    show = data.get("show")
    if show in FILTER_BY_VALUE and show != DEFAULT_FILTER.value:
        params["show"] = show
    q = clean_search(data.get("q") or "")
    if q:
        params["q"] = q
    # Only a value from SORTS is kept; the default is dropped, like show=all.
    if data.get("sort") in SORT_ORDERS and data["sort"] != DEFAULT_SORT:
        params["sort"] = data["sort"]
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


def search_words(q):
    """The search word as typed, and its NFKC form if that is different.

    NFKC turns wide letters into normal ones: "ｍｉｌｋ" becomes "milk".
    """
    words = [q]
    plain = unicodedata.normalize("NFKC", q)
    if plain != q:
        words.append(plain)
    return words


def search_todos(todos, params):
    """Only the to-dos whose title or notes contain the search word, as typed
    or in its NFKC form.

    With a search, each to-do also gets `title_match`: True when the title
    matched. The page shows "matches in notes" when it is False. The database
    works it out in the same query (an annotation).
    """
    q = params.get("q")
    if not q:
        return todos
    title_match = Q()
    notes_match = Q()
    for word in search_words(q):
        title_match |= Q(title__icontains=word)
        notes_match |= Q(notes__icontains=word)
    return todos.filter(title_match | notes_match).annotate(title_match=title_match)


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


def sort_todos(todos, params):
    """The to-dos in the chosen order. Ties keep the order they were added."""
    return todos.order_by(*SORT_ORDERS[params.get("sort", DEFAULT_SORT)])


def sort_links(params):
    """The Sort by links, each one keeping the other parameters."""
    chosen = params.get("sort", DEFAULT_SORT)
    return [
        {
            "label": label,
            "url": reverse("todo_list")
            + list_query(list_params({**params, "sort": value})),
            "current": value == chosen,
        }
        for value, label, _order in SORTS
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
    todos = search_todos(todos, params)
    todos = sort_todos(todos, params)
    # Everything that changes `todos` (search, sort, ...) goes above this line.
    selected = selected_todo(todos, params)
    if selected is None:
        params.pop("selected", None)  # then the page is exactly the page without it
    without_q = {k: v for k, v in params.items() if k != "q"}
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
        "sort_links": sort_links(params),
        "selected": selected,
        "select_base": select_base(params),
        "close_url": reverse("todo_list") + list_query(without_selected(params)),
        "q": params.get("q", ""),
        "no_match_start": chosen_filter(params).no_match_start,
        "search_box_maxlength": SEARCH_BOX_MAXLENGTH,
        "search_keeps": list(without_q.items()),
        "clear_search_url": reverse("todo_list") + list_query(without_q),
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
            edited = form.save(commit=False)
            try:
                # Only change a row that is there. A plain save() would make
                # the to-do again if someone deleted it a moment ago. The
                # atomic block keeps a failed save from breaking the rest of
                # the request's database work.
                with transaction.atomic():
                    edited.save(force_update=True)
            except DatabaseError:
                raise Http404("This to-do was deleted.") from None
            form.save_m2m()
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
