"""Helpers that more than one integration test file uses.

They read the page, or build parts of it exactly as the page must show them,
so the tests can compare whole things instead of searching for a few words.
"""

import re
from html.parser import HTMLParser

CSRF_INPUT = re.compile(
    r'<input type="hidden" name="csrfmiddlewaretoken" value="[^"]*">'
)


def page_without_csrf(response):
    """The page's HTML without the CSRF token inputs.

    The token is different every time the page is drawn, so a test cannot
    write it down. Taking it out lets a test compare whole forms exactly.
    """
    return CSRF_INPUT.sub("", response.content.decode())


def delete_completed_form(ids, query=""):
    """The delete-completed form, exactly as the page must show it.

    `query` is the list query at the end of its address, like "?show=active".
    """
    hidden = "".join(f'<input type="hidden" name="ids" value="{pk}">' for pk in ids)
    count = len(ids)
    return (
        '<form class="delete-completed" method="post" '
        f'action="/delete-completed/{query}">'
        f"{hidden}"
        f'<button type="submit">Delete {count} completed to-do'
        f"{'' if count == 1 else 's'}</button>"
        "</form>"
    )


def list_footer(count_text, completed_ids=(), query=""):
    """The whole footer under the list, exactly as the page must show it."""
    form = delete_completed_form(completed_ids, query) if completed_ids else ""
    return f'<div class="list-footer"><p class="count">{count_text}</p>{form}</div>'


class PageParts(HTMLParser):
    """Reads the parts of the page the tests compare exactly.

    `post_actions` is the `action` of every form with method="post".
    `titles` is the title of every to-do shown, in order: the text of each
    <span class="title"> before any tag inside it (the due date is a <small>
    inside the span, and is not part of the title).
    `current_links` is the text of every link with aria-current="page". A test
    that compares it to one name proves that no OTHER link is marked too.
    """

    def __init__(self, html):
        super().__init__()
        self.post_actions = []
        self.titles = []
        self.current_links = []
        self._collect = None  # the list that the next text goes into
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        # Text inside a tag within the title (like the due date) is not the title.
        self._collect = None
        if tag == "form" and (attrs.get("method") or "").lower() == "post":
            self.post_actions.append(attrs.get("action", ""))
        if tag == "span" and attrs.get("class") == "title":
            self.titles.append("")
            self._collect = self.titles
        if tag == "a" and attrs.get("aria-current") == "page":
            self.current_links.append("")
            self._collect = self.current_links

    def handle_endtag(self, tag):
        self._collect = None

    def handle_data(self, data):
        if self._collect is not None:
            self._collect[-1] += data.strip()


def page_parts(response):
    return PageParts(response.content.decode())


class PageForm:
    """One form on the page: where it sends, and what it sends."""

    def __init__(self, method, action):
        self.method = method
        self.action = action
        self.fields = {}  # name -> value, from the form's own <input>s
        self.button = ""  # the text on its submit button

    def data(self, **typed):
        """What a browser sends: the form's own fields, plus what a person typed.

        Typing into a field the form does not have is a mistake in the test or
        the page, so it fails at once.
        """
        missing = set(typed) - set(self.fields)
        if missing:
            raise AssertionError(f"the form has no field {sorted(missing)}")
        return {**self.fields, **typed}


class PageForms(HTMLParser):
    """Reads every form on the page, with its inputs and its button text."""

    def __init__(self, html):
        super().__init__()
        self.forms = []
        self._form = None
        self._in_button = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            method = (attrs.get("method") or "get").lower()
            self._form = PageForm(method, attrs.get("action", ""))
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None and "name" in attrs:
            self._form.fields[attrs["name"]] = attrs.get("value") or ""
        elif tag == "button" and self._form is not None:
            self._in_button = True

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        elif tag == "button":
            self._in_button = False

    def handle_data(self, data):
        if self._in_button:
            self._form.button += data.strip()


def page_forms(response):
    return PageForms(response.content.decode()).forms
