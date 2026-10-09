import unicodedata
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import urlencode

from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import UserCreationForm
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from .forms import SubtaskForm, TodoEditForm, TodoForm, TodoListForm
from .models import TAG_MAX_LENGTH, Todo, TodoList, clean_tag_name
from .ordering import DIRECTIONS, DOWN, UP, move, move_limits

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
# "My order" (reorder, 16): by position, the empty ones last. Like
# TodoQuerySet.in_my_order, with the completed to-dos last.
MY_ORDER = F("position").asc(nulls_last=True)
SORTS = [
    ("created", "Date added", ("done", "created_at", "pk")),
    ("due", "Due date", ("done", DUE_SOONEST_FIRST, "-priority", "created_at", "pk")),
    (
        "priority",
        "Priority",
        ("done", "-priority", DUE_SOONEST_FIRST, "created_at", "pk"),
    ),
    ("title", "Title", ("done", Lower("title"), "created_at", "pk")),
    # The last link (owner decision: "Date added" stays the default).
    ("manual", "My order", ("done", MY_ORDER, "created_at", "pk")),
]
DEFAULT_SORT = SORTS[0][0]
# The sort that shows the Move up / Move down buttons.
MANUAL_SORT = "manual"
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
    # Tags (14): only the shape is checked here (no database), like show and q.
    tag = clean_tag_name(data.get("tag") or "")
    if tag and len(tag) <= TAG_MAX_LENGTH:
        params["tag"] = tag
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


def tag_todos(todos, params):
    """Only the to-dos with the chosen tag: a tag of the to-do's LIST owner.

    `todos` already has only the to-dos of this list. F("todo_list__owner")
    reads the list's owner from the same row, so another person's tag of the
    same name never matches (also on a shared list, later).
    """
    tag = params.get("tag")
    if tag:
        return todos.filter(tags__name=tag, tags__owner=F("todo_list__owner"))
    return todos


def without(params, *names):
    """The list parameters without these names."""
    return {k: v for k, v in params.items() if k not in names}


def filter_links(params, list_id):
    """The All, Active and Completed links, each one keeping the other parameters."""
    chosen = chosen_filter(params)
    return [
        {
            "label": f.label,
            "url": reverse("todo_list", args=[list_id])
            + list_query(list_params({**params, "show": f.value})),
            "current": f == chosen,
        }
        for f in FILTERS
    ]


def sort_todos(todos, params):
    """The to-dos in the chosen order. Ties keep the order they were added."""
    return todos.order_by(*SORT_ORDERS[params.get("sort", DEFAULT_SORT)])


def sort_links(params, list_id):
    """The Sort by links, each one keeping the other parameters."""
    chosen = params.get("sort", DEFAULT_SORT)
    return [
        {
            "label": label,
            "url": reverse("todo_list", args=[list_id])
            + list_query(list_params({**params, "sort": value})),
            "current": value == chosen,
        }
        for value, label, _order in SORTS
    ]


def without_selected(params):
    """The list parameters without the selection."""
    return {k: v for k, v in params.items() if k != "selected"}


