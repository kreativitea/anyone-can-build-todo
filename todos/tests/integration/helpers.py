"""Helpers that more than one integration test file uses.

They read the page, or build parts of it exactly as the page must show them,
so the tests can compare whole things instead of searching for a few words.
"""

import re
from html.parser import HTMLParser
from typing import NamedTuple

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils.html import escape

from todos.models import Todo, TodoList

# A test value only, for test users. Not a real password.
TEST_PASSWORD = "plum-tree-river-42"

# The account addresses (17).
LOGIN_URL = "/accounts/login/"
SIGNUP_URL = "/accounts/signup/"
LOGOUT_URL = "/accounts/logout/"


def make_user(username="ana"):
    """A saved user with the test password, and their first list "My to-dos",
    like sign-up gives (lists, 13).
    """
    user = get_user_model().objects.create_user(username, password=TEST_PASSWORD)
    TodoList.objects.create_default(user)
    return user


def first_list(user):
    """The person's first list: "My to-dos" for a user from make_user."""
    return TodoList.objects.owned_by(user).first()


def list_path(list_id, query=""):
    """The address of a list page, like "/lists/1/?show=active"."""
    return f"/lists/{list_id}/{query}"


class LoggedInTestCase(TestCase):
    """A test where "ana" is logged in. self.make_todo() makes her to-dos, in
    her list "My to-dos" (`cls.todo_list`) unless `todo_list` says otherwise.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = make_user("ana")
        cls.todo_list = first_list(cls.user)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def csrf_client(self):
        """A second client, logged in as ana, that checks CSRF like a real browser."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        return client

    def make_todo(self, todo_list=None, **fields):
        """A saved to-do in `todo_list`, or in ana's "My to-dos". The owner
        follows the list (Todo.save).
        """
        return Todo.objects.create(todo_list=todo_list or self.todo_list, **fields)

    def list_url(self, todo_list=None, query=""):
        """The address of a list page: ana's "My to-dos" unless `todo_list` says
        otherwise, then `query` (like "?show=active").
        """
        return list_path((todo_list or self.todo_list).pk, query)

    def add_url(self, todo_list=None, query=""):
        """The add form's address, for a list (ana's "My to-dos" by default)."""
        return list_path((todo_list or self.todo_list).pk, f"add/{query}")

    def delete_completed_url(self, todo_list=None, query=""):
        """The delete-completed address, for a list (ana's "My to-dos" by default)."""
        return list_path((todo_list or self.todo_list).pk, f"delete-completed/{query}")

    def list_footer(self, count_text, completed_ids=(), query="", todo_list=None):
        """list_footer() for a list: ana's "My to-dos" by default."""
        list_id = (todo_list or self.todo_list).pk
        return list_footer(count_text, completed_ids, query, list_id=list_id)

    def delete_completed_form(self, ids, query="", todo_list=None):
        """delete_completed_form() for a list: ana's "My to-dos" by default."""
        list_id = (todo_list or self.todo_list).pk
        return delete_completed_form(ids, query, list_id=list_id)


CSRF_INPUT = re.compile(
    r'<input type="hidden" name="csrfmiddlewaretoken" value="[^"]*">'
)


# The priority select box, exactly as a new, empty add form must draw it:
# High, Medium, Low, with Medium chosen.
PRIORITY_SELECT = (
    '<select name="priority" id="id_priority">'
    '<option value="3">High</option>'
    '<option value="2" selected>Medium</option>'
    '<option value="1">Low</option>'
    "</select>"
)


def page_without_csrf(response):
    """The page's HTML without the CSRF token inputs.

    The token is different every time the page is drawn, so a test cannot
    write it down. Taking it out lets a test compare whole forms exactly.
    """
    return CSRF_INPUT.sub("", response.content.decode())


def delete_completed_form(ids, query="", *, list_id):
    """The delete-completed form of the list `list_id`, exactly as the page must show it.

    `query` is the list query at the end of its address, like "?show=active".
    """
    hidden = "".join(f'<input type="hidden" name="ids" value="{pk}">' for pk in ids)
    count = len(ids)
    return (
        '<form class="delete-completed" method="post" '
        f'action="/lists/{list_id}/delete-completed/{query}">'
        f"{hidden}"
        f'<button type="submit">Delete {count} completed to-do'
        f"{'' if count == 1 else 's'}</button>"
        "</form>"
    )


