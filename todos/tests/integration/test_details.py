"""The details pane (feature 21): click a title, see everything about that to-do."""

from datetime import UTC, date, datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import (
    page_parts,
    page_without_csrf,
    pane_element,
    title_element,
)

HINT = '<p class="pane-hint">Click a to-do\'s title to see its details.</p>'


class DetailsPaneTests(TestCase):
    def setUp(self):
        self.milk = Todo.objects.create(title="Buy milk", due_date=date(2026, 10, 5))
        self.home = Todo.objects.create(title="Call home", done=True)
        # auto_now_add ignores a value given at create, so set it afterwards.
        # 15:30 UTC on 1 October is 00:30 on 2 October in Tokyo.
        Todo.objects.filter(pk=self.milk.pk).update(
            created_at=datetime(2026, 10, 1, 15, 30, tzinfo=UTC)
        )
        Todo.objects.filter(pk=self.home.pk).update(
            created_at=datetime(2026, 10, 3, 1, 0, tzinfo=UTC)
        )
        self.selected = f"?selected={self.milk.pk}"

    def milk_pane(self, close_url="/"):
        return pane_element(
            self.milk, due="5 Oct 2026", created="2 Oct 2026", close_url=close_url
        )

    # Details pane: new behaviour.

    def test_titles_are_links_that_keep_the_filter(self):
        for query in ["", "?show=active"]:
            with self.subTest(query=query):
                response = self.client.get("/" + query)
                element = title_element(self.milk, query)
                self.assertContains(response, element, count=1, html=True)
                expected = ["Buy milk"] if query else ["Buy milk", "Call home"]
                self.assertEqual(page_parts(response).titles, expected)

    def test_selected_shows_the_pane_and_marks_the_row(self):
        response = self.client.get("/" + self.selected)
        parts = page_parts(response)
        self.assertEqual(parts.panes, ["Details"])
        self.assertContains(response, self.milk_pane(), count=1, html=True)
        self.assertContains(
            response, title_element(self.milk, selected=True), count=1, html=True
        )
        self.assertEqual(parts.selected_titles, ["Buy milk"])
        self.assertIn("selected", parts.row("Buy milk").classes)
        self.assertEqual(parts.row("Buy milk").id, f"todo-{self.milk.pk}")
        self.assertNotIn("selected", parts.row("Call home").classes)
        # The hint is only for when nothing is selected.
        self.assertNotContains(response, HINT, html=True)

    def test_pane_shows_completed_and_no_due_date(self):
        response = self.client.get(f"/?selected={self.home.pk}")
        pane = pane_element(
            self.home, status="Completed", created="3 Oct 2026", close_url="/"
        )
        self.assertContains(response, pane, count=1, html=True)

    def test_title_is_escaped_in_the_pane(self):
        bold = Todo.objects.create(title="<b>x</b>")
        Todo.objects.filter(pk=bold.pk).update(
            created_at=datetime(2026, 10, 4, 1, 0, tzinfo=UTC)
        )
        response = self.client.get(f"/?selected={bold.pk}")
        self.assertEqual(page_parts(response).panes, ["Details"])
        # Its heading is <h2>&lt;b&gt;x&lt;/b&gt;</h2>: text, not a bold tag.
        pane = pane_element(bold, created="4 Oct 2026", close_url="/")
        self.assertContains(response, pane, count=1, html=True)
        # The row's title link is escaped too.
        row_title = title_element(bold, selected=True)
        self.assertContains(response, row_title, count=1, html=True)

    def test_close_keeps_the_filter(self):
        response = self.client.get(f"/?show=active&selected={self.milk.pk}")
        pane = self.milk_pane(close_url="/?show=active")
        self.assertContains(response, pane, count=1, html=True)

    def test_every_post_form_keeps_selected(self):
        query = f"?show=active&selected={self.milk.pk}"
        response = self.client.get("/" + query)
        self.assertEqual(
            page_parts(response).post_actions,
            [
                reverse("todo_add") + query,
                reverse("todo_toggle", args=[self.milk.pk]) + query,
                reverse("todo_delete", args=[self.milk.pk]) + query,
                reverse("todo_delete_completed") + query,
            ],
        )

    def test_redirects_keep_selected(self):
        cases = [
            ("add", reverse("todo_add"), {"title": "Read chapter 3"}),
            ("toggle", reverse("todo_toggle", args=[self.milk.pk]), {}),
            ("delete", reverse("todo_delete", args=[self.home.pk]), {}),
            ("delete completed", reverse("todo_delete_completed"), {"ids": []}),
        ]
        for name, url, data in cases:
            with self.subTest(name):
                response = self.client.post(url + self.selected, data)
                self.assertEqual(response["Location"], "/" + self.selected)

    def test_deleting_the_selected_todo_closes_the_pane(self):
        url = reverse("todo_delete", args=[self.milk.pk]) + self.selected
        response = self.client.post(url, follow=True)
        self.assertEqual(response.redirect_chain, [("/" + self.selected, 302)])
        self.assertEqual(
            page_without_csrf(response), page_without_csrf(self.client.get("/"))
        )

    def test_add_error_keeps_the_pane(self):
        response = self.client.post(
            reverse("todo_add") + self.selected,
            {"title": "Read chapter 3", "due_date": "not-a-date"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_parts(response).panes, ["Details"])
        self.assertContains(response, self.milk_pane(), count=1, html=True)

    def test_hint_when_nothing_is_selected(self):
        response = self.client.get("/")
        self.assertContains(response, HINT, count=1, html=True)
        self.assertEqual(page_parts(response).panes, [])

    def test_no_hint_when_the_shown_list_is_empty(self):
        # There is no title to click, so the hint would be wrong.
        Todo.objects.filter(done=True).delete()
        for name, url in [("empty filter", "/?show=completed"), ("empty table", "/")]:
            if name == "empty table":
                Todo.objects.all().delete()
            with self.subTest(name):
                response = self.client.get(url)
                self.assertEqual(page_parts(response).titles, [])
                self.assertNotContains(response, HINT, html=True)
                self.assertEqual(page_parts(response).panes, [])

    # Details pane: the sharing rule. An id that is not in the list on the
    # page gives exactly the page without `selected`.

    def test_selected_not_in_the_list_is_the_same_page_as_none(self):
        milk = self.milk.pk
        cases = [
            (f"/?show=active&selected={self.home.pk}", "/?show=active"),
            ("/?selected=999", "/"),
            ("/?selected=abc", "/"),
            ("/?selected=0", "/"),
            ("/?selected=", "/"),
            (f"/?selected={milk}&selected=abc", "/"),
        ]
        for url, same_as in cases:
            with self.subTest(url=url):
                self.assertEqual(
                    page_without_csrf(self.client.get(url)),
                    page_without_csrf(self.client.get(same_as)),
                )

    # Details pane: protect what already works.

    def test_selecting_costs_no_extra_query(self):
        with CaptureQueriesContext(connection) as without:
            self.client.get("/")
        with CaptureQueriesContext(connection) as with_selected:
            self.client.get("/" + self.selected)
        self.assertEqual(len(with_selected), len(without))