def select_base(params, list_id):
    """The start of every title link: "/lists/1/?show=active&selected=". The template adds the id."""
    others = without_selected(params)
    return (
        reverse("todo_list", args=[list_id])
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


def list_url(request, list_id):
    """The address of a list page, with the same list parameters as this request."""
    return reverse("todo_list", args=[list_id]) + list_query(list_params(request.GET))


def back_to_list(request, list_id):
    """Send the browser back to the list `list_id`, with the same list parameters.

    The address always starts from our own list page. `list_id` is a number
    the view already has (like `todo.todo_list_id`), so no extra query.
    """
    return redirect(list_url(request, list_id))


def get_list(request, list_id):
    """A list this person may use, or 404."""
    return get_object_or_404(TodoList.objects.for_user(request.user), pk=list_id)


def get_owned_list(request, list_id):
    """A list this person owns, or 404. For rename and delete."""
    return get_object_or_404(TodoList.objects.owned_by(request.user), pk=list_id)


def list_todos(request, current_list):
    """Every to-do of the open list. Every query starts with for_user, then the list."""
    return Todo.objects.for_user(request.user).filter(todo_list=current_list)


def shown_todos(request, current_list, params):
    """The to-dos the page shows, before the sort: the filter, the search and the tag.

    The list page and the Move buttons both use this, so they never disagree
    about which rows are on the page.
    """
    todos = list_todos(request, current_list)
    todos = filter_todos(todos, params)
    todos = search_todos(todos, params)
    return tag_todos(todos, params)


# The session key of the last move: {"pk", "direction", "moved"}.
MOVED_SESSION_KEY = "todos_last_move"


def after_move(last_move, todos, no_up, no_down):
    """The button to focus, and the message, right after a move.

    `last_move` comes from the session (todo_move wrote it), so it is checked
    again: a dict with an int `pk` that is on this page and a known direction.
    Returns ({"pk", "direction"} or None, the message or "").
    The focus goes to the same button; if it is now disabled (the row reached
    the top or the bottom), to the other one. The message, like "Moved Buy
    milk up (2 of 5)", only when the to-do really moved; the numbers are its
    row on this page and the number of rows.
    """
    if not isinstance(last_move, dict):
        return None, ""
    pk, direction = last_move.get("pk"), last_move.get("direction")
    if not isinstance(pk, int) or direction not in DIRECTIONS:
        return None, ""
    rows = list(todos)  # the page's rows, already read by move_limits
    index = next((i for i, todo in enumerate(rows) if todo.pk == pk), None)
    if index is None:
        return None, ""
    disabled = {UP: no_up, DOWN: no_down}
    other = DOWN if direction == UP else UP
    focus = None
    for choice in (direction, other):
        if pk not in disabled[choice]:
            focus = {"pk": pk, "direction": choice}
            break
    status = ""
    if last_move.get("moved") is True:
        status = f"Moved {rows[index].title} {direction} ({index + 1} of {len(rows)})"
    return focus, status


def page_context(request, form, current_list):
    """What the list page needs. Both views use this, so a new key goes here once.

    Only the to-dos of the open list: every query starts with for_user, then
    the list, and every key comes from that.
    """
    params = list_params(request.GET)
    list_id = current_list.pk
    mine = list_todos(request, current_list)
    # Each to-do comes with its step counts, in the same query (no N+1).
    todos = shown_todos(request, current_list, params).with_subtask_progress()
    todos = sort_todos(todos, params)
    # The tags of every row in ONE more query; the rows read them from memory.
    todos = todos.prefetch_related("tags")
    # Everything that changes `todos` (search, sort, tags, ...) goes above this line.
    selected = selected_todo(todos, params)
    can_move = params.get("sort") == MANUAL_SORT
    # Reads the rows once; the template uses the same rows (no extra query).
    no_up, no_down = move_limits(todos) if can_move else (set(), set())
    # Read once, on any list page: an old note never comes back later.
    last_move = request.session.pop(MOVED_SESSION_KEY, None)
    move_focus, move_status = (
        after_move(last_move, todos, no_up, no_down) if can_move else (None, "")
    )
    if move_focus is not None:
        # A browser focuses the FIRST element with autofocus: the add box
        # gives it up, so the focus stays on the row that moved. (The form's
        # widgets are copies: this changes only this page.)
        form.fields["title"].widget.attrs.pop("autofocus", None)
    if selected is None:
        params.pop("selected", None)  # then the page is exactly the page without it
    without_q = {k: v for k, v in params.items() if k != "q"}
    here = reverse("todo_list", args=[list_id])
    return {
        "todos": todos,
        "form": form,
        "has_todos": mine.exists(),
        "remaining_count": mine.remaining().count(),
        "completed_ids": list(
            mine.completed()
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)[:MAX_DELETE_AT_ONCE]
        ),
        "empty_message": chosen_filter(params).empty_message,
        "current_tag": params.get("tag", ""),
        # A tag link shows a new group: it drops the selection (the pane closes).
        "tag_link_prefix": here
        + list_query({**without(params, "tag", "selected"), "tag": ""}),
        "clear_tag_url": here + list_query(without(params, "tag")),
        "list_query": list_query(params),
        "filter_links": filter_links(params, list_id),
        "sort_links": sort_links(params, list_id),
        "selected": selected,
        "select_base": select_base(params, list_id),
        "close_url": reverse("todo_list", args=[list_id])
        + list_query(without_selected(params)),
        "q": params.get("q", ""),
        "no_match_start": chosen_filter(params).no_match_start,
        "search_box_maxlength": SEARCH_BOX_MAXLENGTH,
        "search_keeps": list(without_q.items()),
        "clear_search_url": reverse("todo_list", args=[list_id])
        + list_query(without_q),
        "current_list": current_list,
        "lists": TodoList.objects.for_user(request.user),
        "can_move": can_move,
        "no_up_ids": no_up,
        "no_down_ids": no_down,
        "move_focus": move_focus,
        "move_status": move_status,
    }