def list_footer(count_text, completed_ids=(), query="", *, list_id=None):
    """The whole footer under the list `list_id`, exactly as the page must show it."""
    form = (
        delete_completed_form(completed_ids, query, list_id=list_id)
        if completed_ids
        else ""
    )
    return f'<div class="list-footer"><p class="count">{count_text}</p>{form}</div>'


def page_path(response):
    """The address of the page in `response`, with its query, like "/?show=active".

    After `follow=True` this is the page the browser ended on.
    """
    query = response.request.get("QUERY_STRING", "")
    return response.request["PATH_INFO"] + (f"?{query}" if query else "")


class PageButton:
    """A button that sends its form: its text, and the name/value it adds.

    `label` is its aria-label, or None when it has none.
    """

    def __init__(self, text, name=None, value="", label=None):
        self.text = text
        self.name = name
        self.value = value
        self.label = label

    @property
    def accessible_name(self):
        """What a screen reader says: the aria-label if there is one, else the text."""
        return self.label if self.label is not None else self.text

    def __repr__(self):
        return (
            f"PageButton({self.text!r}, name={self.name!r}, value={self.value!r}, "
            f"label={self.label!r})"
        )


class PageForm:
    """One form on the page: where it sends, and what it sends.

    `fields` maps each name to the LIST of values a browser would send, in
    order, because a name can repeat (like the "ids" of delete completed).
    `buttons` are the buttons that send this form.
    """

    def __init__(self, method, action):
        self.method = method
        self.action = action
        self.fields = {}
        self.field_names = set()  # every field, also an unchecked checkbox
        self.buttons = []

    def add(self, name, value):
        self.fields.setdefault(name, []).append(value)

    def data(self, button=None, **typed):
        """What a browser sends: the form's own fields, what a person typed,
        and the name/value of the button that was pressed (if it has a name).

        Typing into a field the form does not have is a mistake in the test or
        the page, so it fails at once. A typed value may be a list.
        """
        missing = set(typed) - self.field_names
        if missing:
            raise AssertionError(f"the form has no field {sorted(missing)}")
        data = {name: list(values) for name, values in self.fields.items()}
        for name, value in typed.items():
            data[name] = list(value) if isinstance(value, list | tuple) else [value]
        if button is not None:
            if button not in self.buttons:
                raise AssertionError(f"{button!r} is not a button of this form")
            if button.name:
                data.setdefault(button.name, []).append(button.value)
        return data


def collapse(pieces):
    """Text pieces joined with a space, with every run of spaces made one."""
    return " ".join(" ".join(pieces).split())


class PageForms(HTMLParser):
    """Reads every form on the page, and what a browser would send from it.

    The browser rules it follows: a repeated name keeps every value; a
    <textarea> sends its text; a <select> sends the selected option, or the
    FIRST option when none is selected; an unchecked checkbox or radio sends
    nothing; a disabled field sends nothing; <input type="submit"> is a button;
    a form with no action sends to the page's own address (`page_path`).
    """

    def __init__(self, html, page_path=""):
        super().__init__()
        self.page_path = page_path
        self.forms = []
        self._form = None
        self._button = None  # the text pieces of the button we are in
        self._textarea = None  # (name, text pieces)
        self._select = None  # {"name", "multiple", "options": [...]}
        self._option = None  # the option we are in
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            method = (attrs.get("method") or "get").lower()
            self._form = PageForm(method, attrs.get("action") or self.page_path)
            self.forms.append(self._form)
            return
        if self._form is None:
            return
        name = attrs.get("name")
        disabled = "disabled" in attrs
        if tag == "input":
            self._input(attrs, name, disabled)
        elif tag == "button":
            kind = (attrs.get("type") or "submit").lower()
            if kind == "submit" and not disabled:
                button = PageButton(
                    "", name, attrs.get("value", ""), attrs.get("aria-label")
                )
                self._form.buttons.append(button)
                self._button = []
        elif tag == "textarea" and name and not disabled:
            self._form.field_names.add(name)
            self._textarea = (name, [])
        elif tag == "select" and name and not disabled:
            self._form.field_names.add(name)
            self._select = {
                "name": name,
                "multiple": "multiple" in attrs,
                "options": [],
            }
        elif tag == "option" and self._select is not None:
            self._option = {
                "value": attrs.get("value"),
                "text": [],
                "selected": "selected" in attrs,
            }
            self._select["options"].append(self._option)

    def _input(self, attrs, name, disabled):
        kind = (attrs.get("type") or "text").lower()
        if kind == "submit":
            if not disabled:
                text = attrs.get("value") or "Submit"
                label = attrs.get("aria-label")
                self._form.buttons.append(PageButton(text, name, text, label))
            return
        if kind in ("button", "reset", "image", "file") or not name or disabled:
            return
        self._form.field_names.add(name)
        if kind in ("checkbox", "radio"):
            if "checked" in attrs:
                self._form.add(name, attrs.get("value") or "on")
            return
        self._form.add(name, attrs.get("value") or "")

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        elif tag == "button" and self._button is not None:
            self._form.buttons[-1].text = collapse(self._button)
            self._button = None
        elif tag == "textarea" and self._textarea is not None:
            name, pieces = self._textarea
            text = "".join(pieces)
            # A browser drops one newline right after <textarea>.
            text = text.removeprefix("\r\n") if text.startswith("\r\n") else text
            self._form.add(name, text.removeprefix("\n"))
            self._textarea = None
        elif tag == "option":
            self._option = None
        elif tag == "select" and self._select is not None:
            self._end_select()

    def _end_select(self):
        select, self._select, self._option = self._select, None, None
        options = select["options"]
        chosen = [option for option in options if option["selected"]]
        if not select["multiple"]:
            # One choice: the last one marked selected, else the first option.
            chosen = chosen[-1:] or options[:1]
        for option in chosen:
            value = option["value"]
            if value is None:
                value = collapse(option["text"])
            self._form.add(select["name"], value)

    def handle_data(self, data):
        if self._button is not None:
            self._button.append(data)
        elif self._textarea is not None:
            self._textarea[1].append(data)
        elif self._option is not None:
            self._option["text"].append(data)