def home(request):
    """`/`: only sends the browser to the person's first own list. A GET only reads."""
    first = TodoList.objects.owned_by(request.user).first()
    if first is None:
        # A user from before lists, from createsuperuser, or who deleted
        # every list. GET never makes anything: "New list" does.
        return redirect("list_create")
    return redirect("todo_list", list_id=first.pk)


def todo_list(request, list_id):
    current_list = get_list(request, list_id)
    return render(
        request,
        "todos/todo_list.html",
        page_context(request, TodoForm(), current_list),
    )


@require_POST
def todo_add(request, list_id):
    current_list = get_list(request, list_id)
    form = TodoForm(request.POST)
    if form.is_valid():
        # The list is in the address, never in the form. save() sets the
        # owner from the list.
        form.instance.todo_list = current_list
        try:
            # The database checks the list when this commits.
            with transaction.atomic():
                form.save()
        except IntegrityError:
            # Another tab deleted the list a moment ago: like a list that
            # does not exist.
            raise Http404("This list was deleted.") from None
        return back_to_list(request, current_list.pk)
    return render(
        request, "todos/todo_list.html", page_context(request, form, current_list)
    )


# What the Done and Undo buttons send: the state the person wants. A second
# Done (a double click, an old tab) then changes nothing.
WANTED = {"1": True, "0": False}


@require_POST
def todo_toggle(request, pk):
    """Done (done=1) or Undo (done=0). Anything else is a bad request: 400."""
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    target = WANTED.get(request.POST.get("done"))
    if target is None:
        return HttpResponseBadRequest("done must be 1 or 0")
    todo.set_done(target)
    return back_to_list(request, todo.todo_list_id)


@require_POST
def todo_move(request, pk):
    """Move up (direction=up) or Move down (direction=down) in My order.

    The neighbour is the next row the page shows: the same filter and search
    as the page (the list query). Anything else is a bad request: 400.
    """
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    direction = request.POST.get("direction")
    if direction not in DIRECTIONS:
        return HttpResponseBadRequest("direction must be up or down")
    current_list = get_list(request, todo.todo_list_id)
    params = list_params(request.GET)
    moved = move(todo, shown_todos(request, current_list, params), direction)
    # The next list page puts the focus back on this button and says what
    # happened (after_move). Kept in the session, read once.
    request.session[MOVED_SESSION_KEY] = {
        "pk": todo.pk,
        "direction": direction,
        "moved": moved,
    }
    # Back to the moved row: the browser scrolls to it. The fragment is
    # built from the integer pk, never from the request.
    return redirect(list_url(request, current_list.pk) + f"#todo-{todo.pk}")