def page_forms(response):
    """Every form on the page in `response`, read like a browser reads it."""
    return PageForms(response.content.decode(), page_path(response)).forms


def page_post_forms(response):
    """The POST forms of the page itself: not the account bar's Log out form."""
    return [
        form
        for form in page_forms(response)
        if form.method == "post" and form.action != LOGOUT_URL
    ]


class Row(NamedTuple):
    """One <li> of the list: its `id`, its classes, and the title in it."""

    id: str
    classes: list
    title: str


class PageParts(HTMLParser):
    """Reads the parts of the page the tests compare exactly.

    `post_actions` is the `action` of every form with method="post", read by
    `PageForms`, so a form with no action counts as the page's own address.
    The account bar's Log out form is not in it: it is on every page, and
    test_accounts.py checks it.
    `titles` is the title of every to-do shown, in order: the text of each
    <span class="title">, and of an <a> directly inside it (the title link).
    Other tags inside the span (the due date is a <small>) are not the title.
    `current_links` is the text of every link with aria-current="page". A test
    that compares it to one name proves that no OTHER link is marked too.
    `selected_titles` is the text of every title link with aria-current="true":
    the selected to-do. Sort links use "true" too, but they are not titles.
    `panes` is the aria-label of every <aside>, in order. [] means "no pane".
    `pane_notes` is the text of the pane's <dd class="notes">, with each <br>
    as "\\n" and HTML codes turned back into characters ("&lt;" is "<").
    None means there is no notes row.
    `pane_tags` is the name of every element inside the pane <aside>, in
    order, like ["h2", "dl", "dt", ...]. [] means "no pane".
    `html_lang` is the `lang` of the <html> element (None if it has none).
    """

    def __init__(self, html, page_path=""):
        super().__init__()
        self.post_actions = [
            form.action
            for form in PageForms(html, page_path).forms
            if form.method == "post" and form.action != LOGOUT_URL
        ]
        self.html_lang = None
        self.titles = []
        self.current_links = []
        self.selected_titles = []
        self.panes = []
        self.pane_notes = None
        self.pane_tags = []
        self._in_pane = False
        self._in_notes = False
        self.rows = []
        self._collect = []  # the lists that the next text goes into
        self._row = None  # the <li> we are in: [id, classes]
        self._title_depth = None  # tags open inside the title span, or None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self._pane_start(tag, attrs)
        if tag == "html":
            self.html_lang = attrs.get("lang")
        # Text inside a tag within the title (like the due date) is not the title.
        self._collect = []
        if self._title_depth is not None:
            self._title_depth += 1
            if tag == "a" and self._title_depth == 1:
                self._collect = [self.titles]
                if attrs.get("aria-current") == "true":
                    self.selected_titles.append("")
                    self._collect.append(self.selected_titles)
            return
        if tag == "li":
            self._row = [attrs.get("id"), (attrs.get("class") or "").split()]
        if tag == "span" and attrs.get("class") == "title":
            self.titles.append("")
            self._collect = [self.titles]
            self._title_depth = 0
        if tag == "a" and attrs.get("aria-current") == "page":
            self.current_links.append("")
            self._collect = [self.current_links]
        if tag == "aside":
            self.panes.append(attrs.get("aria-label"))

    def _pane_start(self, tag, attrs):
        """Read the inside of the pane: its tags, and its notes row."""
        if tag == "aside":
            self._in_pane = True
            return
        if not self._in_pane:
            return
        self.pane_tags.append(tag)
        if tag == "dd" and attrs.get("class") == "notes":
            self.pane_notes = ""
            self._in_notes = True
        elif tag == "br" and self._in_notes:
            self.pane_notes += "\n"

    def handle_endtag(self, tag):
        if tag == "aside":
            self._in_pane = False
        if tag == "dd":
            self._in_notes = False
        self._collect = []
        if self._title_depth is not None:
            if self._title_depth > 0:
                self._title_depth -= 1
                return
            self._title_depth = None
            if self._row is not None:
                self.rows.append(Row(*self._row, self.titles[-1]))
        if tag == "li":
            self._row = None

    def handle_data(self, data):
        if self._in_notes:
            self.pane_notes += data
        for target in self._collect:
            target[-1] += data.strip()

    def row(self, title):
        """The one row whose title is exactly `title`."""
        found = [row for row in self.rows if row.title == title]
        if len(found) != 1:
            raise AssertionError(f"{len(found)} rows titled {title!r}, not 1")
        return found[0]


def page_parts(response):
    """The parts of the page in `response` that tests compare exactly."""
    return PageParts(response.content.decode(), page_path(response))


def show_date(day):
    """A date as the page shows it: "5 Oct 2026" (no 0 before the day)."""
    return f"{day.day} {day:%b %Y}"


def title_element(
    todo, query="", selected=False, match_hint=False, repeat="", progress=""
):
    """The whole <span class="title"> of one row: the link, the search's
    "matches in notes" hint, the priority label (High or Low; Medium has none),
    the due date, the repeat and the steps progress.

    `query` is the list query without the selection, like "?show=active".
    `match_hint` is True when the search matched only the notes.
    `repeat` is the words an OPEN repeating to-do shows, like "Every week";
    "" means no repeat span (a to-do that does not repeat, or a completed one).
    `progress` is the whole "1 of 3 steps" element (its own line, last in the
    title block), or "" for a to-do with no steps.
    """
    joiner = "&" if query else "?"
    href = f"{list_path(todo.todo_list_id, escape(query))}{joiner}selected={todo.pk}#details"
    current = ' aria-current="true"' if selected else ""
    hint = '<small class="match-hint">matches in notes</small>' if match_hint else ""
    label = ""
    if todo.priority != todo.Priority.MEDIUM:
        name = todo.get_priority_display()
        label = f' <span class="priority {name.lower()}">{name} priority</span>'
    due = (
        f'<small class="due">due {show_date(todo.due_date)}</small>'
        if todo.due_date
        else ""
    )
    repeat_span = f'<span class="repeat">{repeat}</span>' if repeat else ""
    return (
        f'<span class="title"><a href="{href}"{current}>{escape(todo.title)}</a>'
        f"{hint}{label}{due}{repeat_span}{progress}</span>"
    )


def toggle_form(todo, done=False, query=""):
    """A row's Done (or, for a completed to-do, Undo) form, exactly, without
    the CSRF token. It sends the state the person wants: done=1 or done=0.
    """
    return (
        f'<form method="post" action="/{todo.pk}/toggle/{escape(query)}">'
        f'<input type="hidden" name="done" value="{0 if done else 1}">'
        f'<button type="submit">{"Undo" if done else "Done"}</button></form>'
    )