@require_http_methods(["GET", "HEAD", "POST"])
def todo_edit(request, pk):
    """GET shows the edit form with the saved values. POST saves a good form.

    A bad form shows the page again, with the errors and what the person typed.
    The template gets `pk`, not the to-do, so it never shows a title that was
    not saved.
    """
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    params = list_params(request.GET)
    # Save and Cancel go back to the list the person came from, also after a
    # move (owner decision): the to-do is gone from it, which shows it moved.
    came_from = todo.todo_list_id
    if request.method == "POST":
        form = TodoEditForm(request.POST, instance=todo, user=request.user)
        if form.is_valid():
            edited = form.save(commit=False)
            edited.edited = True  # Undo never deletes a to-do a person edited
            # The to-do and its tags are saved together, or not at all.
            with transaction.atomic():
                try:
                    # Only change a row that is there. A plain save() would
                    # make the to-do again if someone deleted it a moment ago.
                    # The inner atomic block keeps a failed save from breaking
                    # the rest of the request's database work.
                    with transaction.atomic():
                        edited.save(force_update=True)
                except DatabaseError:
                    raise Http404("This to-do was deleted.") from None
                form.save_m2m()
            return back_to_list(request, came_from)
    else:
        form = TodoEditForm(instance=todo, user=request.user)
    return render(
        request,
        "todos/todo_edit.html",
        {
            "pk": pk,
            "form": form,
            "list_query": list_query(params),
            "list_url": list_url(request, came_from),
        },
    )


@require_POST
def todo_delete(request, pk):
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    list_id = todo.todo_list_id  # kept: after delete() the to-do is gone
    todo.delete()
    return back_to_list(request, list_id)


@require_POST
def todo_delete_completed(request, list_id):
    """Delete the completed to-dos whose ids the page sent, and only those."""
    ids = [pk for value in request.POST.getlist("ids") if (pk := clean_id(value))]
    # One delete for all of them. Django also deletes their steps (CASCADE),
    # in one more query. Never delete them one by one in a loop.
    # Only the person's own: another person's ids delete nothing.
    # Only this list's: an id from another list is ignored, even the person's own.
    current_list = get_list(request, list_id)
    Todo.objects.for_user(request.user).filter(
        todo_list=current_list
    ).completed().filter(pk__in=ids).delete()
    return back_to_list(request, current_list.pk)


# Lists (13): make, rename and delete. Rename and delete are owner-only
# (get_owned_list). There is no "all lists" page: the lists <nav> on the list
# page is the index.


def came_from_list(request):
    """The list "New list" was opened from (`?from=<id>`), only if this person
    may use it; else None. Never an address from the request: only an id.
    """
    list_id = clean_id(request.GET.get("from"))
    if list_id is None:
        return None
    return TodoList.objects.for_user(request.user).filter(pk=list_id).first()


def list_form_page(request, form, current_list=None):
    """The "New list" page (no current_list) or the "Rename or delete" page."""
    context = {"form": form, "current_list": current_list}
    if current_list is None:
        came_from = came_from_list(request)
        # The form posts to the same address, so Cancel still knows after an error.
        context["from_query"] = list_query({"from": came_from.pk}) if came_from else ""
        if came_from is not None:
            context["cancel_url"] = reverse("todo_list", args=[came_from.pk])
        elif TodoList.objects.for_user(request.user).exists():
            context["cancel_url"] = reverse("home")
        else:
            # No Cancel without a list: "/" would come back here.
            context["cancel_url"] = None
    else:
        context["cancel_url"] = reverse("todo_list", args=[current_list.pk])
        # For the delete button: "Delete list and its 3 to-dos". One COUNT.
        context["todo_count"] = current_list.todos.count()
    return render(request, "todos/list_form.html", context)


def posted(request):
    """The form data on a POST, else None. An empty POST is still a POST: its
    form shows "This field is required." (`request.POST or None` would not).
    """
    return request.POST if request.method == "POST" else None


def save_list(form):
    """Save a good list form; the list, or None.

    Two requests with the same new name can both pass clean_name. Then the
    database refuses the second one (the unique constraint), and the form
    shows the same message as clean_name.
    """
    try:
        with transaction.atomic():
            return form.save()
    except IntegrityError:
        name = form.cleaned_data["name"]
        form.add_error("name", TodoListForm.name_used_message(name))
        return None


@require_http_methods(["GET", "HEAD", "POST"])
def list_create(request):
    form = TodoListForm(posted(request), owner=request.user)
    if request.method == "POST" and form.is_valid():
        form.instance.owner = request.user  # never from the form
        new_list = save_list(form)
        if new_list is not None:
            return redirect("todo_list", list_id=new_list.pk)
    return list_form_page(request, form)