def pane_element(
    todo,
    *,
    status="Active",
    due="No due date",
    priority="Medium",
    created,
    close_url,
    notes=None,
    edit_url=None,
    repeats=None,
    steps=None,
):
    """The whole details <aside>, exactly as the page must show it.

    `close_url` is the list address without the selection, like "/lists/1/";
    the builder adds "#todo-<pk>". The pane shows every priority, Medium too.
    `notes` (None: no notes row) is plain text: each line is escaped, and the
    lines are joined with <br>, after the Created row.
    `edit_url` is the pane's Edit link: the edit page with the same list query,
    selection included. None builds it from `close_url`, like the page does.
    `repeats` (None: no Repeats row) is the words of the repeat, like
    "Every week". Its row comes right after Due.
    `steps` (None: no Steps row) is (done, total, href): the row "Steps: 1 of 3
    done", a link to the steps page. It comes before the notes.
    """
    if edit_url is None:
        query = close_url[close_url.index("?") :] if "?" in close_url else ""
        joiner = "&" if query else "?"
        edit_url = f"/{todo.pk}/edit/{query}{joiner}selected={todo.pk}"
    rows = [
        ("Status", status),
        ("Due", due),
        *([("Repeats", repeats)] if repeats is not None else []),
        ("Priority", priority),
        ("Created", created),
    ]
    dl = "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows)
    if steps is not None:
        done, total, href = steps
        dl += f'<dt>Steps</dt><dd><a href="{escape(href)}">{done} of {total} done</a></dd>'
    if notes is not None:
        lines = "<br>".join(escape(line) for line in notes.split("\n"))
        dl += f'<dt>Notes</dt><dd class="notes">{lines}</dd>'
    return (
        '<aside class="details" id="details" tabindex="-1" aria-label="Details">'
        f"<h2>{escape(todo.title)}</h2>"
        f"<dl>{dl}</dl>"
        f'<p class="details-actions"><a href="{escape(edit_url)}">Edit</a> '
        f'<a href="{close_url}#todo-{todo.pk}">Close</a></p>'
        "</aside>"
    )


class PageLinks(HTMLParser):
    """Reads every link on the page: its accessible name and its address.

    The name is the `aria-label` when the link has one (like a screen reader
    says it), else its text with the spaces made one.
    """

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.links = []  # (name, href)
        self._link = None  # [aria-label, href, text pieces]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            self._link = [attrs.get("aria-label"), attrs.get("href"), []]

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            label, href, text = self._link
            self.links.append((label if label is not None else collapse(text), href))
            self._link = None

    def handle_data(self, data):
        if self._link is not None:
            self._link[2].append(data)


def link_href(response, name):
    """The address of the one link whose whole name is exactly `name`, like a click.

    It fails when no link, or more than one link, has that name.
    """
    hrefs = [
        href
        for link_name, href in PageLinks(response.content.decode()).links
        if link_name == name
    ]
    if len(hrefs) != 1:
        raise AssertionError(f"{len(hrefs)} links named {name!r}, not 1")
    return hrefs[0]


# Accounts (17).


def account_bar(username):
    """The account bar at the top of every page, exactly, without the CSRF token."""
    return (
        '<div class="account">'
        f"Logged in as <strong>{escape(username)}</strong>"
        f'<form method="post" action="{LOGOUT_URL}">'
        '<button type="submit">Log out</button></form>'
        "</div>"
    )


class ClassCounter(HTMLParser):
    """Counts the elements with one tag and one exact class, like <div class="account">."""

    def __init__(self, html, tag, class_name):
        super().__init__()
        self.tag = tag
        self.class_name = class_name
        self.count = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == self.tag and dict(attrs).get("class") == self.class_name:
            self.count += 1


def count_elements(response, tag, class_name):
    """How many <tag class="class_name"> elements the page has."""
    return ClassCounter(response.content.decode(), tag, class_name).count


def send_form(client, page, button_name, **typed):
    """Press the one button named `button_name` on `page`, like a browser.

    The form's own fields (the CSRF token, `next`) are sent with what was
    typed. Follows the redirects and returns the last page.
    """
    pairs = [
        (form, button)
        for form in page_forms(page)
        for button in form.buttons
        if button.accessible_name == button_name
    ]
    if len(pairs) != 1:
        raise AssertionError(f"{len(pairs)} buttons named {button_name!r}, not 1")
    form, button = pairs[0]
    return client.post(form.action, form.data(button, **typed), follow=True)


def log_in(client, username, password=TEST_PASSWORD):
    """Log in through the real log-in page, like a person, and return the list.

    Opening "/" shows the log-in page. Fill in the form, press "Log in", and
    land on "/", which opens the person's first list.
    """
    page = client.get("/", follow=True)
    if page.redirect_chain != [(f"{LOGIN_URL}?next=/", 302)]:
        raise AssertionError(f"/ did not show the log-in page: {page.redirect_chain}")
    page = send_form(client, page, "Log in", username=username, password=password)
    user = get_user_model().objects.get(username=username)
    landing = [("/", 302), (list_path(first_list(user).pk), 302)]
    if page.redirect_chain != landing:
        raise AssertionError(f"Log in did not land on the list: {page.redirect_chain}")
    return page