@require_http_methods(["GET", "HEAD", "POST"])
def list_edit(request, list_id):
    """GET: the rename form and the delete button. POST: rename."""
    current_list = get_owned_list(request, list_id)
    form = TodoListForm(posted(request), instance=current_list, owner=request.user)
    if request.method == "POST" and form.is_valid() and save_list(form):
        return redirect("todo_list", list_id=current_list.pk)
    if form.errors:
        # The heading and Cancel keep the saved name, not the one typed.
        current_list.refresh_from_db()
    return list_form_page(request, form, current_list)


@require_POST
def list_delete(request, list_id):
    """Delete the list AND its to-dos (owner decision; CASCADE). The button said how many."""
    current_list = get_owned_list(request, list_id)
    current_list.delete()
    return redirect("home")


# Steps (subtasks): each to-do's own small page, /<id>/subtasks/.
# A step is ALWAYS looked up among its to-do's steps (get_subtask_or_404), so
# a link can only change a step of the to-do in its own address.


def subtask_page(request, todo, subtask_form):
    """The steps page of one to-do. subtask_list and subtask_add's error path use this.

    `todo` was found through its owner. The template gets `pk` and `title`,
    not the to-do, like the edit page.
    """
    params = list_params(request.GET)
    return render(
        request,
        "todos/subtask_list.html",
        {
            "pk": todo.pk,
            "title": todo.title,
            "subtasks": todo.subtasks.all(),
            "subtask_form": subtask_form,
            "list_query": list_query(params),
            "list_url": list_url(request, todo.todo_list_id),
        },
    )


def back_to_subtasks(request, pk):
    """Back to the steps page, with the same list settings. Always our own page."""
    return redirect(
        reverse("subtask_list", args=[pk]) + list_query(list_params(request.GET))
    )


def subtask_list(request, pk):
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    return subtask_page(request, todo, SubtaskForm())


@require_POST
def subtask_add(request, pk):
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    form = SubtaskForm(request.POST)
    if form.is_valid():
        form.instance.todo = todo
        with transaction.atomic():
            form.save()
            todo.mark_edited()
        return back_to_subtasks(request, pk)
    return subtask_page(request, todo, form)


def get_subtask_or_404(request, pk, subtask_pk):
    """The to-do `pk` and its step `subtask_pk`, or 404.

    First the to-do, through its owner, then the step among ITS steps
    (`todo.subtasks`), so a link can never change a step of another to-do or
    of another person. Looking up the to-do first also turns an id too big
    for the database into a 404, not a crash. Sharing (20) changes only the
    first line.
    """
    todo = get_object_or_404(Todo.objects.for_user(request.user), pk=pk)
    return todo, get_object_or_404(todo.subtasks, pk=subtask_pk)


@require_POST
def subtask_done(request, pk, subtask_pk):
    """Done (done=1) or Undo (done=0) on one step. It never changes the to-do."""
    todo, subtask = get_subtask_or_404(request, pk, subtask_pk)
    wanted = WANTED.get(request.POST.get("done"))
    if wanted is None:
        return HttpResponseBadRequest("done must be 1 or 0")
    subtask.done = wanted
    with transaction.atomic():
        subtask.save(update_fields=["done"])
        todo.mark_edited()
    return back_to_subtasks(request, pk)


@require_POST
def subtask_delete(request, pk, subtask_pk):
    todo, subtask = get_subtask_or_404(request, pk, subtask_pk)
    with transaction.atomic():
        subtask.delete()
        todo.mark_edited()
    return back_to_subtasks(request, pk)


# Accounts (17). Log in and log out are Django's own views (config/urls.py).


@login_not_required
@require_http_methods(["GET", "POST"])
def signup(request):
    """Sign up with a username and a password, then be logged in.

    Django's UserCreationForm checks the password with the validators in
    settings.py (too short, too common, only numbers, too like the username).
    """
    if request.user.is_authenticated:
        return redirect("home")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # All of it, or nothing: never a user without their first list.
        with transaction.atomic():
            user = form.save()
            TodoList.objects.create_default(user)
        login(request, user)
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})
